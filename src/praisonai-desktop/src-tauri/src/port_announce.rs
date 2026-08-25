//! Learning which port the engine bound, without ever guessing.
//!
//! Two failure modes are being designed out here, both observed in shipped apps:
//!
//!   * **Picking a port and hoping.** jan draws a random ephemeral port with no
//!     bind test (llamacpp-extension/src/index.ts:3400-3402); a collision then
//!     surfaces only as a startup timeout with a misleading message. The fix is
//!     to let the kernel assign it -- the child binds `127.0.0.1:0` and reports
//!     what it got, so a collision cannot happen at all.
//!
//!   * **Trusting the announcement.** A port parsed from a log line is a claim,
//!     not a fact: a stale line from a previous run, a partial write, or an
//!     unrelated process's output can all supply one. unsloth validates over HTTP
//!     before telling the UI (process.rs:3491-3537) precisely because a wrong
//!     port sends the first user message into another process.
//!
//! So this module only *extracts* a claim. Publishing it is gated on a health
//! probe elsewhere, and the type makes that ordering hard to skip.

/// A port parsed from the child's output. Deliberately not a bare `u16`: an
/// unvalidated port must not be interchangeable with a validated one.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub struct AnnouncedPort(u16);

impl AnnouncedPort {
    /// Consume the claim by validating it. There is no other way to get the
    /// number out, so a caller cannot accidentally use an unchecked port.
    pub fn confirm(self, probe: impl FnOnce(u16) -> bool) -> Option<u16> {
        probe(self.0).then_some(self.0)
    }

