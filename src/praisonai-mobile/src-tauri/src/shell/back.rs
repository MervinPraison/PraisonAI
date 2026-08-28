//! Back-gesture arbitration.
//!
//! Android presses back. Rust asks the webview whether it wants it. The webview
//! answers, and if it says no, Rust lets the system act.
//!
//! Three things make this harder than it sounds, and all three are failure
//! modes rather than edge cases:
//!
//!  1. **The answer may never come.** `bridge.invoke` on the TypeScript side
//!     swallows every rejection into `null`, so silence is indistinguishable
//!     from success. If the bundle failed to load, or JS threw before the
//!     handler was attached, a back button that does nothing FOREVER is worse
//!     than one that exits. Hence the watchdog.
//!  2. **There is no correlation id.** The webview sends `{ handled }` and
//!     nothing else, and the TypeScript adapter cannot add one without changing
//!     a frozen contract. So two presses close together would produce two
//!     answers Rust could not tell apart, and the second could pop an activity
//!     the first decided to keep. Dropping presses while one is pending is the
//!     only correct option available on this side.
//!  3. **A late answer must not act twice.** If the watchdog already fired and
//!     fell back, an answer arriving afterwards has to be ignored, or the app
//!     falls back twice for one press.
//!
//! The logic is pure and the platform is injected, so all of that is tested on
//! a laptop rather than discovered on a device.

/// What the caller should do next. Returned rather than performed, so the
/// decision is testable and the side effect lives at the edge.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    /// Ask the webview. It will answer via the `back_gesture_result` command.
    Ask,
    /// Do nothing: a press is already in flight and there is no way to tell
    /// two answers apart.
    Drop,
    /// Let the platform act. On Android that means re-dispatching so the
    /// SYSTEM default runs, which on 12+ moves the task to the back rather
    /// than destroying the activity — preserving warm start.
    FallBack,
    /// A stray or late answer. Ignore it.
    Ignore,
}

/// One press in flight at a time. See the header for why there cannot be more.
#[derive(Debug, Default)]
pub struct Gate {
    pending: bool,
}

impl Gate {
    pub fn new() -> Self {
        Self { pending: false }
    }

    /// The user pressed back.
    pub fn press(&mut self) -> Action {
        if self.pending {
            return Action::Drop;
        }
        self.pending = true;
        Action::Ask
    }

    /// The webview answered.
    pub fn answered(&mut self, handled: bool) -> Action {
        if !self.pending {
            // The watchdog already fired, or this is a stray. Falling back
            // again would exit an app the user is still using.
            return Action::Ignore;
        }
        self.pending = false;
        if handled {
            Action::Ignore
        } else {
            Action::FallBack
        }
    }

    /// The answer never came.
    pub fn timed_out(&mut self) -> Action {
        if !self.pending {
            // It arrived between the timer firing and this running. Not a
            // timeout at all.
            return Action::Ignore;
        }
        self.pending = false;
        Action::FallBack
    }

    pub fn is_pending(&self) -> bool {
        self.pending
    }
}

/// How long to wait for the webview before assuming it will never answer.
///
/// A guess, and deliberately generous: too short falls back while a slow
/// handler is still deciding, which exits an app the user did not ask to
/// leave. Too long leaves a dead back button. Measure the real round trip on a
/// cold device and set this to several times it.
pub const ANSWER_TIMEOUT_MS: u64 = 400;

/// Lowering this is a mistake with a specific consequence, so it fails the
/// BUILD rather than a test: too short a timeout falls back while a slow
/// handler is still deciding, which sends the app to the background for a back
/// press the user's own UI was about to handle.
const _: () = assert!(ANSWER_TIMEOUT_MS >= 250);
