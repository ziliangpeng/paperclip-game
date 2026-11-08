//! Integer logical time; no cadence uses floating-point seconds.

use super::amount::MAX_SAFE_JSON_INTEGER;
use std::error::Error;
use std::fmt;
use std::time::Duration;

pub const UPDATE_QUANTUM: Duration = Duration::from_millis(10);
pub const UPDATE_QUANTUM_NANOS: u128 = 10_000_000;
pub const COMBAT_QUANTUM_NANOS: u128 = 16_000_000;
const FAST_PHASE_TICKS: u8 = 10;
const SECOND_PHASE_TICKS: u8 = 100;
const SLOW_PHASE_TICKS: u16 = 250;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClockState {
    update_count: u64,
    fast_phase: u8,
    second_phase: u8,
    slow_phase: u16,
    combat_remainder_nanos: u32,
    combat_pulses: u64,
}

impl ClockState {
    pub fn fresh() -> Self {
        Self {
            update_count: 0,
            fast_phase: 0,
            second_phase: 0,
            slow_phase: 0,
            combat_remainder_nanos: 0,
            combat_pulses: 0,
        }
    }

    pub fn update_count(&self) -> u64 {
        self.update_count
    }

    pub fn fast_phase(&self) -> u8 {
        self.fast_phase
    }

    pub fn second_phase(&self) -> u8 {
        self.second_phase
    }

    pub fn slow_phase(&self) -> u16 {
        self.slow_phase
    }

    pub fn combat_remainder_nanos(&self) -> u32 {
        self.combat_remainder_nanos
    }

    pub fn combat_pulses(&self) -> u64 {
        self.combat_pulses
    }

    pub(crate) fn advance(&mut self) -> Result<TickCadence, ClockError> {
        let update_count = self
            .update_count
            .checked_add(1)
            .filter(|value| *value <= MAX_SAFE_JSON_INTEGER)
            .ok_or(ClockError::UpdateCounterLimit)?;
        let fast = self.fast_phase + 1;
        let second = self.second_phase + 1;
        let slow = self.slow_phase + 1;
        let fast_due = fast == FAST_PHASE_TICKS;
        let second_due = second == SECOND_PHASE_TICKS;
        let slow_due = slow == SLOW_PHASE_TICKS;
        let combat_total = u128::from(self.combat_remainder_nanos) + UPDATE_QUANTUM_NANOS;
        let combat_due = combat_total / COMBAT_QUANTUM_NANOS;
        let combat_pulses = self
            .combat_pulses
            .checked_add(combat_due as u64)
            .ok_or(ClockError::UpdateCounterLimit)?;

        self.update_count = update_count;
        self.fast_phase = if fast_due { 0 } else { fast };
        self.second_phase = if second_due { 0 } else { second };
        self.slow_phase = if slow_due { 0 } else { slow };
        self.combat_remainder_nanos = (combat_total % COMBAT_QUANTUM_NANOS) as u32;
        self.combat_pulses = combat_pulses;
        Ok(TickCadence {
            fast_due,
            second_due,
            slow_due,
            combat_due: combat_due as u8,
        })
    }
}

impl Default for ClockState {
    fn default() -> Self {
        Self::fresh()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct TickCadence {
    pub fast_due: bool,
    pub second_due: bool,
    pub slow_due: bool,
    pub combat_due: u8,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ClockError {
    UpdateCounterLimit,
}

impl fmt::Display for ClockError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UpdateCounterLimit => {
                formatter.write_str("logical update counter exhausted its safe range")
            }
        }
    }
}

impl Error for ClockError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fresh_cadence_state_is_at_its_root_values() {
        let clock = ClockState::fresh();
        assert_eq!(clock.update_count(), 0);
        assert_eq!(clock.fast_phase(), 0);
        assert_eq!(clock.second_phase(), 0);
        assert_eq!(clock.slow_phase(), 0);
        assert_eq!(clock.combat_remainder_nanos(), 0);
        assert_eq!(clock.combat_pulses(), 0);
    }

    #[test]
    fn cadence_boundaries_are_exact_integer_updates() {
        let mut clock = ClockState::fresh();
        let mut fast = 0;
        let mut second = 0;
        let mut slow = 0;
        for _ in 0..250 {
            let due = clock.advance().unwrap();
            fast += usize::from(due.fast_due);
            second += usize::from(due.second_due);
            slow += usize::from(due.slow_due);
        }
        assert_eq!((fast, second, slow), (25, 2, 1));
        assert_eq!(clock.update_count(), 250);
        assert_eq!(
            (clock.fast_phase(), clock.second_phase(), clock.slow_phase()),
            (0, 50, 0)
        );
        assert_eq!(clock.combat_pulses(), 156);
        assert_eq!(clock.combat_remainder_nanos(), 4_000_000);
    }

    #[test]
    fn combat_remainder_sequence_is_exact() {
        let mut clock = ClockState::fresh();
        let mut remainders = Vec::new();
        let mut due = Vec::new();
        for _ in 0..8 {
            due.push(clock.advance().unwrap().combat_due);
            remainders.push(clock.combat_remainder_nanos());
        }
        assert_eq!(
            remainders,
            [10, 4, 14, 8, 2, 12, 6, 0].map(|ms| ms * 1_000_000)
        );
        assert_eq!(due, [0, 1, 0, 1, 1, 0, 1, 1]);
        assert_eq!(clock.combat_pulses(), 5);
    }

    #[test]
    fn checked_update_exhaustion_does_not_mutate_or_wrap() {
        let mut clock = ClockState {
            update_count: MAX_SAFE_JSON_INTEGER,
            ..ClockState::fresh()
        };
        let before = clock.clone();
        assert_eq!(clock.advance(), Err(ClockError::UpdateCounterLimit));
        assert_eq!(clock, before);
    }
}
