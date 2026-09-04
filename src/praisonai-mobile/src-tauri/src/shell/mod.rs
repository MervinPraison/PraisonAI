//! The four things the native shell tells the webview, and the two it is told.
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
//! channel — nothing would fire, and there would be no error anywhere. That is
//! exactly why the back gesture goes Kotlin → Channel → Rust → `emit` rather
//! than Kotlin → webview.

use std::sync::{Mutex, PoisonError};

use tauri::{Emitter, Manager, Runtime, Window, WindowEvent};

pub mod back;
pub mod lifecycle;

/// Safe-area insets changed, or something happened that means they should be
/// re-read. A payload with none of the four edges is legal and means exactly
/// "re-read the CSS yourself" — see `coerceInsets` in the TypeScript.
pub const EVT_SAFE_AREA: &str = "safe-area-changed";

/// Keyboard height in CSS pixels. `0` is a value, not an absence, and this
/// must fire THROUGH the show/hide transition rather than only at its ends —
/// otherwise the composer teleports while the keyboard slides.
///
/// Nothing native emits this today. The TypeScript reads `visualViewport`,
/// which fires through the transition on both WebViews; the constant stays so
/// a native source can take over without touching the contract.
pub const EVT_KEYBOARD: &str = "keyboard-height";

/// `active` | `inactive` | `background`. An unrecognised phase is dropped by
/// the TypeScript rather than defaulted, because defaulting to `active` would
/// resume the render loop while the app is actually suspended.
pub const EVT_LIFECYCLE: &str = "lifecycle";

/// The user pressed back. Carries no payload: the handler takes no argument.
pub const EVT_BACK: &str = "back-gesture";

/// What the webview calls to answer a back gesture.
pub const CMD_BACK_RESULT: &str = "back_gesture_result";

/// What the webview calls whenever its route stack changes, to say whether it
/// could take the NEXT back press.
///
/// Out of band on purpose. The answer to a press cannot be waited for -- the
/// round trip was measured at 0.7 s and then 5.4 s on the same device -- so the
/// watchdog decides from this standing declaration instead of from silence.
/// See `shell::back` for what each value means when the answer never comes.
pub const CMD_BACK_CAN_GO_BACK: &str = "back_gesture_can_go_back";

/// The lifecycle tracker, managed as Tauri state so `on_window_event` — a
/// plain `Fn` with no captures — can reach it through the window.
#[derive(Debug, Default)]
pub struct LifecycleState(pub Mutex<lifecycle::Tracker>);

/// Translate a Tauri window event into the shell events the webview listens
/// for. Installed with `Builder::on_window_event` in `lib.rs`.
///
/// Emits are best-effort: an emit fails only when there is no webview to
/// deliver to, and there is nothing better to do about that than log it.
pub fn on_window_event<R: Runtime>(window: &Window<R>, event: &WindowEvent) {
    if let WindowEvent::Resized(_) | WindowEvent::ScaleFactorChanged { .. } = event {
        // Deliberately an EMPTY payload. Tauri does not expose the insets and
        // this crate is not going to guess them; the TypeScript's
        // `coerceInsets` treats a payload with no edges as "re-read the CSS
        // env() variables", which the WebView has already recomputed by the
        // time the resize reaches Rust. Sending zeros instead would be a lie
        // the composer would lay out against.
        if let Err(e) = window.emit(EVT_SAFE_AREA, serde_json::json!({})) {
            log::warn!("shell: could not emit {EVT_SAFE_AREA}: {e}");
        }
    }

    let Some(name) = lifecycle::window_event_name(event) else {
        return;
    };
    // `try_state`, not `state`: a missing manage() is a wiring mistake in
    // lib.rs, and a window event is the wrong place to panic about it.
    let Some(state) = window.try_state::<LifecycleState>() else {
        log::warn!("shell: LifecycleState is not managed; {name} dropped");
        return;
    };
    let phase = state
        .0
        .lock()
        .unwrap_or_else(PoisonError::into_inner)
        .observe(name);
    if let Some(phase) = phase {
        if let Err(e) = window.emit(EVT_LIFECYCLE, phase) {
            log::warn!("shell: could not emit {EVT_LIFECYCLE}={phase}: {e}");
        }
    }
}
