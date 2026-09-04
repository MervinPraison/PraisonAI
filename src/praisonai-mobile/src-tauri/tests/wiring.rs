//! The wiring, which is the half of this crate no pure test can reach.
//!
//! `shell/lifecycle.rs` and `shell/back.rs` are pure and thoroughly tested.
//! But a phone sees none of that unless three things are true at once:
//! `on_window_event` is REGISTERED, `LifecycleState` is MANAGED, and the
//! translation actually reaches `Emitter::emit`. Every one of those is silent
//! when it breaks — a missing `manage` logs a warning no device shows, a
//! missing `on_window_event` emits nothing and reports nothing — so mutation
//! testing found all of them surviving the pure suite untouched.
//!
//! These tests build the SAME builder chain the app runs (`configure`) on
//! Tauri's mock runtime, and push a real `Window` through the real handler.

use std::sync::mpsc;
use std::time::Duration;

use praisonai_mobile_lib::{
    commands::BackState,
    configure,
    shell::{self, LifecycleState, EVT_LIFECYCLE, EVT_SAFE_AREA},
};
use tauri::{
    test::{mock_builder, mock_context, noop_assets, MockRuntime},
    Listener, Manager, PhysicalSize, WindowEvent,
};

/// The app exactly as `run()` builds it, minus the parts that need a device.
fn app() -> tauri::App<MockRuntime> {
    configure(mock_builder())
        .build(mock_context(noop_assets()))
        .expect("the shell's builder chain must produce an app")
}

fn window(app: &tauri::App<MockRuntime>) -> tauri::Window<MockRuntime> {
    tauri::webview::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::default())
        .build()
        .expect("a mock window")
        .as_ref()
        .window()
}

/// Collect the payloads of one event as they are emitted.
fn subscribe(app: &tauri::App<MockRuntime>, event: &str) -> mpsc::Receiver<String> {
    let (tx, rx) = mpsc::channel();
    app.listen(event, move |e| {
        let _ = tx.send(e.payload().to_string());
    });
    rx
}

fn next(rx: &mpsc::Receiver<String>) -> Option<String> {
    rx.recv_timeout(Duration::from_secs(2)).ok()
}

// ---- the builder chain -----------------------------------------------------

#[test]
fn the_app_manages_the_state_the_window_handler_reaches_for() {
    // Without this, `on_window_event` takes its `try_state` bail-out and every
    // lifecycle phase is dropped with a log line -- on a phone, invisibly.
    let app = app();
    assert!(
        app.try_state::<LifecycleState>().is_some(),
        "LifecycleState is not managed; every lifecycle event would be dropped"
    );
    assert!(
        app.try_state::<BackState>().is_some(),
        "BackState is not managed; the back gate would panic on the first press"
    );
}

// ---- the window-event handler ----------------------------------------------

#[test]
fn a_focus_change_emits_the_lifecycle_phase_the_typescript_listens_for() {
    // The whole point of the crate: a Tauri window event has to come out of
    // `Emitter::emit` under the contract name, or the webview hears nothing.
    let app = app();
    let win = window(&app);
    let rx = subscribe(&app, EVT_LIFECYCLE);

    shell::on_window_event(&win, &WindowEvent::Focused(true));
    assert_eq!(
        next(&rx).as_deref(),
        Some("\"active\""),
        "focus gain must emit {EVT_LIFECYCLE} = active"
    );

    shell::on_window_event(&win, &WindowEvent::Focused(false));
    assert_eq!(
        next(&rx).as_deref(),
        Some("\"inactive\""),
        "focus loss must emit {EVT_LIFECYCLE} = inactive"
    );
}

#[test]
fn a_repeated_phase_is_not_re_emitted_through_the_real_handler() {
    // The Tracker's suppression is unit-tested; this proves the handler
    // actually consults the SHARED state rather than a fresh one per event.
    // With a per-call Tracker every one of these would emit.
    let app = app();
    let win = window(&app);
    let rx = subscribe(&app, EVT_LIFECYCLE);

    shell::on_window_event(&win, &WindowEvent::Focused(true));
    assert_eq!(next(&rx).as_deref(), Some("\"active\""));

    shell::on_window_event(&win, &WindowEvent::Focused(true));
    assert_eq!(
        next(&rx),
        None,
        "the same phase twice must be announced once; the state is not shared"
    );
}

#[test]
fn a_resize_emits_the_safe_area_event_with_an_empty_payload() {
    // Empty on purpose: Tauri does not expose the insets, and the TypeScript's
    // `coerceInsets` reads a payload with no edges as "re-read the CSS
    // env() variables". Sending zeros would be a lie the composer lays out
    // against, so the payload shape is as load-bearing as the name.
    let app = app();
    let win = window(&app);
    let rx = subscribe(&app, EVT_SAFE_AREA);

    shell::on_window_event(&win, &WindowEvent::Resized(PhysicalSize::new(390, 844)));
    assert_eq!(
        next(&rx).as_deref(),
        Some("{}"),
        "a resize must emit {EVT_SAFE_AREA} with an empty payload"
    );
}

#[test]
fn a_resize_is_not_also_announced_as_a_lifecycle_phase() {
    // Every rotation would otherwise look like a resume.
    let app = app();
    let win = window(&app);
    let rx = subscribe(&app, EVT_LIFECYCLE);

    shell::on_window_event(&win, &WindowEvent::Resized(PhysicalSize::new(390, 844)));
    assert_eq!(next(&rx), None, "a resize is not a lifecycle phase");
}

// ---- the one line the mock runtime cannot check ----------------------------

#[test]
fn run_registers_the_window_event_handler() {
    // Tauri's MockRuntime accepts `on_window_event` and DROPS the callback
    // (test/mock_runtime.rs: the closure is never stored), so no mock app can
    // observe whether the handler is registered -- and deleting that one line
    // leaves every other test in this file passing while a device goes
    // completely silent. A source assertion is the only gate available, so
    // this is that gate, stated plainly rather than left as a hole.
    const LIB_RS: &str = include_str!("../src/lib.rs");
    for required in [
        ".on_window_event(shell::on_window_event)",
        ".manage(shell::LifecycleState::default())",
        ".manage(commands::BackState::default())",
        "tauri_plugin_back_gesture::init(commands::on_back_pressed)",
        "commands::back_gesture_can_go_back",
    ] {
        assert!(
            LIB_RS.contains(required),
            "src/lib.rs no longer contains `{required}` -- the shell would be \
             silent on a device with every other test still green"
        );
    }
    // And that `run` goes through the chain the tests above build.
    assert!(
        LIB_RS.contains("configure(tauri::Builder::default())"),
        "run() no longer builds the app through configure(), so tests/wiring.rs \
         is testing a chain the app does not use"
    );
}
