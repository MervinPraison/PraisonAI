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

pub mod secrets;
pub mod shell;
pub mod store;

use tauri::Manager;

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
        .setup(|app| {
            // The store's root, resolved ONCE at startup.
            //
            // `app_data_dir()` is the app container: on iOS
            // Library/Application Support inside the sandbox, which is backed
            // up and — unlike the WebKit data store `localStorage` lives in —
            // NOT evictable when the device runs low on space. That eviction is
            // the entire bug this exists to close: the user does nothing wrong
            // and their conversations are gone.
            //
            // A failure here is fatal ON PURPOSE. Booting with no store means
            // every chat write fails for the whole session while the crash
            // screen keeps promising the conversations are saved, and that is
            // a worse outcome than refusing to start with a message.
            //
            // It lives on `run`, not in `configure`, because `configure` is what
            // `tests/wiring.rs` builds on the mock runtime, where there is no
            // app container to resolve; the store commands themselves are in
            // `configure`'s `generate_handler!` so the webview can reach them.
            let dir = app
                .path()
                .app_data_dir()
                .map_err(|e| format!("no app data directory to store conversations in: {e}"))?
                .join(store::STORE_DIR);
            app.manage(store::StoreState(store::FileStore::new(dir)));
            Ok(())
        })
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
///
/// The five `store::storage_*` commands are registered here too: a command in
/// `store.rs` but missing from `generate_handler!` is unreachable, the invoke
/// rejects with "command not found", and only that one operation silently stops
/// working. `tools/storage-seam.test.mjs` asserts all five are present.
///
/// The four `secrets::secret_*` commands are here for the same reason, and so
/// is `tauri_plugin_secrets::init()` -- which is what puts the `SecretStore`
/// into managed state. Drop the plugin line and every command still compiles,
/// still registers, and panics on the first `state::<SecretStore>()`; drop a
/// command and the settings screen reports "Not set" for a key that is in the
/// keychain. `tools/secrets-seam.test.mjs` asserts both.
pub fn configure<R: tauri::Runtime>(builder: tauri::Builder<R>) -> tauri::Builder<R> {
    builder
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_back_gesture::init(commands::on_back_pressed))
        .plugin(tauri_plugin_secrets::init())
        .manage(commands::BackState::default())
        .manage(shell::LifecycleState::default())
        .invoke_handler(tauri::generate_handler![
            commands::back_gesture_result,
            store::storage_read,
            store::storage_write,
            store::storage_remove,
            store::storage_list_ids,
            store::storage_clear,
            secrets::secret_read,
            secrets::secret_write,
            secrets::secret_remove,
            secrets::secret_has
        ])
        .on_window_event(shell::on_window_event)
}

pub mod commands;
