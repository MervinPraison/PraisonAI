//! Android's system back gesture, delivered to Rust.
//!
//! Tauri already installs an `OnBackPressedCallback` (`AppPlugin.kt`), but it
//! routes the press to *JavaScript plugin listeners* via `Plugin.trigger` --
//! a channel that reaches neither Tauri's event registry nor Rust. The shell's
//! arbitration (`shell::back::Gate` in the app) has to run in Rust, because
//! the webview's answer is fire-and-forget and only Rust can time it out. So
//! this plugin owns its own callback in Kotlin, ahead of Tauri's, and hands
//! each press to Rust over a [`tauri::ipc::Channel`].
//!
//! Two calls, one each way:
//!
//!  - Kotlin -> Rust: the user pressed back. Delivered to the `on_press`
//!    closure given to [`init`], **on the platform's UI thread** -- the closure
//!    must not block, and must not call [`BackGesture::fall_back`] directly.
//!  - Rust -> Kotlin: [`BackGesture::fall_back`]. The app declined the press,
//!    so the plugin disables its callback and re-dispatches, letting whatever
//!    is beneath it act: Tauri's own callback, then the system default, which
//!    on Android 12+ moves the task to the back rather than finishing the
//!    activity -- warm start survives.
//!
//! On iOS and desktop the plugin is inert: it registers nothing, `on_press`
//! never fires, and `fall_back` does nothing. iOS has no OS-level back, and an
//! iOS app must never terminate itself -- that is an App Review rejection and
//! reads to the user as a crash.

use std::{fmt, sync::Arc};

use tauri::{
    plugin::{Builder, TauriPlugin},
    AppHandle, Manager, Runtime,
};

/// The plugin name, as `tauri::plugin::Builder` and the ACL know it.
pub const PLUGIN_NAME: &str = "back-gesture";

/// What [`init`] is given: called once per press, on the platform's UI thread.
type OnPress<R> = Arc<dyn Fn(&AppHandle<R>) + Send + Sync>;

/// Java package of the Kotlin half. Must match `package` in
/// `android/src/main/java/ai/praison/mobile/backgesture/BackGesturePlugin.kt`;
/// a mismatch is a `ClassNotFoundException` at startup, not a build error.
#[cfg(target_os = "android")]
const PLUGIN_IDENTIFIER: &str = "ai.praison.mobile.backgesture";

/// The listener event the Kotlin side triggers. Must match `EVENT` there.
#[cfg(target_os = "android")]
const EVT_PRESSED: &str = "pressed";

/// Why a fall-back could not be handed to the platform.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    /// The Kotlin side rejected or could not be reached.
    Platform(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Platform(message) => write!(f, "back-gesture platform call failed: {message}"),
        }
    }
}

impl std::error::Error for Error {}

/// What the Kotlin `registerListener` command takes. The `Channel` serialises
/// to `__CHANNEL__:<id>` and Tauri's Kotlin deserialiser turns that back into
/// a `Channel` whose `send` lands in the Rust closure.
#[cfg(target_os = "android")]
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct RegisterListenerArgs<'a> {
    event: &'a str,
    handler: &'a tauri::ipc::Channel<serde_json::Value>,
}

/// The handle to the platform half, managed as Tauri state. Reach it with
/// [`BackGestureExt::back_gesture`].
pub struct BackGesture<R: Runtime> {
    #[cfg(target_os = "android")]
    handle: tauri::plugin::PluginHandle<R>,
    /// Held so the channel outlives setup. Tauri's registry keeps a clone too,
    /// but that is an implementation detail this crate should not lean on.
    #[cfg(target_os = "android")]
    _listener: tauri::ipc::Channel<serde_json::Value>,
    #[cfg(not(target_os = "android"))]
    _runtime: std::marker::PhantomData<fn() -> R>,
}

impl<R: Runtime> BackGesture<R> {
    /// Let the platform act on a press the app declined.
    ///
    /// On Android this blocks until the UI thread has re-dispatched the press,
    /// so it must be called from a thread that is not the UI thread -- never
    /// from inside the `on_press` closure. Off Android it returns `Ok(())`
    /// immediately and does nothing, on purpose; see the crate docs.
    pub fn fall_back(&self) -> Result<(), Error> {
        #[cfg(target_os = "android")]
        {
            self.handle
                .run_mobile_plugin::<()>("fallBack", ())
                .map_err(|e| Error::Platform(e.to_string()))?;
        }
        Ok(())
    }
}

/// `app.back_gesture()` on anything that is a `Manager`.
pub trait BackGestureExt<R: Runtime> {
    fn back_gesture(&self) -> &BackGesture<R>;
}

impl<R: Runtime, T: Manager<R>> BackGestureExt<R> for T {
    fn back_gesture(&self) -> &BackGesture<R> {
        self.state::<BackGesture<R>>().inner()
    }
}

/// Build the plugin. `on_press` runs once per system back press, on the
/// platform's UI thread; it must return quickly and must not block on the
/// platform.
pub fn init<R: Runtime>(
    on_press: impl Fn(&AppHandle<R>) + Send + Sync + 'static,
) -> TauriPlugin<R> {
    let on_press: OnPress<R> = Arc::new(on_press);

    Builder::new(PLUGIN_NAME)
        .setup(move |app, api| {
            #[cfg(target_os = "android")]
            let state: BackGesture<R> = {
                let handle = api.register_android_plugin(PLUGIN_IDENTIFIER, "BackGesturePlugin")?;

                let app_handle = app.clone();
                let on_press = on_press.clone();
                let listener = tauri::ipc::Channel::<serde_json::Value>::new(move |_press| {
                    on_press(&app_handle);
                    Ok(())
                });

                // The base `Plugin` class's own `registerListener` command --
                // the same one `addPluginListener` uses from JS -- with a
                // Rust-owned channel as the handler. This is the entire
                // Kotlin -> Rust path; there is no other supported one.
                handle.run_mobile_plugin::<()>(
                    "registerListener",
                    RegisterListenerArgs {
                        event: EVT_PRESSED,
                        handler: &listener,
                    },
                )?;

                BackGesture {
                    handle,
                    _listener: listener,
                }
            };

            #[cfg(not(target_os = "android"))]
            let state: BackGesture<R> = {
                // Nothing to register: no OS-level back on iOS, none on desktop.
                let _ = (&on_press, &api);
                BackGesture {
                    _runtime: std::marker::PhantomData,
                }
            };

            app.manage(state);
            Ok(())
        })
        .build()
}
