//! Exact G02 commands and 100 ms economy rules.

use super::amount::{Amount, IntegralAmount, NonNegativeAmount, SafeU64};
use super::conversion::{ConversionError, convert_wire_ratio};
use super::evaluator::{EvaluatorError, ExactRatio, creativity_speed, sale_request, wire_quote};
use super::rng::GameRng;
use super::state::{GameState, ProState};
use num_bigint::BigInt;
use std::error::Error;
use std::fmt;

// Protect exact restoration from attacker-sized exponentiation. This is a decoder
// resource boundary, not a game-value clamp; rejecting at this boundary is explicit.
pub(crate) const MAX_EXACT_EXPONENT: u32 = 10_000;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EconomyError {
    InsufficientFunds,
    PriceAtMinimum,
    InvalidState,
    ExponentResourceLimit,
    CounterLimit,
    TrustCapacityFull,
    ComputationLocked,
    ProcessorEvaluatorDomain,
    Evaluator(EvaluatorError),
}

impl fmt::Display for EconomyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InsufficientFunds => formatter.write_str("insufficient funds"),
            Self::PriceAtMinimum => formatter.write_str("price is already at its minimum"),
            Self::InvalidState => formatter.write_str("economy state is outside its domain"),
            Self::ExponentResourceLimit => {
                formatter.write_str("exact economy exponent exceeds the evaluation resource limit")
            }
            Self::CounterLimit => formatter.write_str("economy counter reached its safe limit"),
            Self::TrustCapacityFull => {
                formatter.write_str("no unspent Trust configuration capacity remains")
            }
            Self::ComputationLocked => {
                formatter.write_str("computational resources are still locked")
            }
            Self::ProcessorEvaluatorDomain => formatter
                .write_str("the requested Processor count exceeds the supported evaluator domain"),
            Self::Evaluator(error) => write!(formatter, "{error}"),
        }
    }
}

impl Error for EconomyError {}

impl From<EvaluatorError> for EconomyError {
    fn from(error: EvaluatorError) -> Self {
        Self::Evaluator(error)
    }
}

fn whole(value: &IntegralAmount) -> BigInt {
    ProState::integral_mantissa(value)
}

fn marketing_exponent(level: &IntegralAmount) -> Result<u32, EconomyError> {
    let level = whole(level);
    if level < BigInt::from(1u8) {
        return Err(EconomyError::InvalidState);
    }
    let exponent = level - BigInt::from(1u8);
    if exponent > BigInt::from(MAX_EXACT_EXPONENT) {
        return Err(EconomyError::ExponentResourceLimit);
    }
    u32::try_from(exponent).map_err(|_| EconomyError::ExponentResourceLimit)
}

pub(crate) fn marketing_cost_for_level(level: &IntegralAmount) -> Result<Amount, EconomyError> {
    let exponent = marketing_exponent(level)?;
    Ok(Amount::from_i128(100).multiply_integer(&BigInt::from(2u8).pow(exponent)))
}

/// Exact demand formula, before its separate binary64 sale-request conversion.
pub fn demand_ratio(state: &ProState) -> Result<ExactRatio, EconomyError> {
    let scale = Amount::from_i128(1).mantissa().clone();
    if state.price_per_clip <= Amount::zero()
        || state.marketing_effectiveness < Amount::zero()
        || state.demand_boost < Amount::zero()
        || whole(&state.prestige_u) < BigInt::from(0u8)
    {
        return Err(EconomyError::InvalidState);
    }
    let exponent = marketing_exponent(&state.marketing_level)?;
    // 0.8 / (price_mantissa/scale).
    let mut numerator = &scale * 4u8;
    let mut denominator = state.price_per_clip.mantissa() * 5u8;
    numerator *= BigInt::from(11u8).pow(exponent);
    denominator *= BigInt::from(10u8).pow(exponent);
    numerator *= state.marketing_effectiveness.mantissa();
    denominator *= &scale;
    numerator *= state.demand_boost.mantissa();
    denominator *= &scale;
    // 1 + prestige_u/10, where prestige_u is integral in whole units.
    numerator *= &scale * 10u8 + whole(&state.prestige_u);
    denominator *= &scale * 10u8;
    ExactRatio::new(numerator, denominator).map_err(EconomyError::from)
}

/// Recompute only the exact public demand cache, without using it for probability.
pub fn refresh_demand(state: &mut ProState) -> Result<(), EconomyError> {
    let ratio = demand_ratio(state)?;
    let cache = Amount::quantize_ratio(ratio.numerator(), ratio.denominator())
        .map_err(|_| EconomyError::InvalidState)?
        .nonnegative()
        .map_err(|_| EconomyError::InvalidState)?;
    state.demand = cache;
    Ok(())
}

