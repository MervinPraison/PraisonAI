//! Deciding, from the child's own log lines, whether the engine came up.
//!
//! Modelled on jan's `is_ready_line` (jan/src-tauri/plugins/tauri-plugin-llamacpp/
//! src/router.rs:22-36), whose doc comment records that a single added colon in an
//! upstream log line broke readiness detection in the field. The lesson generalises:
//! the phrase is an *upstream* string that changes between versions, so it belongs
//! in a tested pure function rather than inline in the spawn path.
//!
//! Our engine is a Python HTTP server, so the phrasings differ from llama.cpp's.

/// True when `line` is the engine announcing it is serving.
///
/// Lowercased by the caller. Matching is broad on purpose: a false negative
/// costs a spurious startup timeout, which is far worse than a false positive
/// that the health probe then rejects.
pub fn is_ready_line(line_lower: &str) -> bool {
    line_lower.contains("uvicorn running on")
        || line_lower.contains("application startup complete")
        || line_lower.contains("praisonai runtime listening")
        || line_lower.contains("running on http://127.0.0.1")
}

/// A recognised way for a Python engine to die.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Crash {
    /// A dependency is missing: the venv is broken, not the machine.
    MissingModule,
    /// Out of memory, host or accelerator.
    OutOfMemory,
    /// The port was taken. jan's unchecked random port makes this common.
    AddressInUse,
    /// An unhandled exception reached the top of the stack.
    Traceback,
}

/// Classify one stderr line. `None` means "not a recognised failure", which is
/// not the same as "healthy" -- the caller must not read it as success.
pub fn classify_crash(line_lower: &str) -> Option<Crash> {
    if line_lower.contains("modulenotfounderror") || line_lower.contains("importerror") {
        return Some(Crash::MissingModule);
    }
    if line_lower.contains("memoryerror")
        || line_lower.contains("out of memory")
        || line_lower.contains("killed process")
    {
        return Some(Crash::OutOfMemory);
    }
    if line_lower.contains("address already in use") || line_lower.contains("errno 48") {
        return Some(Crash::AddressInUse);
    }
    if line_lower.contains("traceback (most recent call last)") {
        return Some(Crash::Traceback);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ready(line: &str) -> bool {
        is_ready_line(&line.to_lowercase())
    }
    fn crash(line: &str) -> Option<Crash> {
        classify_crash(&line.to_lowercase())
    }

    #[test]
    fn recognises_the_phrasings_our_engine_actually_prints() {
        assert!(ready("INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)"));
        assert!(ready("INFO:     Application startup complete."));
        assert!(ready("praisonai runtime listening on 127.0.0.1:51234"));
    }

    #[test]
    fn does_not_mistake_ordinary_chatter_for_readiness() {
        // The failure that matters: a line that merely mentions the server while
        // it is still starting, or is actively failing, must not count.
        assert!(!ready("INFO:     Waiting for application startup."));
        assert!(!ready("ERROR:    Uvicorn failed to start"));
        assert!(!ready("loading praisonai runtime"));
        assert!(!ready(""));
    }

    #[test]
    fn a_startup_that_begins_but_never_completes_is_not_ready() {
        // uvicorn prints "Waiting for application startup." then hangs if a
        // lifespan handler blocks. Treating that as ready routes a user's first
        // message into a server that will never answer.
        assert!(!ready("info:     waiting for application startup."));
        assert!(ready("info:     application startup complete."));
    }

    #[test]
    fn classifies_the_failures_a_broken_venv_produces() {
        assert_eq!(crash("ModuleNotFoundError: No module named 'litellm'"), Some(Crash::MissingModule));
        assert_eq!(crash("ImportError: dlopen(.../pydantic_core.so): incompatible"), Some(Crash::MissingModule));
        assert_eq!(crash("OSError: [Errno 48] Address already in use"), Some(Crash::AddressInUse));
        assert_eq!(crash("Traceback (most recent call last):"), Some(Crash::Traceback));
        assert_eq!(crash("MemoryError"), Some(Crash::OutOfMemory));
    }

    #[test]
    fn an_unrecognised_line_is_none_and_never_success() {
        // Guards the read-site: None must mean "no verdict", not "fine".
        assert_eq!(crash("INFO:     Started server process [12345]"), None);
        assert_eq!(crash(""), None);
    }

    #[test]
    fn a_ready_line_is_never_also_a_crash_line() {
        for line in [
            "INFO:     Uvicorn running on http://127.0.0.1:8765",
            "INFO:     Application startup complete.",
        ] {
            assert!(ready(line));
            assert_eq!(crash(line), None, "{line:?} classified as both ready and crashed");
        }
    }
}
