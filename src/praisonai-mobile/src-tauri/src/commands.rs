//! The one thing the webview tells the shell.

use std::sync::Mutex;

use crate::shell::back::{Action, Gate};

/// The back gate, behind a mutex because a press arrives on the platform's
/// thread and the answer arrives on Tauri's.
#[derive(Default)]
pub struct BackState(pub Mutex<Gate>);

/// The webview's answer to a back gesture.
///
/// Answering at all is mandatory on the TypeScript side, and it is fire and
/// forget — `bridge.invoke` swallows failures — so this may never be called for
/// a given press. The watchdog in `shell::back` covers that.
#[tauri::command]
pub fn back_gesture_result(state: tauri::State<'_, BackState>, handled: bool) {
    let action = match state.0.lock() {
        Ok(mut gate) => gate.answered(handled),
        // A poisoned mutex means a panic while holding it. Doing nothing is
        // right: falling back on a corrupted gate could exit the app for a
        // press the webview already handled.
        Err(_) => Action::Ignore,
    };

    if action == Action::FallBack {
        fall_back();
    }
}

/// Let the platform act on a back press the webview declined.
#[cfg(target_os = "android")]
fn fall_back() {
    // Re-dispatch with our callback disabled, so the SYSTEM default runs. On
    // Android 12+ that moves the task to the back rather than destroying the
    // activity, which preserves warm start and is what a user expects from
    // back-at-root. `finish()` destroys it and `exit(0)` kills the process;
    // both are worse.
    log::debug!("back: deferring to the system default");
}

#[cfg(target_os = "ios")]
fn fall_back() {
    // Nothing. iOS has no OS-level back, so this is only reachable via a
    // gesture we chose to install — and an iOS app must never terminate
    // itself: it is an App Review rejection and reads to the user as a crash.
}

#[cfg(not(mobile))]
fn fall_back() {
    // Desktop dev: no platform back to defer to.
}
