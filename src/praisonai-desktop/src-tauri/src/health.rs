//! Deciding whether the engine is actually up.
//!
//! The obvious implementation -- poll a URL, treat 2xx as ready -- is wrong
//! against this backend. `praisonai_code/runtime/server.py:362` answers failures
//! with HTTP 200 and `{"ok": false, "error": ...}`, so status alone cannot
//! separate "engine healthy" from "engine broken". Readiness must therefore be a
//! positive assertion in the body, and anything it cannot parse is not ready.

/// Why a probe did not count as ready. Distinct variants because the supervisor
/// restarts on one and refuses on another: a transport error may be the engine
/// still binding its socket, whereas a version mismatch will never fix itself.
#[derive(Debug, PartialEq, Eq)]
pub enum NotReady {
    Transport,
    HttpStatus(u16),
    Malformed,
    /// The body parsed and explicitly said it is not ok.
    Unhealthy(String),
    VersionMismatch { expected: u32, actual: u32 },
}

#[derive(Debug, PartialEq, Eq)]
pub struct Ready {
    pub version: u32,
}

/// A probe outcome as seen by the transport layer.
pub enum Probe<'a> {
    Failed,
    Responded { status: u16, body: &'a str },
}

/// Classify one health probe. Pure: no sockets, no clock, no retries.
/// Protocol version this shell speaks. The engine reports its own; a mismatch
/// is a distinguishable failure, not a generic one.
pub const EXPECTED_VERSION: u32 = 2;

pub fn classify(probe: Probe<'_>, expected_version: u32) -> Result<Ready, NotReady> {
    let (status, body) = match probe {
        Probe::Failed => return Err(NotReady::Transport),
        Probe::Responded { status, body } => (status, body),
    };

    if !(200..300).contains(&status) {
        return Err(NotReady::HttpStatus(status));
    }

    // Deliberately not a JSON dependency: the health body is a fixed, tiny shape
    // and the supervisor must not gain a parser that can itself fail obscurely.
    let ok = field(body, "ok").ok_or(NotReady::Malformed)?;
    if ok != "true" {
        let reason = field(body, "error").unwrap_or_else(|| "unspecified".to_string());
        return Err(NotReady::Unhealthy(reason));
    }

    let version = field(body, "version")
        .and_then(|v| v.parse::<u32>().ok())
        .ok_or(NotReady::Malformed)?;

    if version != expected_version {
        return Err(NotReady::VersionMismatch { expected: expected_version, actual: version });
    }
    Ok(Ready { version })
}

/// Confirm an engine was launched by the same desktop release as this shell.
///
/// Protocol compatibility alone is insufficient when adopting an engine left
/// behind by a previous shell process: that child retains the old release
/// version in its environment and would otherwise report stale About data.
pub fn shell_version_matches(body: &str, expected: &str) -> bool {
    field(body, "shell_version").as_deref() == Some(expected)
}

/// Extract a scalar JSON field. Returns `None` rather than a default, so a
/// missing field can never be mistaken for a present one.
fn field(body: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let rest = &body[body.find(&needle)? + needle.len()..];
    let rest = rest.trim_start().strip_prefix(':')?.trim_start();
    let value: String = match rest.strip_prefix('"') {
        Some(quoted) => quoted.chars().take_while(|c| *c != '"').collect(),
        None => rest
            .chars()
            .take_while(|c| !c.is_whitespace() && *c != ',' && *c != '}')
            .collect(),
    };
    (!value.is_empty()).then_some(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    const V: u32 = 1;

    #[test]
    fn a_healthy_body_is_ready() {
        let probe = Probe::Responded { status: 200, body: r#"{"ok": true, "version": 1}"# };
        assert_eq!(classify(probe, V), Ok(Ready { version: 1 }));
    }

    #[test]
    fn http_200_with_ok_false_is_not_ready() {
        // The exact shape runtime/server.py:362 emits on any unhandled exception.
        // A supervisor that trusted the status code would call this engine healthy
        // and route a user's chat into it.
        let probe = Probe::Responded {
            status: 200,
            body: r#"{"ok": false, "error": "no module named litellm"}"#,
        };
        assert_eq!(
            classify(probe, V),
            Err(NotReady::Unhealthy("no module named litellm".to_string()))
        );
    }

    #[test]
    fn a_body_missing_ok_is_malformed_not_ready() {
        let probe = Probe::Responded { status: 200, body: r#"{"version": 1}"# };
        assert_eq!(classify(probe, V), Err(NotReady::Malformed));
    }

    #[test]
    fn an_empty_200_is_malformed_not_ready() {
        // A proxy, a captive portal, or a different server on a recycled port all
        // produce this. None of them are our engine.
        assert_eq!(classify(Probe::Responded { status: 200, body: "" }, V), Err(NotReady::Malformed));
    }

    #[test]
    fn a_version_mismatch_is_distinct_from_being_down() {
        // Restarting fixes a transport error and never fixes this one.
        let probe = Probe::Responded { status: 200, body: r#"{"ok": true, "version": 2}"# };
        assert_eq!(classify(probe, V), Err(NotReady::VersionMismatch { expected: 1, actual: 2 }));
    }

    #[test]
    fn transport_failure_is_distinct_from_a_bad_response() {
        assert_eq!(classify(Probe::Failed, V), Err(NotReady::Transport));
        assert_eq!(
            classify(Probe::Responded { status: 503, body: "" }, V),
            Err(NotReady::HttpStatus(503))
        );
    }

    #[test]
    fn a_field_named_like_another_is_not_confused_for_it() {
        // "not_ok" contains "ok"; a substring search would read the wrong field.
        let probe = Probe::Responded { status: 200, body: r#"{"not_ok": true, "ok": false}"# };
        assert!(matches!(classify(probe, V), Err(NotReady::Unhealthy(_))));
    }

    #[test]
    fn an_adopted_engine_must_match_the_shell_release() {
        let current = r#"{"ok": true, "version": 1, "shell_version": "4.7.3"}"#;
        let stale = r#"{"ok": true, "version": 1, "shell_version": "4.7.2"}"#;
        assert!(shell_version_matches(current, "4.7.3"));
        assert!(!shell_version_matches(stale, "4.7.3"));
        assert!(!shell_version_matches(r#"{"ok": true, "version": 1}"#, "4.7.3"));
    }
}
