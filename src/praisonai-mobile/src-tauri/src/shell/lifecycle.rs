//! Lifecycle, which Tauri very nearly gives us for free.
//!
//! `WindowEvent::Suspended` / `Resumed` are already surfaced on mobile:
//! `onPause`/`onResume` on Android, `applicationWillResignActive` /
//! `willEnterForeground` on iOS. `WindowEvent::Focused` is surfaced on every
//! platform. Only the translation is ours, and it is in three pure pieces:
//!
//!  - [`window_event_name`] names the Tauri variant. The mobile-only variants
//!    are not constructible on a laptop, which is why the rest of the chain
//!    works on strings: it can be tested where the tests run.
//!  - [`phase_for`] maps a name to one of the three phases the TypeScript
//!    accepts.
//!  - [`Tracker`] decides whether that phase is news. The platforms deliver
//!    focus and suspension in an order that would otherwise announce
//!    `inactive` AFTER `background`, or `active` twice.

use tauri::WindowEvent;

/// A platform-neutral name for the window events the shell cares about.
///
/// `Suspended`/`Resumed` exist only under `cfg(mobile)`; the arms are gated
/// the same way so the desktop dev build compiles, and `cargo check --target
/// aarch64-linux-android` is what proves the mobile arms still match Tauri.
pub fn window_event_name(event: &WindowEvent) -> Option<&'static str> {
    match event {
        #[cfg(mobile)]
        WindowEvent::Suspended => Some("suspended"),
        #[cfg(mobile)]
        WindowEvent::Resumed => Some("resumed"),
        WindowEvent::Focused(true) => Some("focused"),
        WindowEvent::Focused(false) => Some("unfocused"),
        // Resized, ScaleFactorChanged, Moved, CloseRequested, Destroyed,
        // DragDrop, ThemeChanged, and whatever a future Tauri adds
        // (`WindowEvent` is non_exhaustive): none of these is a phase.
        _ => None,
    }
}

/// The phase to report for a named window event, or `None` to say nothing.
///
/// # The mapping decision, stated rather than buried
///
/// Tauri gives a two-state model and `ShellPort` declares three. `Suspended`
/// is `willResignActive` on iOS and `onPause` on Android, both of which are
/// semantically **inactive** rather than **background**.
///
/// It is mapped to `background` anyway, and that is deliberate. `boot.ts` only
/// flushes on `background`, and `core/src/ports/shell.ts` records why that
/// matters: *"on iOS the app can be killed while suspended with no further
/// callback, so anything unflushed at this moment is simply lost."* Mapping to
/// `inactive` would mean the flush never runs and transcripts are lost on every
/// backgrounding.
///
/// The cost is that a control-centre pull-down or a permission dialog stops
/// the run loop unnecessarily. That is the right trade — a needless pause is
/// recoverable, a lost transcript is not — but it is a trade, and closing it
/// needs platform code: `didEnterBackgroundNotification` on iOS,
/// `ProcessLifecycleOwner` on Android.
///
/// `inactive` comes from focus loss alone: a system dialog over the activity,
/// a window blur on the desktop dev build. `active` is both `resumed` and
/// focus gain, because a control-centre dismissal on iOS is `didBecomeActive`
/// with no `willEnterForeground` before it — without the focus arm, that app
/// would stay reported as backgrounded until the next real suspend/resume.
pub fn phase_for(event: &str) -> Option<&'static str> {
    match event {
        "suspended" => Some("background"),
        "resumed" => Some("active"),
        "focused" => Some("active"),
        "unfocused" => Some("inactive"),
        _ => None,
    }
}

/// Decides whether a phase is worth announcing, given what was announced last.
///
/// Two suppressions, each for a real delivery order:
///
///  1. **`inactive` after `background` is dropped.** Android's `onPause` is
///     followed by `onWindowFocusChanged(false)`; iOS's `willResignActive`
///     is followed by a scene `Focused(false)`. Passing the second through
///     would tell the webview the app had come *up* to inactive when it is
///     in fact still in the background.
///  2. **A repeat of the current phase is dropped.** `onResume` is followed
///     by `onWindowFocusChanged(true)`, and both say `active`.
///
/// Anything else — including `inactive` → `background`, and `background` →
/// `active` via focus alone — passes through.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct Tracker {
    current: Option<&'static str>,
}

impl Tracker {
    pub fn new() -> Self {
        Self::default()
    }

    /// A named window event happened. `Some(phase)` if the webview should be
    /// told; `None` if the event is not a phase or is not news.
    pub fn observe(&mut self, event: &str) -> Option<&'static str> {
        let phase = phase_for(event)?;
        if self.current == Some(phase) {
            return None;
        }
        if phase == "inactive" && self.current == Some("background") {
            return None;
        }
        self.current = Some(phase);
        Some(phase)
    }

    /// The last phase announced, if any.
    pub fn current(&self) -> Option<&'static str> {
        self.current
    }
}
