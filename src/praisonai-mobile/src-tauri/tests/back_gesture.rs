//! Back-gesture arbitration.
//!
//! Every case here is a failure mode that would otherwise only appear on a
//! device, and two of them are the kind a user reports as "the back button is
//! broken" with no way to say more.

use praisonai_mobile_lib::shell::back::{Action, Gate};

#[test]
fn a_press_asks_the_webview() {
    let mut gate = Gate::new();
    assert_eq!(gate.press(), Action::Ask);
    assert!(gate.is_pending());
}

#[test]
fn declining_lets_the_platform_act() {
    // handled: false means the app did not want it -- on Android the system
    // default must run, or back at the root does nothing at all.
    let mut gate = Gate::new();
    gate.press();
    assert_eq!(gate.answered(false), Action::FallBack);
    assert!(!gate.is_pending());
}

#[test]
fn handling_does_not_let_the_platform_act() {
    // The pair. If a handled press also fell back, closing a modal would
    // simultaneously send the app to the background.
    let mut gate = Gate::new();
    gate.press();
    assert_eq!(gate.answered(true), Action::Ignore);
}

#[test]
fn a_second_press_while_pending_is_dropped() {
    // There is no correlation id in the payload -- the webview sends only
    // { handled } -- so two answers cannot be told apart, and the second could
    // pop an activity the first decided to keep.
    let mut gate = Gate::new();
    assert_eq!(gate.press(), Action::Ask);
    assert_eq!(gate.press(), Action::Drop);
}

#[test]
fn a_press_after_an_answer_is_asked_again() {
    // The pair for dropping: a gate that latched would answer the first back
    // press of the session and ignore every one after it.
    let mut gate = Gate::new();
    gate.press();
    gate.answered(true);
    assert_eq!(gate.press(), Action::Ask);
}

#[test]
fn silence_falls_back_rather_than_leaving_a_dead_button() {
    // bridge.invoke swallows every failure on the TypeScript side, so silence
    // is indistinguishable from success. Without this, a bundle that failed to
    // load leaves a back button that does nothing forever -- which is worse
    // than one that exits.
    let mut gate = Gate::new();
    gate.press();
    assert_eq!(gate.timed_out(), Action::FallBack);
}

#[test]
fn silence_does_not_take_the_app_away_when_it_said_it_can_go_back() {
    // The device bug this whole declaration exists for. Back on the Settings
    // screen: the webview HAD consumed the press and popped, but its answer
    // took 5.4 s to cross the bridge, the 400 ms watchdog fired first, and the
    // app was handed to the platform -- which left it. The app said it could go
    // back, so silence is a slow webview, not one that declined.
    let mut gate = Gate::new();
    gate.declare_can_go_back(true);
    gate.press();
    assert_eq!(gate.timed_out(), Action::Ignore);
    assert!(!gate.is_pending(), "the press is spent either way");
}

#[test]
fn silence_still_falls_back_when_the_app_says_it_cannot_go_back() {
    // The other half, and the reason the declaration is not simply "never fall
    // back on silence": at the root there is nothing to pop, so a webview that
    // never answers must not leave the back button dead.
    let mut gate = Gate::new();
    gate.declare_can_go_back(false);
    gate.press();
    assert_eq!(gate.timed_out(), Action::FallBack);
}

#[test]
fn a_gate_that_was_told_nothing_assumes_it_cannot_go_back() {
    // A bundle that failed to load declares nothing at all. Defaulting to "it
    // can go back" would swallow every press on an app that cannot even paint.
    let gate = Gate::new();
    assert!(!gate.can_go_back());
    assert!(!Gate::default().can_go_back());
}

#[test]
fn an_explicit_no_falls_back_even_from_a_screen_that_could_go_back() {
    // The declaration only speaks for silence. An answer is the app's own word
    // about THIS press and outranks it -- otherwise a route the app decided not
    // to pop would leave the back button doing nothing.
    let mut gate = Gate::new();
    gate.declare_can_go_back(true);
    gate.press();
    assert_eq!(gate.answered(false), Action::FallBack);
}

#[test]
fn going_back_to_the_root_re_arms_the_fall_back() {
    // The declaration is a mirror of a stack that moves both ways. Popping the
    // last route has to clear it, or the app is one that can never be left.
    let mut gate = Gate::new();
    gate.declare_can_go_back(true);
    gate.declare_can_go_back(false);
    gate.press();
    assert_eq!(gate.timed_out(), Action::FallBack);
}

#[test]
fn a_late_answer_after_a_timeout_does_not_fall_back_twice() {
    // The bug this design is most likely to ship: the watchdog fires, the app
    // goes to the background, and the webview's answer arrives afterwards and
    // sends it back again.
    let mut gate = Gate::new();
    gate.press();
    assert_eq!(gate.timed_out(), Action::FallBack);
    assert_eq!(gate.answered(false), Action::Ignore);
}

#[test]
fn a_timeout_after_an_answer_does_nothing() {
    // The mirror: the answer arrived between the timer firing and its handler
    // running. That is not a timeout, and treating it as one exits the app.
    let mut gate = Gate::new();
    gate.press();
    gate.answered(true);
    assert_eq!(gate.timed_out(), Action::Ignore);
}

#[test]
fn a_stray_answer_with_no_press_is_ignored() {
    let mut gate = Gate::new();
    assert_eq!(gate.answered(false), Action::Ignore);
}

// The timeout floor is asserted at COMPILE time in shell::back -- clippy
// correctly points out that asserting on a const inside a test proves nothing
// at runtime, and a build failure is the stronger guard anyway.
