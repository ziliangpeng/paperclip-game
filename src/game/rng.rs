//! Versioned deterministic game randomness with exact continuation state.

use rand_chacha::ChaCha20Rng;
use rand_core::{Rng, SeedableRng};
use std::error::Error;
use std::fmt;

const STATE_VERSION: u8 = 1;
const STATE_BYTES: usize = 1 + 32 + 8 + 16;
const STATE_HEX_BYTES: usize = STATE_BYTES * 2;
const MEANINGFUL_WORD_BITS: u32 = 68;

/// ChaCha20's output stream is the only source used by game decisions.
#[derive(Clone)]
pub struct GameRng {
    inner: ChaCha20Rng,
}

impl GameRng {
    pub(crate) fn from_entropy() -> Result<Self, getrandom::Error> {
        let mut seed = [0u8; 32];
        getrandom::fill(&mut seed)?;
        Ok(Self {
            inner: ChaCha20Rng::from_seed(seed),
        })
    }

    pub fn next_u32(&mut self) -> u32 {
        self.inner.next_u32()
    }

    pub fn next_u64(&mut self) -> u64 {
        self.inner.next_u64()
    }

    pub fn fill_bytes(&mut self, destination: &mut [u8]) {
        self.inner.fill_bytes(destination);
    }

    /// Export version 1: version byte, 32-byte seed, big-endian u64 stream,
    /// then big-endian u128 word position. Only the low 68 position bits are
    /// meaningful to `rand_chacha` 0.10; imports reject nonzero upper bits.
    pub fn export_hex(&self) -> String {
        let mut bytes = [0u8; STATE_BYTES];
        bytes[0] = STATE_VERSION;
        bytes[1..33].copy_from_slice(&self.inner.get_seed());
        bytes[33..41].copy_from_slice(&self.inner.get_stream().to_be_bytes());
        bytes[41..57].copy_from_slice(&self.inner.get_word_pos().to_be_bytes());
        encode_hex(&bytes)
    }

    pub fn import_hex(text: &str) -> Result<Self, RngStateError> {
        if text.len() != STATE_HEX_BYTES {
            return Err(RngStateError::InvalidEncoding);
        }
        if !text
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(RngStateError::InvalidEncoding);
        }
        let mut bytes = [0u8; STATE_BYTES];
        for (index, output) in bytes.iter_mut().enumerate() {
            *output = (hex_nibble(text.as_bytes()[index * 2])? << 4)
                | hex_nibble(text.as_bytes()[index * 2 + 1])?;
        }
        if bytes[0] != STATE_VERSION {
            return Err(RngStateError::UnsupportedVersion);
        }
        let seed: [u8; 32] = bytes[1..33]
            .try_into()
            .map_err(|_| RngStateError::InvalidEncoding)?;
        let stream = u64::from_be_bytes(
            bytes[33..41]
                .try_into()
                .map_err(|_| RngStateError::InvalidEncoding)?,
        );
        let word_position = u128::from_be_bytes(
            bytes[41..57]
                .try_into()
                .map_err(|_| RngStateError::InvalidEncoding)?,
        );
        if (word_position >> MEANINGFUL_WORD_BITS) != 0 {
            return Err(RngStateError::InvalidWordPosition);
        }
        let mut inner = ChaCha20Rng::from_seed(seed);
        inner.set_stream(stream);
        inner.set_word_pos(word_position);
        Ok(Self { inner })
    }

    #[cfg(test)]
    pub(crate) fn from_test_seed(seed: [u8; 32]) -> Self {
        Self {
            inner: ChaCha20Rng::from_seed(seed),
        }
    }
}

impl fmt::Debug for GameRng {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("GameRng")
            .field("format_version", &STATE_VERSION)
            .finish_non_exhaustive()
    }
}

fn encode_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(char::from(DIGITS[usize::from(byte >> 4)]));
        output.push(char::from(DIGITS[usize::from(byte & 0x0f)]));
    }
    output
}

fn hex_nibble(byte: u8) -> Result<u8, RngStateError> {
    match byte {
        b'0'..=b'9' => Ok(byte - b'0'),
        b'a'..=b'f' => Ok(byte - b'a' + 10),
        _ => Err(RngStateError::InvalidEncoding),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RngStateError {
    InvalidEncoding,
    UnsupportedVersion,
    InvalidWordPosition,
}

impl fmt::Display for RngStateError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidEncoding => formatter.write_str("invalid fixed-width lowercase RNG state"),
            Self::UnsupportedVersion => formatter.write_str("unsupported RNG state version"),
            Self::InvalidWordPosition => {
                formatter.write_str("RNG word position exceeds the ChaCha20 68-bit range")
            }
        }
    }
}

