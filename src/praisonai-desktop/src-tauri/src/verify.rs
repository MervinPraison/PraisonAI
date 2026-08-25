//! Proving a resolved venv can actually run the engine.
//!
//! `venv_resolve` is filesystem-only by design: it decides which venv owns an
//! interpreter, and it runs on the launch path where spawning a process would be
//! too expensive. But a path existing is not the same as a venv importing. An
//! install interrupted partway leaves a directory tree that passes every
//! filesystem check and then crashes on first use.
//!
//! So readiness needs a second gate that executes the interpreter, and its
//! central rule is that **half-installed is Stale, not Ready** -- because
//! starting the engine against a partial venv just crashes it, and the crash
//! surfaces far from its cause.
//!
//! Distinguishing Stale from Broken matters: Stale can be repaired by re-running
//! the installer, Broken cannot and must be reported to the user.

/// Raw result of executing the probe, supplied by the caller.
pub enum ProbeOutcome {
    /// The interpreter could not be executed at all.
    CouldNotSpawn { reason: String },
    /// Ran, but did not finish inside the deadline. The child was killed.
    TimedOut { after_ms: u64 },
    /// Ran to completion.
    Exited { code: i32, stdout: String },
}

#[derive(Debug, PartialEq, Eq)]
pub enum VenvVerdict {
    /// Verified: the engine imports and reports a compatible protocol.
    Ready { protocol: u32 },
    /// Repairable by re-running the installer.
    Stale { reason: StaleReason },
    /// Not repairable by reinstalling; show the user.
    Broken { reason: String },
}

#[derive(Debug, PartialEq, Eq)]
pub enum StaleReason {
    /// The probe ran but reported the install did not complete.
    IncompleteInstall,
    /// A dependency present at install time is now gone.
    MissingDependency(String),
    /// Engine is older than this shell supports.
    ProtocolTooOld { found: u32, required: u32 },
}

pub const REQUIRED_PROTOCOL: u32 = 1;

/// Classify a probe. Never returns `Ready` on ambiguous evidence: an unparseable
/// or silent success is treated as Broken, because a probe that cannot say what
/// it found has not verified anything.
pub fn classify(outcome: ProbeOutcome) -> VenvVerdict {
    let (code, stdout) = match outcome {
        ProbeOutcome::CouldNotSpawn { reason } => {
            return VenvVerdict::Broken { reason: format!("interpreter did not start: {reason}") }
        }
        // A hung import is not a healthy one. Treating a timeout as success is
        // how a permanently-stalled engine reaches the chat window.
        ProbeOutcome::TimedOut { after_ms } => {
            return VenvVerdict::Broken { reason: format!("probe timed out after {after_ms}ms") }
        }
        ProbeOutcome::Exited { code, stdout } => (code, stdout),
    };

    if code != 0 {
        // A non-zero probe with a recognisable import failure is repairable.
        let lower = stdout.to_lowercase();
        if let Some(module) = missing_module(&lower) {
            return VenvVerdict::Stale { reason: StaleReason::MissingDependency(module) };
        }
        return VenvVerdict::Broken { reason: format!("probe exited {code}") };
    }

    let Some(install_ok) = field(&stdout, "install_ok") else {
        return VenvVerdict::Broken { reason: "probe reported no install_ok".to_string() };
    };
    if install_ok != "true" {
        return VenvVerdict::Stale { reason: StaleReason::IncompleteInstall };
    }

    let Some(protocol) = field(&stdout, "protocol").and_then(|v| v.parse::<u32>().ok()) else {
        return VenvVerdict::Broken { reason: "probe reported no usable protocol".to_string() };
    };
    if protocol < REQUIRED_PROTOCOL {
        return VenvVerdict::Stale {
            reason: StaleReason::ProtocolTooOld { found: protocol, required: REQUIRED_PROTOCOL },
        };
    }
    VenvVerdict::Ready { protocol }
}