pub fn buy_wire(state: &mut ProState) -> Result<(), EconomyError> {
    let mut next = state.clone();
    if next.wire_quote.is_negative() || next.funds < next.wire_quote {
        return Err(EconomyError::InsufficientFunds);
    }
    let funds = &next.funds - &next.wire_quote;
    let wire = next.wire.add_exact(&next.wire_spool_length);
    let purchases = next
        .wire_purchase_count
        .checked_add(1)
        .map_err(|_| EconomyError::CounterLimit)?;
    let base =
        &next.wire_base_price + &Amount::parse("0.05").map_err(|_| EconomyError::InvalidState)?;
    next.funds = funds;
    next.wire = wire;
    next.wire_purchase_count = purchases;
    next.wire_base_price = base;
    next.wire_inactivity_ticks = SafeU64::new(0).map_err(|_| EconomyError::CounterLimit)?;
    // Source buyWire does not adjust the existing quote or sine counter.
    *state = next;
    Ok(())
}

pub fn lower_price(state: &mut ProState) -> Result<(), EconomyError> {
    let mut next = state.clone();
    let cent = Amount::parse("0.01").map_err(|_| EconomyError::InvalidState)?;
    if next.price_per_clip <= cent {
        return Err(EconomyError::PriceAtMinimum);
    }
    next.price_per_clip = &next.price_per_clip - &cent;
    refresh_demand(&mut next)?;
    *state = next;
    Ok(())
}

pub fn raise_price(state: &mut ProState) -> Result<(), EconomyError> {
    let mut next = state.clone();
    let cent = Amount::parse("0.01").map_err(|_| EconomyError::InvalidState)?;
    next.price_per_clip = &next.price_per_clip + &cent;
    refresh_demand(&mut next)?;
    *state = next;
    Ok(())
}

pub fn buy_marketing(state: &mut ProState) -> Result<(), EconomyError> {
    let mut next = state.clone();
    // Charge the pre-purchase cost before incrementing the exact stored level.
    let cost = marketing_cost_for_level(&next.marketing_level)?;
    if next.funds < cost {
        return Err(EconomyError::InsufficientFunds);
    }
    next.funds = &next.funds - &cost;
    let incremented = whole(&next.marketing_level) + BigInt::from(1u8);
    next.marketing_level = Amount::from_i128(1)
        .multiply_integer(&incremented)
        .integral()
        .map_err(|_| EconomyError::InvalidState)?;
    refresh_demand(&mut next)?;
    *state = next;
    Ok(())
}

pub(crate) fn push_console_message(state: &mut ProState, message: String) {
    state.console_messages.rotate_left(1);
    state.console_messages[4] = message;
}

pub const COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE: &str = "Trust-Constrained Self-Modification";

/// Exact source availability condition, independent of the persisted visibility latch.
pub fn computational_resources_unlock_condition(state: &ProState) -> bool {
    let one = Amount::from_i128(1);
    state.lifetime_clips.amount() >= &Amount::from_i128(2_000)
        || (state.unsold_clips.amount() < &one
            && state.funds < state.wire_quote
            && state.wire.amount() < &one)
}

/// Observe both availability flags atomically after a successful legal update.
/// The visible state is the one-way latch; no later observation can relock it.
pub fn observe_computational_resources(state: &mut ProState) {
    if state.computing_hidden
        && state.projects_hidden
        && computational_resources_unlock_condition(state)
    {
        state.computing_hidden = false;
        state.projects_hidden = false;
        push_console_message(state, COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE.to_owned());
    }
}

fn integral_from_whole(value: BigInt) -> Result<IntegralAmount, EconomyError> {
    Amount::from_i128(1)
        .multiply_integer(&value)
        .integral()
        .map_err(|_| EconomyError::InvalidState)
}

fn trust_target_announcement(target: &IntegralAmount) -> String {
    let exact = target.to_string();
    if exact.len() <= 160 {
        format!("Trust target {exact} reached: +1 Trust; Processor/Memory capacity increased.")
    } else {
        // Keep bounded console history valid even for extreme retained targets.
        // The exact target/cursor remain authoritative Amount fields; this is
        // one per-target emission, never an aggregate or a target clamp.
        format!(
            "Trust target with {} decimal digits reached: +1 Trust; Processor/Memory capacity increased.",
            exact.len()
        )
    }
}

/// Catch up every exact Human production target in one serialized observation.
/// Cursor advancement is the one-once record shared by ticks, retries and restore.
pub fn observe_trust_targets(state: &mut ProState) -> Result<(), EconomyError> {
    let mut next = state.clone();
    if whole(&next.next_trust_target) <= BigInt::from(0u8)
        || whole(&next.trust_target_predecessor) <= BigInt::from(0u8)
        || next.next_trust_target <= next.trust_target_predecessor
    {
        return Err(EconomyError::InvalidState);
    }
    while next.lifetime_clips.amount() >= next.next_trust_target.amount() {
        // Trust is total capacity. Allocation never reverses this increment.
        next.trust = integral_from_whole(whole(&next.trust) + BigInt::from(1u8))?;
        let announcement = trust_target_announcement(&next.next_trust_target);
        push_console_message(&mut next, announcement);
        let successor = whole(&next.trust_target_predecessor) + whole(&next.next_trust_target);
        next.trust_target_predecessor = next.next_trust_target.clone();
        next.next_trust_target = integral_from_whole(successor)?;
    }
    *state = next;
    Ok(())
}

