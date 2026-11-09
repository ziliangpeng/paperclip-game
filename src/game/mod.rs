//! Shared exact game primitives and logical state.

pub mod amount;
pub mod clock;
pub(crate) mod conversion;
pub mod economy;
pub mod evaluator;
pub use conversion::ConversionError;
pub mod rng;
pub mod state;
