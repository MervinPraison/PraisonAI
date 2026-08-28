//! The four things the native shell tells the webview, and the one thing it asks.
//!
//! These names are a CONTRACT with `adapters/src/tauri/shell.ts`, which
//! subscribes to them by string. A rename on either side is silent: the
//! webview simply stops receiving an event and lays out as though the phone
//! had no notch, no keyboard and no lifecycle. `tests/contract.rs` asserts
//! each constant against a literal, and a Node test greps these out and
//! compares them to the TypeScript, so the seam fails CI rather than a device.
//!
//! One architectural fact governs all four, and it is the easiest thing here to
//! get wrong: the TypeScript subscribes via `plugin:event|listen`, which
//! registers in TAURI'S OWN event registry. Only `Emitter::emit` reaches it. A
//! Tauri mobile *plugin* calling `Plugin.trigger` reaches a completely separate
//! channel — nothing would fire, and there would be no error anywhere.

pub mod back;
pub mod lifecycle;

/// Safe-area insets changed, or something happened that means they should be
/// re-read. A payload with none of the four edges is legal and means exactly
/// "re-read the CSS yourself" — see `coerceInsets` in the TypeScript.
pub const EVT_SAFE_AREA: &str = "safe-area-changed";

/// Keyboard height in CSS pixels. `0` is a value, not an absence, and this
/// must fire THROUGH the show/hide transition rather than only at its ends —
/// otherwise the composer teleports while the keyboard slides.
pub const EVT_KEYBOARD: &str = "keyboard-height";

/// `active` | `inactive` | `background`. An unrecognised phase is dropped by
/// the TypeScript rather than defaulted, because defaulting to `active` would
/// resume the render loop while the app is actually suspended.
pub const EVT_LIFECYCLE: &str = "lifecycle";

/// The user pressed back. Carries no payload: the handler takes no argument.
pub const EVT_BACK: &str = "back-gesture";

/// What the webview calls to answer a back gesture.
pub const CMD_BACK_RESULT: &str = "back_gesture_result";