fn check_allocation_availability(state: &ProState) -> Result<(), EconomyError> {
    if state.computing_hidden {
        return Err(EconomyError::ComputationLocked);
    }
    if whole(&state.processors) + whole(&state.memory) >= whole(&state.trust) {
        return Err(EconomyError::TrustCapacityFull);
    }
    Ok(())
}

/// Add one Processor only after the complete new-count speed evaluation succeeds.
pub fn add_processor(state: &mut ProState) -> Result<(), EconomyError> {
    check_allocation_availability(state)?;
    let new_count = integral_from_whole(whole(&state.processors) + BigInt::from(1u8))?;
    // Exact-P domain checks and every binary64/final-grid guard happen before
    // the cloned authoritative candidate receives any allocation/speed write.
    let new_speed = creativity_speed(&new_count).map_err(|error| match error {
        EvaluatorError::OutsideProcessorDomain => EconomyError::ProcessorEvaluatorDomain,
        other => EconomyError::Evaluator(other),
    })?;
    let mut next = state.clone();
    next.processors = new_count;
    next.creativity_speed = new_speed;
    push_console_message(
        &mut next,
        "Processor added: standard Ops rate +10/s; Creativity speed recomputed.".to_owned(),
    );
    *state = next;
    Ok(())
}

/// Add exactly one Memory and 1000 standard Ops capacity; speed is untouched.
pub fn add_memory(state: &mut ProState) -> Result<(), EconomyError> {
    check_allocation_availability(state)?;
    let mut next = state.clone();
    next.memory = integral_from_whole(whole(&next.memory) + BigInt::from(1u8))?;
    push_console_message(
        &mut next,
        "Memory added, max operations increased.".to_owned(),
    );
    *state = next;
    Ok(())
}

/// Latch reveal only after the authoritative Funds balance actually reaches 5.
pub fn observe_auto_clipper_reveal(state: &mut ProState) {
    if !state.auto_clipper_revealed && state.funds >= Amount::from_i128(5) {
        state.auto_clipper_revealed = true;
        push_console_message(state, "AutoClippers revealed: Funds reached $5.".to_owned());
    }
}

/// Exact 5 + (11/10)^level, ceiled only at the final 10^-18 price boundary.
/// This is an integer-exponent rational, not a binary64 transcendental operation.
fn auto_clipper_successor_cost(level: &BigInt) -> Result<Amount, EconomyError> {
    if *level < BigInt::from(1u8) {
        return Err(EconomyError::InvalidState);
    }
    if *level > BigInt::from(MAX_EXACT_EXPONENT) {
        return Err(EconomyError::ExponentResourceLimit);
    }
    let level = u32::try_from(level).map_err(|_| EconomyError::ExponentResourceLimit)?;
    let numerator = BigInt::from(11u8).pow(level) * Amount::from_i128(1).mantissa();
    let denominator = BigInt::from(10u8).pow(level);
    let mut increment = &numerator / &denominator;
    if numerator % &denominator != BigInt::from(0u8) {
        increment += 1u8;
    }
    Ok(Amount::from_mantissa(
        Amount::from_i128(5).mantissa() + increment,
    ))
}

/// Buy exactly one producer at the stored current price at writer execution.
pub fn buy_auto_clipper(state: &mut ProState) -> Result<(), EconomyError> {
    let mut next = state.clone();
    let charged = next.auto_clipper_cost.clone();
    if charged < Amount::from_i128(5) || next.auto_clippers.amount().is_negative() {
        return Err(EconomyError::InvalidState);
    }
    if next.funds < charged {
        return Err(EconomyError::InsufficientFunds);
    }
    let level = whole(&next.auto_clippers) + BigInt::from(1u8);
    let successor = auto_clipper_successor_cost(&level)?;
    observe_auto_clipper_reveal(&mut next);
    next.funds = &next.funds - &charged;
    next.auto_clippers = Amount::from_i128(1)
        .multiply_integer(&level)
        .integral()
        .map_err(|_| EconomyError::InvalidState)?;
    next.auto_clipper_cost = successor;
    // Keep bounded feedback independent of an unbounded exact successor's digits.
    // The typed public cost fields carry that exact value; console remains short.
    let message = format!("AutoClipper {} purchased.", next.auto_clippers);
    push_console_message(&mut next, message);
    *state = next;
    Ok(())
}