    /// Escape hatch for logging only. Never pass the result to a connection.
    pub fn for_logging(self) -> u16 {
        self.0
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum AnnounceError {
    /// Port 0 means the child never actually bound.
    NotBound,
    /// Present but unparseable as a port.
    Malformed(String),
    /// Two different ports announced. A stale line is mixed in with a live one,
    /// and choosing either silently would be a coin flip.
    Conflicting { first: u16, second: u16 },
}

const MARKER: &str = "PRAISONAI_PORT=";

/// Scan accumulated child output for a port announcement.
///
/// `Ok(None)` means "not yet" -- the caller keeps reading. Errors are terminal
/// and must fail the launch rather than fall back to a default port.
pub fn scan(output: &str) -> Result<Option<AnnouncedPort>, AnnounceError> {
    let mut found: Option<u16> = None;

    for line in output.lines() {
        let Some(idx) = line.find(MARKER) else { continue };
        let raw: String = line[idx + MARKER.len()..]
            .chars()
            .take_while(|c| c.is_ascii_digit())
            .collect();

        if raw.is_empty() {
            return Err(AnnounceError::Malformed(line.trim().to_string()));
        }
        let port: u16 = raw.parse().map_err(|_| AnnounceError::Malformed(raw.clone()))?;
        if port == 0 {
            return Err(AnnounceError::NotBound);
        }
        match found {
            Some(first) if first != port => {
                return Err(AnnounceError::Conflicting { first, second: port })
            }
            _ => found = Some(port),
        }
    }
    Ok(found.map(AnnouncedPort))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_the_port_from_a_normal_startup_log() {
        let out = "INFO: starting\nPRAISONAI_PORT=51234\nINFO: ready\n";
        assert_eq!(scan(out), Ok(Some(AnnouncedPort(51234))));
    }

    #[test]
    fn absence_is_not_an_error_it_is_not_yet() {
        // The caller is streaming output; "no port line so far" must not fail.
        assert_eq!(scan(""), Ok(None));
        assert_eq!(scan("INFO: loading dependencies\n"), Ok(None));
    }

    #[test]
    fn port_zero_is_rejected_because_it_means_nothing_was_bound() {
        // A child that failed to bind can still print its template string.
        assert_eq!(scan("PRAISONAI_PORT=0\n"), Err(AnnounceError::NotBound));
    }

    #[test]
    fn two_different_ports_are_a_hard_error_not_a_pick() {
        // Log files are appended to. A stale line from the previous run sitting
        // above a live one is the normal case, not an exotic one -- and silently
        // taking either would send the first message to a coin flip.
        let out = "PRAISONAI_PORT=51234\nrestarting\nPRAISONAI_PORT=51999\n";
        assert_eq!(scan(out), Err(AnnounceError::Conflicting { first: 51234, second: 51999 }));
    }

    #[test]
    fn the_same_port_repeated_is_fine() {
        let out = "PRAISONAI_PORT=51234\nPRAISONAI_PORT=51234\n";
        assert_eq!(scan(out), Ok(Some(AnnouncedPort(51234))));
    }

    #[test]
    fn a_malformed_announcement_fails_rather_than_defaulting() {
        for bad in ["PRAISONAI_PORT=\n", "PRAISONAI_PORT=abc\n", "PRAISONAI_PORT=99999\n"] {
            assert!(
                matches!(scan(bad), Err(AnnounceError::Malformed(_))),
                "{bad:?} did not fail: {:?}",
                scan(bad)
            );
        }
    }

    #[test]
    fn an_unvalidated_port_cannot_be_used_without_a_probe() {
        // The type is the enforcement: confirm() is the only way to a u16 that a
        // connection can use, and it cannot run without the probe.
        let announced = scan("PRAISONAI_PORT=51234\n").unwrap().unwrap();
        assert_eq!(announced.confirm(|_| false), None, "a failed probe must yield no port");

        let announced = scan("PRAISONAI_PORT=51234\n").unwrap().unwrap();
        assert_eq!(announced.confirm(|p| p == 51234), Some(51234));
    }

    #[test]
    fn the_probe_receives_the_announced_port_not_a_default() {
        let announced = scan("PRAISONAI_PORT=51234\n").unwrap().unwrap();
        let mut seen = None;
        announced.confirm(|p| {
            seen = Some(p);
            true
        });
        assert_eq!(seen, Some(51234));
    }
}

#[cfg(test)]
mod loopback_literal {
    //! `localhost` resolves to `::1` before `127.0.0.1` on modern macOS, so a
    //! server that bound IPv4 is unreachable to a client that connected by name.
    //! It is a live, recurring bug class across shipped apps, and the fix is a
    //! two-minute rule: both ends use the literal address, never the name.

    /// Every source file in this crate, so the rule cannot be broken later.
    const SOURCES: &[(&str, &str)] = &[
        ("venv_resolve.rs", include_str!("venv_resolve.rs")),
        ("health.rs", include_str!("health.rs")),
        ("readiness.rs", include_str!("readiness.rs")),
        ("adopt.rs", include_str!("adopt.rs")),
        ("lockfile.rs", include_str!("lockfile.rs")),
        ("verify.rs", include_str!("verify.rs")),
        ("coalesce.rs", include_str!("coalesce.rs")),
    ];

    #[test]
    fn no_module_connects_by_hostname() {
        for (name, src) in SOURCES {
            for (n, line) in src.lines().enumerate() {
                // Skip whole-line comments only. Splitting on "//" would also
                // split "http://", hiding the very thing being looked for.
                if line.trim_start().starts_with("//") {
                    continue;
                }
                assert!(
                    !line.contains("localhost"),
                    "{name}:{} uses the name \"localhost\"; use the literal 127.0.0.1 so an \
                     IPv6-first resolver cannot send us somewhere the engine is not listening",
                    n + 1
                );
            }
        }
    }

    #[test]
    fn the_guard_would_catch_a_violation() {
        // Positive control: prove the check is capable of failing.
        let offending = "let url = format!(\"http://localhost:{port}\");";
        assert!(!offending.trim_start().starts_with("//"), "not a comment line");
        assert!(offending.contains("localhost"), "the guard must see through http://");
    }
}
