//! Shared exact game primitives and logical state.

pub mod amount;
pub mod clock;
pub(crate) mod conversion;
pub mod economy;
pub mod evaluator;
pub use conversion::ConversionError;
pub mod rng;
pub mod state;

#[cfg(test)]
mod m1_playable_integration_tests {
    use super::amount::{Amount, NonNegativeAmount};
    use super::conversion::{ConversionError, convert_one_wire};
    use super::economy;
    use super::rng::GameRng;
    use super::state::GameState;
    use num_bigint::BigInt;

    fn positive(value: &str) -> NonNegativeAmount {
        Amount::parse(value).unwrap().nonnegative().unwrap()
    }

    fn advance(state: &mut GameState) {
        let cadence = state.clock.advance().unwrap();
        if cadence.fast_due {
            economy::advance_fast_phase(state).unwrap();
            economy::observe_auto_clipper_reveal(&mut state.pro);
        }
        economy::advance_auto_clippers(state, cadence.second_due).unwrap();
    }

    fn advance_until(state: &mut GameState, predicate: impl Fn(&GameState) -> bool, label: &str) {
        for _ in 0..20_000 {
            if predicate(state) {
                return;
            }
            advance(state);
        }
        panic!(
            "bounded legal M1 sequence did not reach {label}: ticks={}, Funds={}, income={}, lifetime={}, Unsold={}, Wire={}, Price={}, Demand={}, producers={}",
            state.clock.update_count(),
            state.pro.funds,
            state.pro.income,
            state.pro.lifetime_clips,
            state.pro.unsold_clips,
            state.pro.wire,
            state.pro.price_per_clip,
            state.pro.demand,
            state.pro.auto_clippers,
        );
    }

    fn make_available_whole_wire(state: &mut GameState) -> u64 {
        let available = state.pro.wire.amount().mantissa() / Amount::from_i128(1).mantissa();
        let mut made = 0_u64;
        while BigInt::from(made) < available {
            convert_one_wire(&mut state.pro).expect("whole available Wire makes one clip");
            made += 1;
        }
        made
    }

    fn existing_inventory_can_fund(state: &GameState, target: &Amount) -> bool {
        // A conservative test-driver policy only; it never mutates state or
        // substitutes for observed sale receipts. At the working cent price,
        // exact current-price liquidation determines whether another spool is needed.
        let unit_amount = Amount::from_i128(1);
        let unit = unit_amount.mantissa();
        let potential = state.pro.funds.mantissa()
            + (state.pro.unsold_clips.amount().mantissa() * state.pro.price_per_clip.mantissa())
                / unit;
        potential >= target.mantissa().clone()
    }

    fn assert_conserved(state: &GameState) {
        let pro = &state.pro;
        assert_eq!(
            pro.unsold_clips.add_exact(&pro.clips_sold),
            pro.lifetime_clips
        );
        assert_eq!(pro.unused_clips, pro.lifetime_clips);
    }