/// One logical 10 ms step of nominal one-clip/s producer requests.
/// Only time after the writer admitted ownership is part of this request.
pub fn advance_auto_clippers(state: &mut GameState, second_due: bool) -> Result<(), EconomyError> {
    let mut next = state.clone();
    let request = whole(&next.pro.auto_clippers);
    if request < BigInt::from(0u8)
        || (request > BigInt::from(0u8) && !next.pro.auto_clipper_revealed)
    {
        return Err(EconomyError::InvalidState);
    }
    let actual = if request == BigInt::from(0u8)
        || next.pro.wire < NonNegativeAmount::from_i128(1).expect("one is nonnegative")
    {
        // Zero producers never call conversion. G01's ordinary Wire gate also
        // precedes every computed request, including positive remainders.
        NonNegativeAmount::zero()
    } else {
        // 10 ms is exactly 1/100 second on the Amount grid. Quantize only the
        // operation-local request; the later capped conserved transfer is exact.
        match convert_wire_ratio(&mut next.pro, &request, &BigInt::from(100u8)) {
            Ok(actual) => actual,
            Err(ConversionError::InsufficientWire) => NonNegativeAmount::zero(),
            Err(_) => return Err(EconomyError::InvalidState),
        }
    };
    next.pro.auto_clipper_production_accumulator = next
        .pro
        .auto_clipper_production_accumulator
        .add_exact(&actual);
    if second_due {
        // Rollover reports the actual latest complete interval, never the
        // producer count guessed from current elapsed or remaining Wire.
        next.pro.auto_clipper_rate = next.pro.auto_clipper_production_accumulator.clone();
        next.pro.auto_clipper_production_accumulator = NonNegativeAmount::zero();
    }
    *state = next;
    Ok(())
}

/// Quantize currency toward a nonnegative mill or cent while retaining 10^-18 grid.
fn floor_units(amount: &Amount, decimal_places: u32) -> Amount {
    let divisor = BigInt::from(10u8).pow(18 - decimal_places);
    let mut quotient = amount.mantissa() / &divisor;
    if amount.mantissa() < &BigInt::from(0u8) && amount.mantissa() % &divisor != BigInt::from(0u8) {
        quotient -= 1u8;
    }
    Amount::from_mantissa(quotient * divisor)
}

fn requested_amount(request: u64) -> NonNegativeAmount {
    Amount::from_i128(i128::from(request))
        .nonnegative()
        .expect("checked u64 request is nonnegative")
}

fn process_sale(state: &mut ProState, requested: u64) {
    if state.unsold_clips.amount().is_zero() {
        return;
    }
    let requested = requested_amount(requested);
    if requested > state.unsold_clips {
        let sold = state.unsold_clips.clone();
        let transaction = floor_transaction(sold.amount(), &state.price_per_clip);
        next_stock_limited_sale(state, sold, transaction);
    } else {
        let transaction = floor_transaction(requested.amount(), &state.price_per_clip);
        let new_unsold = state
            .unsold_clips
            .checked_sub(&requested)
            .expect("in-stock request was checked");
        let new_funds = floor_units(&(&state.funds + &transaction), 2);
        state.clips_sold = state.clips_sold.add_exact(&requested);
        state.unsold_clips = new_unsold;
        state.funds = new_funds;
        state.income = &state.income + &transaction;
        state.last_sale_revenue = transaction;
    }
}

fn floor_transaction(quantity: &Amount, price: &Amount) -> Amount {
    // (quantity_m * price_m * 10^-36)*1000, floored, then /1000.
    // The resulting 10^-18 mantissa is floor(product_m / 10^33) * 10^15.
    let product = quantity.mantissa() * price.mantissa();
    let divisor = BigInt::from(10u8).pow(33u32);
    let thousands = product / &divisor;
    Amount::from_mantissa(thousands * BigInt::from(10u8).pow(15u32))
}

fn next_stock_limited_sale(state: &mut ProState, sold: NonNegativeAmount, transaction: Amount) {
    state.clips_sold = state.clips_sold.add_exact(&sold);
    state.unsold_clips = NonNegativeAmount::zero();
    // Exactly the source's mill-floor branch: no cent floor here.
    state.funds = &state.funds + &transaction;
    state.income = &state.income + &transaction;
    state.last_sale_revenue = transaction;
}

pub(crate) fn sales_opportunity(
    state: &mut ProState,
    demand: &ExactRatio,
) -> Result<(), EconomyError> {
    let mut next = state.clone();
    let request = sale_request(demand)?;
    process_sale(&mut next, request);
    *state = next;
    Ok(())
}

/// Uniform integer comparison equivalent to the source open probability interval.
fn bounded_uniform_success(roll: u64, probability: &ExactRatio) -> bool {
    // roll has 53 random bits. Use roll/2^53 < probability directly in BigInt.
    (BigInt::from(roll) * probability.denominator())
        < (BigInt::from(1u8) << 53) * probability.numerator()
}

fn roll53(rng: &mut GameRng) -> u64 {
    rng.next_u64() >> 11
}

