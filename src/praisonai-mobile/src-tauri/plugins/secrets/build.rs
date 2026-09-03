// No JS-facing commands: the webview never talks to this plugin. It reaches
// the store through the app's own `secret_*` commands in
// `src-tauri/src/secrets.rs`, which is where the slot allowlist lives -- so
// there is nothing here for a capability to grant, and naming a command that
// does not exist would fail the ACL build.
const COMMANDS: &[&str] = &[];

fn main() {
    // `android_path` is what gets android/ compiled into the APK: on an android
    // target the tauri-plugin build copies the tauri-api into android/.tauri and
    // emits `cargo:android_library_path`, which tauri-build in the app turns
    // into a Gradle `include`. Off android it only sets the `mobile`/`desktop`
    // cfg aliases this crate's `#[cfg]`s rely on.
    //
    // There is deliberately no `ios_path`. The Apple half is Rust calling the
    // Security framework directly (see src/lib.rs), so there is no Swift
    // package to link -- which is also why the iOS store is testable on a
    // laptop and the Android one is not.
    tauri_plugin::Builder::new(COMMANDS)
        .android_path("android")
        .build();
}
