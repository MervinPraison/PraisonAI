//! Lifecycle, which Tauri very nearly gives us for free.
//!
//! `WindowEvent::Suspended` / `Resumed` are already surfaced on mobile:
//! `onPause`/`onResume` on Android, `applicationWillResignActive` /
//! `willEnterForeground` on iOS. Only the translation is ours.

/// The phase to report for a Tauri window event, or `None` to say nothing.
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
/// The cost is that a control-centre pull-down stops the run loop
/// unnecessarily, and that `inactive` is never emitted from here at all. That
/// is the right trade — a needless pause is recoverable, a lost transcript is
/// not — but it is a trade, and emitting all three needs platform code:
/// `didEnterBackgroundNotification` on iOS, `ProcessLifecycleOwner` on Android.
pub fn phase_for(event: &str) -> Option<&'static str> {
    match event {
        "suspended" => Some("background"),
        "resumed" => Some("active"),
        _ => None,
    }
}