/// One logical 100 ms phase: Wire first, then one independent sales draw.
pub fn advance_fast_phase(state: &mut GameState) -> Result<(), EconomyError> {
    let mut next = state.clone();
    let inactivity = next
        .pro
        .wire_inactivity_ticks
        .checked_add(1)
        .map_err(|_| EconomyError::CounterLimit)?;
    next.pro.wire_inactivity_ticks = inactivity;
    if inactivity.get() > 250 && next.pro.wire_base_price > Amount::from_i128(15) {
        let decayed = Amount::from_mantissa(next.pro.wire_base_price.mantissa() * 999u16 / 1000u16);
        next.pro.wire_base_price = decayed;
        next.pro.wire_inactivity_ticks = SafeU64::new(0).map_err(|_| EconomyError::CounterLimit)?;
    }
    if bounded_uniform_success(
        roll53(&mut next.rng),
        &ExactRatio::new(BigInt::from(3u8), BigInt::from(200u8))
            .map_err(|_| EconomyError::InvalidState)?,
    ) {
        next.pro.wire_price_counter = next
            .pro
            .wire_price_counter
            .checked_add(1)
            .map_err(|_| EconomyError::CounterLimit)?;
        next.pro.wire_quote = Amount::from_i128(i128::from(wire_quote(
            &next.pro.wire_base_price,
            next.pro.wire_price_counter,
        )?));
    }
    let demand = demand_ratio(&next.pro)?;
    let chance = ExactRatio::new(
        demand.numerator().clone(),
        demand.denominator().clone() * 100u8,
    )
    .map_err(|_| EconomyError::InvalidState)?;
    if bounded_uniform_success(roll53(&mut next.rng), &chance) {
        sales_opportunity(&mut next.pro, &demand)?;
    }
    *state = next;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::amount::MAX_SAFE_JSON_INTEGER;
    use crate::game::rng::GameRng;

    fn positive(text: &str) -> NonNegativeAmount {
        Amount::parse(text).unwrap().nonnegative().unwrap()
    }

    fn game() -> GameState {
        GameState::fresh(GameRng::from_test_seed([7u8; 32]))
    }

    #[test]
    fn exact_demand_and_price_boundaries_follow_the_source() {
        let mut state = ProState::fresh();
        assert_eq!(state.demand.to_string(), "3.2");
        assert_eq!(demand_ratio(&state).unwrap().to_f64().unwrap(), 3.2);
        raise_price(&mut state).unwrap();
        assert_eq!(state.price_per_clip.to_string(), "0.26");
        assert_eq!(state.demand.to_string(), "3.076923076923076923");
        state.price_per_clip = Amount::parse("0.01").unwrap();
        let before = state.clone();
        assert_eq!(lower_price(&mut state), Err(EconomyError::PriceAtMinimum));
        assert_eq!(state, before);
        state.price_per_clip = Amount::parse("0.011").unwrap();
        lower_price(&mut state).unwrap();
        assert_eq!(state.price_per_clip.to_string(), "0.001");
    }

    #[test]
    fn purchase_and_marketing_fail_closed_before_mutating() {
        let mut state = ProState::fresh();
        let before = state.clone();
        assert_eq!(buy_wire(&mut state), Err(EconomyError::InsufficientFunds));
        assert_eq!(
            buy_marketing(&mut state),
            Err(EconomyError::InsufficientFunds)
        );
        assert_eq!(state, before);
        state.funds = Amount::parse("120.02").unwrap();
        buy_wire(&mut state).unwrap();
        assert_eq!(state.funds.to_string(), "100.02");
        assert_eq!(state.wire.to_string(), "2000");
        assert_eq!(state.wire_base_price.to_string(), "20.05");
        assert_eq!(state.wire_quote.to_string(), "20");
        assert_eq!(state.wire_price_counter.get(), 0);
        assert_eq!(state.wire_purchase_count.get(), 1);
        buy_marketing(&mut state).unwrap();
        assert_eq!(state.funds.to_string(), "0.02");
        assert_eq!(state.marketing_level.to_string(), "2");
        assert_eq!(state.marketing_cost().unwrap().to_string(), "200");
        assert_eq!(state.demand.to_string(), "3.52");
        let cached = state.clone();
        assert_eq!(
            buy_marketing(&mut state),
            Err(EconomyError::InsufficientFunds)
        );
        assert_eq!(state, cached);
    }

    #[test]
    fn both_sales_branches_keep_the_source_fractional_floor_difference() {
        let mut ordinary = ProState::fresh();
        ordinary.unsold_clips = positive("5");
        ordinary.unused_clips = positive("5");
        ordinary.lifetime_clips = positive("5");
        ordinary.funds = Amount::parse("0.004").unwrap();
        ordinary.price_per_clip = Amount::parse("0.333").unwrap();
        sales_opportunity(
            &mut ordinary,
            &ExactRatio::new(BigInt::from(4u8), BigInt::from(1u8)).unwrap(),
        )
        .unwrap();
        assert_eq!(ordinary.unsold_clips.to_string(), "2");
        assert_eq!(ordinary.clips_sold.to_string(), "3");
        assert_eq!(ordinary.last_sale_revenue.to_string(), "0.999");
        assert_eq!(ordinary.income.to_string(), "0.999");
        assert_eq!(ordinary.funds.to_string(), "1");

        let mut limited = ProState::fresh();
        limited.unsold_clips = positive("1.5");
        limited.unused_clips = positive("1.5");
        limited.lifetime_clips = positive("1.5");
        limited.funds = Amount::parse("0.004").unwrap();
        limited.price_per_clip = Amount::parse("0.333").unwrap();
        sales_opportunity(
            &mut limited,
            &ExactRatio::new(BigInt::from(4u8), BigInt::from(1u8)).unwrap(),
        )
        .unwrap();
        eprintln!(
            "stock-limited trace: sold={} unsold={} funds={} income={} transaction={}",
            limited.clips_sold,
            limited.unsold_clips,
            limited.funds,
            limited.income,
            limited.last_sale_revenue
        );
        assert_eq!(limited.unsold_clips.to_string(), "0");
        assert_eq!(limited.clips_sold.to_string(), "1.5");
        assert_eq!(limited.last_sale_revenue.to_string(), "0.499");
        assert_eq!(limited.income.to_string(), "0.499");
        assert_eq!(limited.funds.to_string(), "0.503");
        assert_eq!(limited.unused_clips.to_string(), "1.5");
    }

    #[test]
    fn zero_and_stockout_sales_do_not_inflate_any_ledger() {
        let mut stockout = ProState::fresh();
        stockout.last_sale_revenue = Amount::parse("2.756").unwrap();
        let before = stockout.clone();
        sales_opportunity(
            &mut stockout,
            &ExactRatio::new(BigInt::from(100u8), BigInt::from(1u8)).unwrap(),
        )
        .unwrap();
        assert_eq!(stockout, before);

        let mut zero = ProState::fresh();
        zero.unsold_clips = positive("4");
        zero.funds = Amount::parse("0.009").unwrap();
        sales_opportunity(
            &mut zero,
            &ExactRatio::new(BigInt::from(1u8), BigInt::from(1u8)).unwrap(),
        )
        .unwrap();
        assert_eq!(zero.funds.to_string(), "0");
        assert_eq!(zero.unsold_clips.to_string(), "4");
        assert_eq!(zero.clips_sold.to_string(), "0");
        assert_eq!(zero.income.to_string(), "0");
    }

    #[test]
    fn wire_phase_order_decay_threshold_and_conservation_are_testable() {
        let mut state = game();
        state.pro.wire_inactivity_ticks = SafeU64::new(250).unwrap();
        state.pro.wire_base_price = Amount::from_i128(20);
        advance_fast_phase(&mut state).unwrap();
        assert_eq!(state.pro.wire_inactivity_ticks.get(), 0);
        assert_eq!(state.pro.wire_base_price.to_string(), "19.98");
        let produced = positive("3");
        state.pro.unused_clips = produced.clone();
        state.pro.unsold_clips = produced.clone();
        state.pro.lifetime_clips = produced.clone();
        advance_fast_phase(&mut state).unwrap();
        assert_eq!(
            state.pro.unsold_clips.add_exact(&state.pro.clips_sold),
            produced
        );
        assert_eq!(state.pro.lifetime_clips.to_string(), "3");
        assert_eq!(state.pro.unused_clips.to_string(), "3");
    }

    #[test]
    fn inactivity_keeps_counting_when_base_cannot_decay() {
        let mut state = game();
        state.pro.wire_base_price = Amount::from_i128(15);
        state.pro.wire_inactivity_ticks = SafeU64::new(250).unwrap();
        advance_fast_phase(&mut state).unwrap();
        assert!(state.pro.wire_inactivity_ticks.get() > 250);
        assert_eq!(state.pro.wire_base_price.to_string(), "15");
    }

    #[test]
    fn evaluator_failures_do_not_advance_any_candidate_field_or_rng() {
        let mut state = game();
        state.pro.wire_price_counter = SafeU64::new(MAX_SAFE_JSON_INTEGER).unwrap();
        let mut observed_counter_failure = false;
        for _ in 0..100 {
            let pro_before = state.pro.clone();
            let rng_before = state.rng_state_hex();
            match advance_fast_phase(&mut state) {
                Err(EconomyError::CounterLimit) => {
                    assert_eq!(state.pro, pro_before);
                    assert_eq!(state.rng_state_hex(), rng_before);
                    observed_counter_failure = true;
                    break;
                }
                Ok(()) => {}
                Err(other) => panic!("unexpected error: {other}"),
            }
        }
        assert!(observed_counter_failure);

        let mut state = ProState::fresh();
        state.unsold_clips = positive("1");
        let before = state.clone();
        let huge = ExactRatio::new(BigInt::from(10u8).pow(18u32), BigInt::from(1u8)).unwrap();
        assert_eq!(
            sales_opportunity(&mut state, &huge),
            Err(EconomyError::Evaluator(
                EvaluatorError::OutsideDecisionDomain
            ))
        );
        assert_eq!(state, before);
    }
}

