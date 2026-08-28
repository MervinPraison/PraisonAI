//! The PraisonAI mobile shell.
//!
//! Everything the app actually does lives in the webview. This crate exists to
//! tell it four things the browser cannot know — the safe-area insets, the
//! keyboard height, the lifecycle phase, and that the user pressed back — and
//! to act on the one answer it sends back.
//!
//! The decisions are in `shell::back` and `shell::lifecycle`, both pure and
//! both tested without a device. What is here is the Tauri wiring.

pub mod shell;

/// The single entry point for all three platforms.
///
/// `#[cfg_attr(mobile, tauri::mobile_entry_point)]` expands to
/// `android_binding!(...)` on Android — which generates the JNI symbol
/// `MainActivity`'s `System.loadLibrary` resolves against — and to a
/// `#[no_mangle] pub extern "C" fn start_app()` on iOS, which the CLI looks for
/// by that exact name. So this function must keep the attribute and must not be
/// renamed to something the macro cannot wrap.
///
/// Both are wrapped in `catch_unwind`, which is why the release profile does
/// not set `panic = "abort"`: unwinding across the JNI/ObjC boundary is
/// undefined behaviour, and aborting with no message on a phone is a crash
/// nobody can read.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![commands::back_gesture_result])
        .manage(commands::BackState::default())
        .on_window_event(|_window, _event| {
            // Lifecycle translation lands here. `shell::lifecycle::phase_for`
            // holds the mapping and the reasoning; this is the one line that
            // would emit it, and it is left unwired until the mobile targets
            // are initialised so there is no dead `emit` on desktop.
        })
        .run(tauri::generate_context!())
        .expect("error while running the PraisonAI mobile shell");
}

pub mod commands;
