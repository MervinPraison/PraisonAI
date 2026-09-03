//! The PraisonAI mobile shell.
//!
//! Everything the app actually does lives in the webview. This crate exists to
//! tell it four things the browser cannot know — the safe-area insets, the
//! keyboard height, the lifecycle phase, and that the user pressed back — and
//! to act on the one answer it sends back.
//!
//! The decisions are in `shell::back` and `shell::lifecycle`, both pure and
//! both tested without a device. What is here is the Tauri wiring, and what
//! each piece of it emits:
//!
//!  - `shell::on_window_event` — `lifecycle` on suspend/resume/focus, and
//!    `safe-area-changed` on resize and scale change.
//!  - `tauri_plugin_back_gesture` + `commands::on_back_pressed` — `back-gesture`
//!    on Android's system back, answered through `back_gesture_result`.
//!  - `keyboard-height` — NOT emitted by anything here. The TypeScript reads
//!    `visualViewport`, which WKWebView and Android WebView both implement,
//!    and treats a native event as an override if one ever arrives.
//!
//! What is honestly not provided: an iOS edge-swipe back (`ShellPort` mentions
//! one; nothing installs the gesture), and the haptics/share plugins the
//! bridge speaks to — those invokes reject and the bridge degrades.

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
    configure(tauri::Builder::default())
        .run(tauri::generate_context!())
        .expect("error while running the PraisonAI mobile shell");
}

/// Every piece of wiring the shell needs, applied to a builder.
///
/// Split out of [`run`] so a test can build the SAME app on Tauri's mock
/// runtime. `run` itself is untestable — `generate_context!` wants a built
/// webview bundle, and `.run()` wants the main thread and never returns — and
/// this chain is precisely where a deletion is SILENT. Drop the
/// `LifecycleState` line and `on_window_event` still runs, still finds no
/// state, and drops every phase with a `log::warn!` no phone displays; drop
/// the `on_window_event` line and nothing at all is emitted. Neither shows up
/// as a failure anywhere except on a device, which is why
/// `tests/wiring.rs` builds this and asserts on the result.
pub fn configure<R: tauri::Runtime>(builder: tauri::Builder<R>) -> tauri::Builder<R> {
    builder
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_back_gesture::init(commands::on_back_pressed))
        .manage(commands::BackState::default())
        .manage(shell::LifecycleState::default())
        .invoke_handler(tauri::generate_handler![commands::back_gesture_result])
        .on_window_event(shell::on_window_event)
}

pub mod commands;