#[cfg(test)]
mod autoclipper_tests {
    use super::*;

    fn positive(text: &str) -> NonNegativeAmount {
        Amount::parse(text).unwrap().nonnegative().unwrap()
    }

    fn game() -> GameState {
        GameState::fresh(GameRng::from_test_seed([41u8; 32]))
    }

    #[test]
    fn reveal_latches_at_actual_crossing_and_never_recomputes_initial_price() {
        let mut state = ProState::fresh();
        state.funds = Amount::parse("4.99").unwrap();
        observe_auto_clipper_reveal(&mut state);
        assert!(!state.auto_clipper_revealed);
        assert_eq!(state.auto_clipper_cost, Amount::from_i128(5));

        state.funds = Amount::from_i128(5);
        observe_auto_clipper_reveal(&mut state);
        assert!(state.auto_clipper_revealed);
        assert_eq!(state.console_messages.len(), 5);
        assert_eq!(
            state.console_messages[4],
            "AutoClippers revealed: Funds reached $5."
        );
        state.funds = Amount::zero();
        observe_auto_clipper_reveal(&mut state);
        assert!(state.auto_clipper_revealed);
        assert_eq!(state.auto_clipper_cost, Amount::from_i128(5));
    }

    #[test]
    fn exact_stored_cost_lifecycle_and_below_cost_rejection_are_atomic() {
        let mut state = ProState::fresh();
        state.funds = Amount::from_i128(5);
        observe_auto_clipper_reveal(&mut state);
        state.funds = Amount::parse("4.99").unwrap();
        let before = state.clone();
        assert_eq!(
            buy_auto_clipper(&mut state),
            Err(EconomyError::InsufficientFunds)
        );
        assert_eq!(state, before, "4.99 cannot buy the stored price 5");
        eprintln!(
            "G03 below-cost rejection: Funds 4.99/count 0/cost 5 unchanged; latch remained true"
        );

        state.funds = Amount::from_i128(5);
        buy_auto_clipper(&mut state).unwrap();
        assert_eq!(state.funds, Amount::zero());
        assert_eq!(state.auto_clippers.to_string(), "1");
        assert_eq!(state.auto_clipper_cost.to_string(), "6.1");
        assert!(state.auto_clipper_revealed);
        assert_eq!(state.wire.to_string(), "1000");
        assert_eq!(state.lifetime_clips.to_string(), "0");
        eprintln!("G03 exact threshold receipt: charged 5 -> Funds 0/count 1/next 6.1");

        state.funds = Amount::from_i128(20);
        buy_auto_clipper(&mut state).unwrap();
        assert_eq!(state.funds.to_string(), "13.9");
        assert_eq!(state.auto_clippers.to_string(), "2");
        assert_eq!(state.auto_clipper_cost.to_string(), "6.21");
        state.funds = Amount::from_i128(100);
        buy_auto_clipper(&mut state).unwrap();
        assert_eq!(state.auto_clipper_cost.to_string(), "6.331");
        eprintln!(
            "G03 successors: stored 6.1 charged to count 2/next 6.21; third next 6.331 (not cents)"
        );
    }