    #[test]
    fn legal_m1_entry_to_exit_prefix_preserves_conversion_receipts_and_conservation() {
        let mut initial = GameState::fresh(GameRng::from_test_seed([0x17; 32]));

        // ENG-WIRE-MANUAL-FLOOR is a separate pure fixture. It never substitutes
        // for the real online browser path below or creates a public amount input.
        let mut below_one = initial.clone();
        below_one.pro.wire = positive("0.999");
        let rejected_before = below_one.clone();
        assert_eq!(
            convert_one_wire(&mut below_one.pro),
            Err(ConversionError::InsufficientWire)
        );
        assert_eq!(below_one.pro, rejected_before.pro);
        assert_eq!(below_one.clock, rejected_before.clock);
        assert_eq!(below_one.rng_state_hex(), rejected_before.rng_state_hex());

        let mut exactly_one = initial.clone();
        exactly_one.pro.wire = NonNegativeAmount::from_i128(1).unwrap();
        assert_eq!(convert_one_wire(&mut exactly_one.pro), Ok(positive("1")));
        assert_eq!(exactly_one.pro.wire, NonNegativeAmount::zero());
        for ledger in [
            &exactly_one.pro.lifetime_clips,
            &exactly_one.pro.unsold_clips,
            &exactly_one.pro.unused_clips,
        ] {
            assert_eq!(ledger, &positive("1"));
        }

        // E2E-M1-DECLARED-PLAYABLE-EXIT begins at the exact canonical entry.
        assert_eq!(initial.pro.lifetime_clips, NonNegativeAmount::zero());
        assert_eq!(initial.pro.unsold_clips, NonNegativeAmount::zero());
        assert_eq!(initial.pro.unused_clips, NonNegativeAmount::zero());
        assert_eq!(initial.pro.funds, Amount::zero());
        assert_eq!(initial.pro.wire, positive("1000"));
        assert_eq!(initial.pro.wire_spool_length, positive("1000"));
        assert_eq!(initial.pro.wire_quote, Amount::from_i128(20));
        assert_eq!(initial.pro.price_per_clip.to_string(), "0.25");
        assert_eq!(initial.pro.marketing_level.to_string(), "1");
        assert_eq!(initial.pro.marketing_cost().unwrap().to_string(), "100");
        assert!(!initial.pro.auto_clipper_revealed);
        assert_eq!(initial.pro.auto_clippers.to_string(), "0");
        assert_eq!(initial.pro.auto_clipper_cost.to_string(), "5");
        assert!(initial.pro.computing_hidden && initial.pro.projects_hidden);

        // Every clip is a legal individual Make; no pre-reveal Wire or Marketing buy.
        for expected in 1..=1_000_i128 {
            assert_eq!(convert_one_wire(&mut initial.pro), Ok(positive("1")));
            assert_eq!(initial.pro.lifetime_clips, positive(&expected.to_string()));
        }
        assert_eq!(initial.pro.wire, NonNegativeAmount::zero());
        assert_conserved(&initial);
        assert_eq!(initial.pro.wire_purchase_count.get(), 0);
        assert_eq!(initial.pro.marketing_level.to_string(), "1");

        // Legal price controls accelerate the bounded seeded-sales wait. All
        // revenue still comes from actual fast-phase stochastic opportunities.
        for _ in 0..21 {
            economy::lower_price(&mut initial.pro).unwrap();
        }
        assert_eq!(initial.pro.price_per_clip.to_string(), "0.04");
        advance_until(
            &mut initial,
            |state| state.pro.auto_clipper_revealed,
            "first sale-funded reveal",
        );
        let first_reveal_funds = initial.pro.funds.clone();
        assert!(first_reveal_funds >= Amount::from_i128(5));
        assert!(initial.pro.clips_sold.amount() > &Amount::zero());
        assert!(initial.pro.income > Amount::zero());
        assert_eq!(initial.pro.auto_clipper_cost.to_string(), "5");
        assert_eq!(initial.pro.wire_purchase_count.get(), 0);
        assert_eq!(initial.pro.marketing_level.to_string(), "1");

        let first_charge = initial.pro.auto_clipper_cost.clone();
        let funds_before_first = initial.pro.funds.clone();
        economy::buy_auto_clipper(&mut initial.pro).unwrap();
        assert_eq!(first_charge, Amount::from_i128(5));
        assert_eq!(
            initial.pro.funds,
            &funds_before_first - &Amount::from_i128(5)
        );
        assert_eq!(initial.pro.auto_clippers.to_string(), "1");
        assert_eq!(initial.pro.auto_clipper_cost.to_string(), "6.1");

        // The rejection is a command no-op, not a source of Funds or inventory.
        assert!(initial.pro.funds < initial.pro.auto_clipper_cost);
        let rejected = initial.clone();
        assert_eq!(
            economy::buy_auto_clipper(&mut initial.pro),
            Err(economy::EconomyError::InsufficientFunds)
        );
        assert_eq!(initial.pro, rejected.pro);
        assert_eq!(initial.clock, rejected.clock);
        assert_eq!(initial.rng_state_hex(), rejected.rng_state_hex());

        advance_until(
            &mut initial,
            |state| state.pro.funds >= Amount::parse("6.1").unwrap(),
            "successor funding",
        );
        let second_charge = initial.pro.auto_clipper_cost.clone();
        let funds_before_second = initial.pro.funds.clone();
        economy::buy_auto_clipper(&mut initial.pro).unwrap();
        assert_eq!(second_charge.to_string(), "6.1");
        assert_eq!(initial.pro.funds, &funds_before_second - &second_charge);
        assert_eq!(initial.pro.auto_clippers.to_string(), "2");
        assert_eq!(initial.pro.auto_clipper_cost.to_string(), "6.21");
        assert!(initial.pro.auto_clipper_revealed);

        // Required post-reveal Price business action; no tick is inserted between
        // this lower/raise pair, so the exact working price is restored.
        economy::lower_price(&mut initial.pro).unwrap();
        assert_eq!(initial.pro.price_per_clip.to_string(), "0.03");
        economy::raise_price(&mut initial.pro).unwrap();
        assert_eq!(initial.pro.price_per_clip.to_string(), "0.04");

        advance_until(
            &mut initial,
            |state| state.pro.funds >= Amount::from_i128(26),
            "Wire funding",
        );
        let funds_before_wire = initial.pro.funds.clone();
        let quote = initial.pro.wire_quote.clone();
        let base = initial.pro.wire_base_price.clone();
        let purchases = initial.pro.wire_purchase_count.get();
        economy::buy_wire(&mut initial.pro).unwrap();
        assert_eq!(initial.pro.funds, &funds_before_wire - &quote);
        assert_eq!(initial.pro.wire, positive("1000"));
        assert_eq!(initial.pro.wire_purchase_count.get(), purchases + 1);
        assert_eq!(initial.pro.wire_inactivity_ticks.get(), 0);
        assert_eq!(
            initial.pro.wire_base_price,
            &base + &Amount::parse("0.05").unwrap()
        );

        // Two 100-tick windows preserve the exact current-second phase. The
        // second window guarantees a latest complete second owned by producers,
        // rather than inventing an integral rate for an initially partial window.
        let clips_before = initial.pro.lifetime_clips.clone();
        let unused_before = initial.pro.unused_clips.clone();
        let wire_before = initial.pro.wire.clone();
        for _ in 0..200 {
            advance(&mut initial);
        }
        assert_eq!(
            initial.pro.lifetime_clips,
            clips_before.add_exact(&positive("4"))
        );
        assert_eq!(
            initial.pro.unused_clips,
            unused_before.add_exact(&positive("4"))
        );
        assert_eq!(
            initial.pro.wire,
            wire_before.checked_sub(&positive("4")).unwrap()
        );
        assert_eq!(initial.pro.auto_clipper_rate, positive("2"));
        assert_conserved(&initial);

        // Continue only through legal Make/sale/current-quote procurement. The
        // bounded test cannot assign the missing Funds or assume another spool is free.
        let mut procurement_rounds = 0_u64;
        while initial.pro.funds < Amount::from_i128(100) {
            procurement_rounds += 1;
            assert!(
                procurement_rounds <= 12,
                "bounded M1 Marketing procurement: Funds={}, income={}, lifetime={}, Unsold={}, Wire={}, quote={}, base={}",
                initial.pro.funds,
                initial.pro.income,
                initial.pro.lifetime_clips,
                initial.pro.unsold_clips,
                initial.pro.wire,
                initial.pro.wire_quote,
                initial.pro.wire_base_price,
            );
            make_available_whole_wire(&mut initial);
            assert_conserved(&initial);
            let inventory_can_fund = existing_inventory_can_fund(&initial, &Amount::from_i128(100));
            advance_until(
                &mut initial,
                |state| {
                    state.pro.funds >= Amount::from_i128(100)
                        || (!inventory_can_fund
                            && state.pro.funds >= &state.pro.wire_quote + &Amount::from_i128(13))
                },
                "sale-funded Marketing procurement",
            );
            if initial.pro.funds < Amount::from_i128(100) {
                economy::buy_wire(&mut initial.pro).expect("current affordable Wire quote");
            }
        }
        let funds_before_marketing = initial.pro.funds.clone();
        economy::buy_marketing(&mut initial.pro).unwrap();
        assert_eq!(
            initial.pro.funds,
            &funds_before_marketing - &Amount::from_i128(100)
        );
        assert_eq!(initial.pro.marketing_level.to_string(), "2");
        assert_eq!(initial.pro.marketing_cost().unwrap().to_string(), "200");
        assert!(initial.pro.auto_clipper_revealed);
        assert_eq!(initial.pro.auto_clipper_cost.to_string(), "6.21");
        assert_conserved(&initial);

        // This is the supported M1 prefix, not the later projects/space/ending trace.
        assert_eq!(initial.pro.trust.to_string(), "2");
        assert_eq!(initial.pro.processors.to_string(), "1");
        assert_eq!(initial.pro.memory.to_string(), "1");
        assert!(initial.pro.computing_hidden && initial.pro.projects_hidden);
        eprintln!(
            "E2E-M1-DECLARED-PLAYABLE-EXIT pure prefix: reveal Funds={}, charges 5/6.1, Wire quote={}, automatic 4 in 200 ticks / complete-second rate 2, lifetime={}, sold={}, income={}, Marketing level 2; M2/full phase not claimed",
            first_reveal_funds,
            quote,
            initial.pro.lifetime_clips,
            initial.pro.clips_sold,
            initial.pro.income
        );
    }
}
