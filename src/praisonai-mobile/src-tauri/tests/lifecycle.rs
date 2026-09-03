//! The lifecycle translation, event by event and sequence by sequence.
//!
//! The strings asserted here are the ones `coercePhase` in
//! `adapters/src/tauri/shell.ts` accepts: `active`, `inactive`, `background`.
//! Anything else is DROPPED by the TypeScript rather than defaulted, so a
//! misspelling here would not throw anywhere — the app would simply never
//! flush on backgrounding again.

use praisonai_mobile_lib::shell::lifecycle::{phase_for, window_event_name, Tracker};
use tauri::{PhysicalSize, WindowEvent};

/// Exactly what `LIFECYCLE_PHASES` in shell.ts lists.
const ACCEPTED_BY_TYPESCRIPT: [&str; 3] = ["active", "inactive", "background"];

#[test]
fn every_relevant_window_event_maps_to_a_phase_the_typescript_accepts() {
    // The full set of names `window_event_name` can produce, each pinned to
    // its exact phase. Adding a name there without adding it here fails.
    let expected = [
        ("suspended", "background"),
        ("resumed", "active"),
        ("focused", "active"),
        ("unfocused", "inactive"),
    ];
    for (event, phase) in expected {
        assert_eq!(phase_for(event), Some(phase), "phase_for({event:?})");
        assert!(
            ACCEPTED_BY_TYPESCRIPT.contains(&phase),
            "{phase:?} is not a LifecyclePhase the TypeScript accepts"
        );
    }
}

#[test]
fn the_variants_constructible_on_a_laptop_are_named() {
    // Suspended/Resumed exist only under cfg(mobile) and cannot be built
    // here; the android cross-check in CI compiles those arms. Focus can.
    assert_eq!(window_event_name(&WindowEvent::Focused(true)), Some("focused"));
    assert_eq!(window_event_name(&WindowEvent::Focused(false)), Some("unfocused"));
}

#[test]
fn geometry_and_teardown_are_not_phases() {
    // Resized is what drives safe-area-changed; it must not also announce a
    // lifecycle phase, or every rotation would look like a resume.
    // ScaleFactorChanged is not constructible here (non_exhaustive variant);
    // it takes the same `_ => None` arm as Resized.
    assert_eq!(window_event_name(&WindowEvent::Resized(PhysicalSize::new(1, 1))), None);
    assert_eq!(window_event_name(&WindowEvent::Destroyed), None);
}

// ---- sequences the platforms actually deliver -------------------------------

#[test]
fn android_home_press_announces_background_once_and_not_inactive_after_it() {
    // onPause, then onWindowFocusChanged(false). The second must not be
    // reported: it would tell the webview the app had come UP to inactive.
    let mut t = Tracker::new();
    assert_eq!(t.observe("focused"), Some("active"));
    assert_eq!(t.observe("suspended"), Some("background"));
    assert_eq!(t.observe("unfocused"), None);
    assert_eq!(t.current(), Some("background"));
}

#[test]
fn android_return_announces_active_once_for_resume_plus_focus() {
    // onResume, then onWindowFocusChanged(true): both say active.
    let mut t = Tracker::new();
    t.observe("suspended");
    assert_eq!(t.observe("resumed"), Some("active"));
    assert_eq!(t.observe("focused"), None);
}

#[test]
fn focus_loss_before_suspension_reports_both_in_order() {
    // The other order the platforms use. inactive -> background is real
    // progress and both must arrive, in that order.
    let mut t = Tracker::new();
    t.observe("focused");
    assert_eq!(t.observe("unfocused"), Some("inactive"));
    assert_eq!(t.observe("suspended"), Some("background"));
}

#[test]
fn ios_control_centre_dismissal_returns_to_active_through_focus_alone() {
    // willResignActive suspends; the pull-down dismissal is didBecomeActive
    // with NO willEnterForeground. Without the focus arm the app would stay
    // reported as backgrounded.
    let mut t = Tracker::new();
    t.observe("focused");
    assert_eq!(t.observe("suspended"), Some("background"));
    assert_eq!(t.observe("focused"), Some("active"));
}

#[test]
fn a_system_dialog_is_inactive_then_active() {
    let mut t = Tracker::new();
    t.observe("focused");
    assert_eq!(t.observe("unfocused"), Some("inactive"));
    assert_eq!(t.observe("focused"), Some("active"));
}

#[test]
fn a_name_that_is_not_a_phase_is_ignored_and_does_not_disturb_the_state() {
    let mut t = Tracker::new();
    t.observe("suspended");
    assert_eq!(t.observe("resized"), None);
    assert_eq!(t.current(), Some("background"));
}