    #[test]
    fn successor_price_is_an_exact_rational_ceil_at_the_grid_only() {
        for (level, expected) in [
            (1, "6.1"),
            (2, "6.21"),
            (3, "6.331"),
            (7, "6.9487171"),
            (18, "10.559917313492231481"),
            (19, "11.11590904484145463"),
            (20, "11.727499949325600093"),
        ] {
            assert_eq!(
                auto_clipper_successor_cost(&BigInt::from(level))
                    .unwrap()
                    .to_string(),
                expected
            );
        }
        let mut boundary = ProState {
            auto_clippers: IntegralAmount::from_i128(i128::from(MAX_EXACT_EXPONENT) - 1),
            auto_clipper_cost: Amount::parse("6.1").unwrap(),
            funds: Amount::from_i128(100),
            ..ProState::fresh()
        };
        buy_auto_clipper(&mut boundary).unwrap();
        let boundary_state = GameState {
            pro: boundary,
            ..game()
        };
        let snapshot = crate::snapshot::Snapshot::capture(&boundary_state, 1).unwrap();
        assert!(snapshot.pro.console_messages[4].len() <= 256);
        assert_eq!(snapshot.pro.auto_clippers.to_string(), "10000");
        assert!(snapshot.pro.auto_clipper_cost.to_string().len() > 256);
        assert_eq!(
            snapshot.pro.console_messages[4],
            "AutoClipper 10000 purchased."
        );

        let before = ProState {
            auto_clippers: IntegralAmount::from_i128(i128::from(MAX_EXACT_EXPONENT)),
            auto_clipper_cost: Amount::parse("6.1").unwrap(),
            funds: Amount::from_i128(100),
            ..ProState::fresh()
        };
        let mut state = before.clone();
        assert_eq!(
            buy_auto_clipper(&mut state),
            Err(EconomyError::ExponentResourceLimit)
        );
        assert_eq!(state, before);
    }

