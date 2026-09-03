// No JS-facing commands: the webview never talks to this plugin. The press
// reaches Rust over a Channel and Rust answers the webview through Tauri's own
// event registry, so there is nothing for a capability to grant.
const COMMANDS: &[&str] = &[];

fn main() {
    // `android_path` is what gets android/ compiled into the APK: on an
    // android target the tauri-plugin build copies the tauri-api into
    // android/.tauri and emits `cargo:android_library_path`, which tauri-build
    // in the app turns into a Gradle `include`. Off android it only sets the
    // `mobile`/`desktop` cfg aliases this crate's `#[cfg]`s rely on.
    tauri_plugin::Builder::new(COMMANDS)
        .android_path("android")
        .build();
}
