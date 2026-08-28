//! The seam with `adapters/src/tauri/shell.ts`.
//!
//! These strings are how the webview subscribes. A rename on either side is
//! SILENT: the webview simply stops receiving an event, and the app lays out
//! as though the phone had no notch, no keyboard and no lifecycle. Nothing
//! throws, so nothing is reported.

use praisonai_mobile_lib::shell::{CMD_BACK_RESULT, EVT_BACK, EVT_KEYBOARD, EVT_LIFECYCLE, EVT_SAFE_AREA};

#[test]
fn event_names_match_the_typescript_adapter() {
    // Literals on purpose. Comparing a constant to itself proves nothing;
    // these are the exact strings in adapters/src/tauri/shell.ts.
    assert_eq!(EVT_SAFE_AREA, "safe-area-changed");
    assert_eq!(EVT_KEYBOARD, "keyboard-height");
    assert_eq!(EVT_LIFECYCLE, "lifecycle");
    assert_eq!(EVT_BACK, "back-gesture");
}

#[test]
fn the_command_name_matches() {
    assert_eq!(CMD_BACK_RESULT, "back_gesture_result");
}

#[test]
fn suspension_maps_to_background_so_the_flush_runs() {
    // Tauri gives two states and ShellPort declares three. Suspended is
    // semantically "inactive", but boot.ts only flushes on "background" -- and
    // on iOS the app can be killed while suspended with no further callback,
    // so mapping to inactive loses the transcript every time.
    use praisonai_mobile_lib::shell::lifecycle::phase_for;
    assert_eq!(phase_for("suspended"), Some("background"));
    assert_eq!(phase_for("resumed"), Some("active"));
}

#[test]
fn an_unknown_window_event_reports_nothing() {
    // Emitting a guess would be worse than silence: the TypeScript drops an
    // unrecognised phase rather than defaulting, precisely so a wrong guess
    // cannot resume the render loop on a suspended app.
    use praisonai_mobile_lib::shell::lifecycle::phase_for;
    assert_eq!(phase_for("resized"), None);
    assert_eq!(phase_for(""), None);
}