    #[test]
    fn first_and_second_producers_use_conserved_conversion_and_positive_final_cap() {
        let mut state = game();
        state.pro.auto_clippers = IntegralAmount::from_i128(1);
        state.pro.auto_clipper_revealed = true;
        state.pro.wire = positive("2");
        for tick in 1..=100 {
            // denom=100 quantizes 1/100 exactly on the 10^-18 grid per tick.
            advance_auto_clippers(&mut state, tick % 100 == 0).unwrap();
            if tick == 10 {
                assert_eq!(state.pro.lifetime_clips.to_string(), "0.1");
                assert_eq!(state.pro.auto_clipper_rate.to_string(), "0");
            }
        }
        assert_eq!(state.pro.wire.to_string(), "1");
        assert_eq!(state.pro.lifetime_clips.to_string(), "1");
        assert_eq!(state.pro.auto_clipper_rate.to_string(), "1");
        assert_eq!(
            state.pro.auto_clipper_production_accumulator.to_string(),
            "0"
        );
        for tick in 1..=100 {
            advance_auto_clippers(&mut state, tick % 100 == 0).unwrap();
        }
        // G01 allows another 0.01 at Wire 1, then leaves 0.99 below its gate.
        // Nothing can manufacture a full second clip from the missing stock.
        assert_eq!(state.pro.wire.to_string(), "0.99");
        assert_eq!(state.pro.lifetime_clips.to_string(), "1.01");
        assert_eq!(state.pro.auto_clipper_rate.to_string(), "0.01");
        for tick in 1..=100 {
            advance_auto_clippers(&mut state, tick % 100 == 0).unwrap();
        }
        assert_eq!(state.pro.lifetime_clips.to_string(), "1.01");
        assert_eq!(state.pro.auto_clipper_rate.to_string(), "0");

        let mut fractional = game();
        fractional.pro.auto_clippers = IntegralAmount::from_i128(2);
        fractional.pro.auto_clipper_revealed = true;
        fractional.pro.wire = positive("1.5");
        for tick in 1..=100 {
            advance_auto_clippers(&mut fractional, tick % 100 == 0).unwrap();
        }
        // 0.52 is produced while the G01 gate stays open; 0.98 is stranded
        // strictly below one Wire, with exact conserved increments throughout.
        assert_eq!(fractional.pro.wire.to_string(), "0.98");
        for ledger in [
            &fractional.pro.lifetime_clips,
            &fractional.pro.unsold_clips,
            &fractional.pro.unused_clips,
            &fractional.pro.auto_clipper_rate,
        ] {
            assert_eq!(ledger, &positive("0.52"));
        }
        assert_eq!(
            fractional
                .pro
                .auto_clipper_production_accumulator
                .to_string(),
            "0"
        );

        // A stock-limited final request itself can be fractional. Quantization
        // applies only to this request, never to the conserved capped transfer.
        let mut final_partial = game();
        final_partial.pro.auto_clippers = IntegralAmount::from_i128(200);
        final_partial.pro.auto_clipper_revealed = true;
        final_partial.pro.wire = positive("1.005");
        advance_auto_clippers(&mut final_partial, true).unwrap();
        assert_eq!(final_partial.pro.wire, NonNegativeAmount::zero());
        for ledger in [
            &final_partial.pro.lifetime_clips,
            &final_partial.pro.unsold_clips,
            &final_partial.pro.unused_clips,
            &final_partial.pro.auto_clipper_rate,
        ] {
            assert_eq!(ledger, &positive("1.005"));
        }
        assert_eq!(
            final_partial
                .pro
                .auto_clipper_production_accumulator
                .to_string(),
            "0"
        );
        eprintln!(
            "G01/G03 partial cap: count 200 requests 2, Wire 1.005 -> all three ledgers +1.005, Wire 0; sub-one stock produces nothing further"
        );
    }

    #[test]
    fn zero_producers_or_no_elapsed_second_never_requests_or_mints() {
        let mut state = game();
        let before = state.clone();
        advance_auto_clippers(&mut state, false).unwrap();
        advance_auto_clippers(&mut state, true).unwrap();
        assert_eq!(state.pro, before.pro);
        assert_eq!(state.clock, before.clock);
        assert_eq!(state.rng_state_hex(), before.rng_state_hex());
        assert_eq!(state.pro.auto_clipper_rate.to_string(), "0");
        assert_eq!(
            state.pro.auto_clipper_production_accumulator.to_string(),
            "0"
        );

        let mut hidden = game();
        hidden.pro.auto_clippers = IntegralAmount::from_i128(1);
        let hidden_before = hidden.clone();
        assert_eq!(
            advance_auto_clippers(&mut hidden, true),
            Err(EconomyError::InvalidState)
        );
        assert_eq!(hidden.pro, hidden_before.pro);
        assert_eq!(hidden.rng_state_hex(), hidden_before.rng_state_hex());
    }
}
