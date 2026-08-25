//! Reading the engine's lockfile, distinguishing every way it can fail.
//!
//! The pattern this replaces is `except (OSError, ValueError): return None`
//! (praisonai_code/runtime/descriptor.py:136-153), which reports an unreadable
//! or corrupt lockfile as "no engine is running". Those need opposite responses:
//! absent means spawn, corrupt means the previous run died mid-write and its
//! process may still be holding the port. Collapsing them leaks an orphan every
//! time a write is interrupted.

use crate::adopt::Lock;

#[derive(Debug, PartialEq, Eq)]
pub enum LockState {
    /// No previous run. Spawn cleanly.
    Absent,
    /// Present and parseable.
    Present(Lock),
    /// Present but not valid: a partial write, or a foreign file at our path.
    /// A process may still be alive and unreachable, so this must be surfaced.
    Corrupt { reason: String },
    /// Written by a version whose fields we cannot rely on.
    Incompatible { found: u32, supported: u32 },
}

pub const LOCK_FORMAT_VERSION: u32 = 2;

/// Parse lockfile contents. `None` input means the file does not exist --
/// distinct from existing-but-empty, which is a truncated write.
pub fn parse(contents: Option<&str>) -> LockState {
    let Some(contents) = contents else {
        return LockState::Absent;
    };
    if contents.trim().is_empty() {
        // A zero-length file is the signature of a crash between create and
        // write. It is emphatically not "nothing was running".
        return LockState::Corrupt { reason: "empty file".to_string() };
    }

    let mut fields = std::collections::BTreeMap::new();
    for line in contents.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            return LockState::Corrupt { reason: format!("malformed line: {line:?}") };
        };
        fields.insert(key.trim().to_string(), value.trim().to_string());
    }

    let version = match fields.get("format_version").map(|v| v.parse::<u32>()) {
        Some(Ok(v)) => v,
        Some(Err(_)) => {
            return LockState::Corrupt { reason: "format_version is not a number".to_string() }
        }
        None => return LockState::Corrupt { reason: "missing format_version".to_string() },
    };
    if version != LOCK_FORMAT_VERSION {
        return LockState::Incompatible { found: version, supported: LOCK_FORMAT_VERSION };
    }

    macro_rules! required {
        ($name:literal, $ty:ty) => {
            match fields.get($name).map(|v| v.parse::<$ty>()) {
                Some(Ok(v)) => v,
                Some(Err(_)) => {
                    return LockState::Corrupt { reason: format!("{} is not valid", $name) }
                }
                None => return LockState::Corrupt { reason: format!("missing {}", $name) },
            }
        };
        ($name:literal) => {
            match fields.get($name) {
                Some(v) if !v.is_empty() => v.clone(),
                _ => return LockState::Corrupt { reason: format!("missing {}", $name) },
            }
        };
    }

    LockState::Present(Lock {
        pid: required!("pid", u32),
        start_time: required!("start_time", u64),
        port: required!("port", u16),
        interpreter: required!("interpreter"),
        venv_root: required!("venv_root"),
        config_hash: required!("config_hash"),
    })
}

/// Serialize a lock. Round-trips with `parse`.
pub fn render(lock: &Lock) -> String {
    format!(
        "format_version={}\npid={}\nstart_time={}\nport={}\ninterpreter={}\nvenv_root={}\nconfig_hash={}\n",
        LOCK_FORMAT_VERSION,
        lock.pid,
        lock.start_time,
        lock.port,
        lock.interpreter,
        lock.venv_root,
        lock.config_hash,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lock() -> Lock {
        Lock {
            pid: 4242,
            start_time: 1_700_000_000,
            interpreter: "/v/bin/python3".into(),
            venv_root: "/v".into(),
            config_hash: "abc123".into(),
            port: 51234,
        }
    }

    #[test]
    fn a_rendered_lock_parses_back_identically() {
        assert_eq!(parse(Some(&render(&lock()))), LockState::Present(lock()));
    }

    #[test]
    fn absent_and_corrupt_are_never_the_same_answer() {
        // The whole reason this module exists. Absent means spawn; corrupt means
        // a process may be alive and holding the port, and must be investigated.
        assert_eq!(parse(None), LockState::Absent);
        assert!(matches!(parse(Some("")), LockState::Corrupt { .. }));
        assert!(matches!(parse(Some("   \n  ")), LockState::Corrupt { .. }));
        assert_ne!(parse(Some("")), parse(None));
    }

    #[test]
    fn a_truncated_write_is_corrupt_not_present() {
        // Crash halfway through writing: the header landed, the rest did not.
        let full = render(&lock());
        let half = &full[..full.len() / 2];
        assert!(
            matches!(parse(Some(half)), LockState::Corrupt { .. }),
            "a half-written lock parsed as valid: {:?}",
            parse(Some(half))
        );
    }

    #[test]
    fn every_missing_required_field_is_caught() {
        // Guards against a field being added to Lock but not validated here,
        // which would let a default silently stand in for a real value.
        let full = render(&lock());
        for line in full.lines() {
            let key = line.split_once('=').unwrap().0;
            let without: String =
                full.lines().filter(|l| !l.starts_with(key)).collect::<Vec<_>>().join("\n");
            assert!(
                !matches!(parse(Some(&without)), LockState::Present(_)),
                "lock parsed as valid with {key:?} missing"
            );
        }
    }

    #[test]
    fn a_future_format_version_is_incompatible_not_corrupt() {
        // These differ: corrupt warrants investigating an orphan, incompatible
        // means a newer build wrote it and we should not guess at its fields.
        // Derived from the constant: hardcoding "1" here meant bumping the
        // format broke the test that guards the format.
        let bumped = render(&lock()).replace(
            &format!("format_version={LOCK_FORMAT_VERSION}"), "format_version=99");
        assert_eq!(
            parse(Some(&bumped)),
            LockState::Incompatible { found: 99, supported: LOCK_FORMAT_VERSION }
        );
    }

    #[test]
    fn garbage_at_our_path_is_corrupt_not_present() {
        for junk in ["\u{0}\u{0}\u{0}", "<html>404</html>", "pid", "{\"pid\": 1}"] {
            assert!(
                !matches!(parse(Some(junk)), LockState::Present(_)),
                "junk parsed as a valid lock: {junk:?}"
            );
        }
    }

    #[test]
    fn a_non_numeric_pid_is_rejected() {
        let bad = render(&lock()).replace("pid=4242", "pid=notapid");
        assert!(matches!(parse(Some(&bad)), LockState::Corrupt { .. }));
    }
}