fn missing_module(lower: &str) -> Option<String> {
    let idx = lower.find("no module named")?;
    let rest = &lower[idx + "no module named".len()..];
    let name: String =
        rest.trim().trim_start_matches(['\'', '"']).chars().take_while(|c| c.is_alphanumeric() || *c == '_').collect();
    (!name.is_empty()).then_some(name)
}

fn field(stdout: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let rest = &stdout[stdout.find(&needle)? + needle.len()..];
    let rest = rest.trim_start().strip_prefix(':')?.trim_start();
    let value: String = match rest.strip_prefix('"') {
        Some(q) => q.chars().take_while(|c| *c != '"').collect(),
        None => rest.chars().take_while(|c| !c.is_whitespace() && *c != ',' && *c != '}').collect(),
    };
    (!value.is_empty()).then_some(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn exited(code: i32, stdout: &str) -> ProbeOutcome {
        ProbeOutcome::Exited { code, stdout: stdout.to_string() }
    }

    #[test]
    fn a_complete_venv_is_ready() {
        let out = exited(0, r#"{"install_ok": true, "protocol": 1}"#);
        assert_eq!(classify(out), VenvVerdict::Ready { protocol: 1 });
    }

    #[test]
    fn half_installed_is_stale_not_ready() {
        // The rule this module exists for. Every path exists, the interpreter
        // runs, and the engine still cannot serve a request.
        let out = exited(0, r#"{"install_ok": false, "protocol": 1}"#);
        assert_eq!(classify(out), VenvVerdict::Stale { reason: StaleReason::IncompleteInstall });
    }

    #[test]
    fn a_dependency_removed_after_install_is_stale_and_names_itself() {
        // Repairable, and the user should be told which package, not just "broken".
        let out = exited(1, "ModuleNotFoundError: No module named 'litellm'");
        assert_eq!(
            classify(out),
            VenvVerdict::Stale { reason: StaleReason::MissingDependency("litellm".into()) }
        );
    }

    #[test]
    fn a_hung_probe_is_never_ready() {
        // Treating a timeout as success is how a permanently-stalled engine
        // reaches the chat window and hangs on the user's first message.
        let v = classify(ProbeOutcome::TimedOut { after_ms: 10_000 });
        assert!(matches!(v, VenvVerdict::Broken { .. }), "a timeout was not Broken: {v:?}");
    }

    #[test]
    fn a_silent_success_is_broken_not_ready() {
        // Exit 0 with nothing to say has verified nothing. The dangerous reading
        // is "no errors, therefore fine".
        for stdout in ["", "{}", "ok", r#"{"protocol": 1}"#] {
            let v = classify(exited(0, stdout));
            assert!(
                matches!(v, VenvVerdict::Broken { .. }),
                "empty probe output {stdout:?} classified as {v:?}"
            );
        }
    }

    #[test]
    fn install_ok_without_a_protocol_is_broken() {
        let v = classify(exited(0, r#"{"install_ok": true}"#));
        assert!(matches!(v, VenvVerdict::Broken { .. }));
    }

    #[test]
    fn an_old_engine_is_stale_and_reports_both_versions() {
        let out = exited(0, r#"{"install_ok": true, "protocol": 0}"#);
        assert_eq!(
            classify(out),
            VenvVerdict::Stale {
                reason: StaleReason::ProtocolTooOld { found: 0, required: REQUIRED_PROTOCOL }
            }
        );
    }

    #[test]
    fn an_interpreter_that_cannot_start_is_broken() {
        let v = classify(ProbeOutcome::CouldNotSpawn { reason: "ENOENT".into() });
        assert!(matches!(v, VenvVerdict::Broken { .. }));
    }

    #[test]
    fn stale_and_broken_are_never_conflated() {
        // They drive different UI: Stale offers Repair, Broken reports the fault.
        let stale = classify(exited(0, r#"{"install_ok": false, "protocol": 1}"#));
        let broken = classify(ProbeOutcome::TimedOut { after_ms: 1 });
        assert!(matches!(stale, VenvVerdict::Stale { .. }));
        assert!(matches!(broken, VenvVerdict::Broken { .. }));
        assert_ne!(stale, broken);
    }
}
