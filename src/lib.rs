//! Authoritative game rules and the HTTP/process host.

pub mod api;
pub mod config;
pub mod game;
pub mod health;
pub mod persistence;
pub mod runtime;
pub mod snapshot;
pub mod startup;
pub mod view_sync;

mod view_broadcast;
