//! Pure core for the PraisonAI desktop shell.
//!
//! Every module here is free of real I/O: filesystem and process access arrive
//! through injected traits so the logic is testable without a Mac, a signing
//! certificate, a network, or an installed Python. The Tauri layer is a thin
//! adapter over this crate.

pub mod venv_resolve;
pub mod health;
pub mod readiness;
pub mod adopt;
pub mod coalesce;
pub mod lockfile;
pub mod verify;
pub mod port_announce;
pub mod supervisor;
