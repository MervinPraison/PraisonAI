//! The back gesture, end to end: the press comes in from the platform, the
//! webview is asked, and its answer — or its silence — decides.

use std::{sync::Mutex, thread, time::Duration};

use tauri::{AppHandle, Emitter, Manager, Runtime};
use tauri_plugin_back_gesture::BackGestureExt;

use crate::shell::{
    back::{Action, Gate, ANSWER_TIMEOUT_MS},
    EVT_BACK,
};

/// The back gate, behind a mutex because a press arrives on the platform's
/// UI thread, the answer on Tauri's, and the timeout on its own.
#[derive(Default)]
pub struct BackState(pub Mutex<Gate>);

/// Run one gate transition. A poisoned mutex means a panic while holding it,
/// and doing nothing is right: falling back on a corrupted gate could exit
/// the app for a press the webview already handled.
fn transition<R: Runtime>(app: &AppHandle<R>, step: impl FnOnce(&mut Gate) -> Action) -> Action {
    let state = app.state::<BackState>();
    let action = match state.0.lock() {
        Ok(mut gate) => step(&mut gate),
        Err(_) => Action::Ignore,
    };
    action
}

/// The platform's system back gesture. Handed to `tauri_plugin_back_gesture`
/// in `lib.rs`; on Android it runs on the UI thread, so nothing here blocks.
///
/// Emitting `back-gesture` is what the TypeScript's `onBackGesture` stack is
/// waiting for; it answers with `back_gesture_result`. If the emit fails, or
/// the webview never answers, the watchdog falls back — silence must not be a
/// dead back button.
pub fn on_back_pressed<R: Runtime>(app: &AppHandle<R>) {
    match transition(app, Gate::press) {
        Action::Ask => {
            if let Err(e) = app.emit(EVT_BACK, ()) {
                log::warn!("back: could not emit {EVT_BACK}: {e}");
            }
            watchdog(app.clone());
        }
        Action::Drop => log::debug!("back: a press is already pending; dropped"),
        // `press` never returns these. Handled rather than `unreachable!()`
        // because a panic on the UI thread is a crash, and acting on the
        // gate's word is always safe.
        Action::FallBack => fall_back(app),
        Action::Ignore => {}
    }
}

/// The answer may never come — `bridge.invoke` swallows every rejection, so a
/// bundle that failed to load is indistinguishable from one still deciding.
fn watchdog<R: Runtime>(app: AppHandle<R>) {
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(ANSWER_TIMEOUT_MS));
        if transition(&app, Gate::timed_out) == Action::FallBack {
            log::debug!("back: no answer within {ANSWER_TIMEOUT_MS}ms; falling back");
            fall_back(&app);
        }
    });
}

/// The webview's answer to a back gesture.
///
/// Answering at all is mandatory on the TypeScript side, and it is fire and
/// forget, so this may never be called for a given press; the watchdog above
/// covers that, and `Gate::answered` ignores an answer that arrives after it.
#[tauri::command]
pub fn back_gesture_result<R: Runtime>(app: AppHandle<R>, handled: bool) {
    if transition(&app, |gate| gate.answered(handled)) == Action::FallBack {
        fall_back(&app);
    }
}

/// Let the platform act on a press the webview declined.
///
/// On Android the plugin re-dispatches the press with its own callback
/// disabled, so the SYSTEM default runs — on 12+ that moves the task to the
/// back rather than destroying the activity, which preserves warm start. That
/// call blocks until the UI thread has done it, and this function has callers
/// on the UI thread (via the plugin) and on Tauri's main thread (the command),
/// so it always runs on its own thread. On iOS and desktop the plugin does
/// nothing, by design: see its crate docs.
fn fall_back<R: Runtime>(app: &AppHandle<R>) {
    let app = app.clone();
    thread::spawn(move || {
        if let Err(e) = app.back_gesture().fall_back() {
            log::warn!("back: the platform did not take the press: {e}");
        }
    });
}