impl Error for RngStateError {}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    #[test]
    fn zero_seed_matches_the_backend_native_test_vector() {
        let mut rng = GameRng::from_test_seed([0u8; 32]);
        let expected = [
            0xade0b876, 0x903df1a0, 0xe56a5d40, 0x28bd8653, 0xb819d2bd, 0x1aed8da0, 0xccef36a8,
            0xc70d778b, 0x7c5941da, 0x8d485751, 0x3fe02477, 0x374ad8b8, 0xf4b8436a, 0x1ca11815,
            0x69b687c3, 0x8665eeb2,
        ];
        for expected_word in expected {
            assert_eq!(rng.next_u32(), expected_word);
        }
        assert_eq!(rng.inner.get_word_pos(), 16);
    }

    #[test]
    fn fixed_width_state_replays_whole_and_partial_blocks() {
        for prefix_words in [0, 1, 15, 16, 17, 63, 64, 65] {
            let mut uninterrupted = GameRng::from_test_seed([7u8; 32]);
            uninterrupted.inner.set_stream(91);
            for _ in 0..prefix_words {
                uninterrupted.next_u32();
            }
            let encoded = uninterrupted.export_hex();
            assert_eq!(encoded.len(), STATE_HEX_BYTES);
            assert!(encoded.bytes().all(|byte| !byte.is_ascii_uppercase()));
            let mut restored = GameRng::import_hex(&encoded).unwrap();
            assert_eq!(restored.export_hex(), encoded);
            for _ in 0..200 {
                assert_eq!(restored.next_u32(), uninterrupted.next_u32());
            }
            for _ in 0..100 {
                assert_eq!(restored.next_u64(), uninterrupted.next_u64());
            }
        }
    }

    #[test]
    fn mixed_word_and_byte_draws_continue_exactly() {
        let mut original = GameRng::from_test_seed([42u8; 32]);
        original.next_u32();
        original.next_u64();
        let mut original_bytes = [0u8; 13];
        original.fill_bytes(&mut original_bytes);
        let mut restored = GameRng::import_hex(&original.export_hex()).unwrap();
        for _ in 0..33 {
            assert_eq!(restored.next_u64(), original.next_u64());
        }
        let mut a = [0u8; 29];
        let mut b = [0u8; 29];
        restored.fill_bytes(&mut a);
        original.fill_bytes(&mut b);
        assert_eq!(a, b);
    }

    #[test]
    fn negative_table_rejects_ambiguous_or_unsupported_rng_state() {
        let state = GameRng::from_test_seed([0xabu8; 32]).export_hex();
        let mut version = state.clone();
        version.replace_range(0..2, "02");
        let mut bytes = [0u8; STATE_BYTES];
        bytes[0] = STATE_VERSION;
        bytes[41..57].copy_from_slice(&(1u128 << MEANINGFUL_WORD_BITS).to_be_bytes());
        let bad_position = encode_hex(&bytes);
        for (label, input, expected) in [
            (
                "uppercase",
                state.to_uppercase(),
                RngStateError::InvalidEncoding,
            ),
            ("empty", String::new(), RngStateError::InvalidEncoding),
            ("short", "00".to_string(), RngStateError::InvalidEncoding),
            ("nonhex", "xyz".to_string(), RngStateError::InvalidEncoding),
            (
                "version only",
                "01".to_string(),
                RngStateError::InvalidEncoding,
            ),
            (
                "unknown version",
                version,
                RngStateError::UnsupportedVersion,
            ),
            (
                "68-bit overflow",
                bad_position,
                RngStateError::InvalidWordPosition,
            ),
        ] {
            let error = match GameRng::import_hex(&input) {
                Ok(_) => panic!("accepted bad RNG state: {label}"),
                Err(error) => error,
            };
            assert_eq!(error, expected, "wrong category for {label}");
            eprintln!("negative RNG state case {label}: {expected:?}");
        }
    }

    #[test]
    fn native_many_block_replay_and_performance_probe() {
        let started = Instant::now();
        let mut original = GameRng::from_test_seed([0x5au8; 32]);
        for _ in 0..100_000 {
            original.next_u64();
        }
        original.next_u32();
        let mut restored = GameRng::import_hex(&original.export_hex()).unwrap();
        for _ in 0..128 {
            assert_eq!(restored.next_u64(), original.next_u64());
        }
        eprintln!(
            "RNG native probe: 100000 next_u64 calls, one partial word, 128 replay checks in {:?}",
            started.elapsed()
        );
    }
}
