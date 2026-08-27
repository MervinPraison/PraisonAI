//! Deciding whether an engine process left behind by a previous run may be reused.
//!
//! When the shell is SIGKILLed the child is never reaped: it keeps the port and
//! the memory. On next launch we find a lockfile pointing at a live PID. Adopting
//! it blindly is unsafe, and killing it blindly makes every crash cost a restart.
//!
//! Modelled on jan's `try_adopt_router`
//! (jan/src-tauri/plugins/tauri-plugin-llamacpp/src/router.rs:359-422). The gate
//! that matters most is `start_time`: PIDs are recycled, so a live PID alone
//! proves nothing about whether it is *our* process. Anything failing a gate is
//! killed rather than adopted -- a half-matching process is not a cheaper win, it
//! is a process running someone else's code against our port.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Lock {
    pub pid: u32,
    /// Process start time. The PID-reuse guard: a recycled PID belongs to a
    /// process that started later, so a mismatch means ours is gone.
    pub start_time: u64,
    pub interpreter: String,
    pub venv_root: String,
    pub config_hash: String,
    pub port: u16,
}

/// What the OS says about the PID in the lock, supplied by the caller.
pub enum Observed {
    NoSuchProcess,
    Running { start_time: u64 },
}

#[derive(Debug, PartialEq, Eq)]
pub enum Decision {
    Adopt { port: u16 },
    /// Kill the process, then spawn fresh. Carries why, for the log.
    KillAndRespawn(Rejected),
    /// Nothing to kill; just spawn.
    Spawn(Rejected),
}

#[derive(Debug, PartialEq, Eq)]
pub enum Rejected {
    NoLock,
    ProcessGone,
    PidReused,
    DifferentInterpreter,
    DifferentVenv,
    ConfigChanged,
    UnhealthyProbe,
}

/// The expected identity of an adoptable engine.
pub struct Expected<'a> {
    pub interpreter: &'a str,
    pub venv_root: &'a str,
    pub config_hash: &'a str,
}

/// Decide what to do about a possibly-live previous engine.
///
/// `health_ok` is evaluated last and only when every cheap gate has passed, so a
/// probe is never sent to a process we already know is not ours.
pub fn decide(
    lock: Option<&Lock>,
    observed: Observed,
    expected: Expected<'_>,
    health_ok: impl FnOnce(&Lock) -> bool,
) -> Decision {
    let Some(lock) = lock else {
        return Decision::Spawn(Rejected::NoLock);
    };

    let start_time = match observed {
        Observed::NoSuchProcess => return Decision::Spawn(Rejected::ProcessGone),
        Observed::Running { start_time } => start_time,
    };

    if start_time != lock.start_time {
        // Someone else now owns this PID. Killing it would kill an unrelated
        // process, so this is the one rejection that must never escalate to a kill.
        return Decision::Spawn(Rejected::PidReused);
    }
    if !same_path(&lock.interpreter, expected.interpreter) {
        return Decision::KillAndRespawn(Rejected::DifferentInterpreter);
    }
    if !same_path(&lock.venv_root, expected.venv_root) {
        return Decision::KillAndRespawn(Rejected::DifferentVenv);
    }
    if lock.config_hash != expected.config_hash {
        return Decision::KillAndRespawn(Rejected::ConfigChanged);
    }
    if !health_ok(lock) {
        return Decision::KillAndRespawn(Rejected::UnhealthyProbe);
    }
    Decision::Adopt { port: lock.port }
}

/// Two spellings of one path. The lockfile records the engine's `sys.executable`
/// verbatim -- fully backslashed on Windows -- while the expected value is built
/// by joining a relative `venv_python_rel` that may still carry a `/`. A byte
/// mismatch there is not a different engine, it is a different separator or
/// letter case, and treating it as different escalates to `taskkill /T`, which
/// takes the running trainer with it. On Windows we therefore fold `/` to `\`
/// and lower-case (its filesystem is case-insensitive); elsewhere the path is
/// case-sensitive and separators are already canonical, so we compare as-is.
fn same_path(a: &str, b: &str) -> bool {
    #[cfg(windows)]
    let norm = |s: &str| s.replace('/', "\\").to_lowercase();
    #[cfg(not(windows))]
    let norm = |s: &str| s.to_string();
    norm(a) == norm(b)
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
    fn expected<'a>() -> Expected<'a> {
        Expected { interpreter: "/v/bin/python3", venv_root: "/v", config_hash: "abc123" }
    }
    fn running() -> Observed {
        Observed::Running { start_time: 1_700_000_000 }
    }

    #[test]
    fn a_matching_healthy_process_is_adopted() {
        let l = lock();
        assert_eq!(decide(Some(&l), running(), expected(), |_| true), Decision::Adopt { port: 51234 });
    }

    #[test]
    fn a_recycled_pid_is_never_adopted_and_never_killed() {
        // The whole point of start_time. The PID is live, every other field
        // matches the lock -- but it is a different process now. Killing it would
        // terminate an unrelated program on the user's machine.
        let l = lock();
        let reused = Observed::Running { start_time: 1_700_009_999 };
        assert_eq!(decide(Some(&l), reused, expected(), |_| true), Decision::Spawn(Rejected::PidReused));
    }

    #[test]
    fn health_is_probed_only_after_identity_matches() {
        // A probe against a process that is not ours is both useless and a write
        // to a port we do not own. If any identity gate fails, the closure must
        // never run.
        let mut l = lock();
        l.venv_root = "/other".into();
        let decision = decide(Some(&l), running(), expected(), |_| {
            panic!("health probe ran against a process that failed an identity gate")
        });
        assert_eq!(decision, Decision::KillAndRespawn(Rejected::DifferentVenv));
    }

    #[test]
    fn an_engine_from_a_different_venv_is_killed_not_reused() {
        // This is the desktop form of the venv-coherence bug: yesterday's engine
        // is alive and answers health checks, but it imports another venv's
        // packages. It looks perfectly healthy and is silently wrong.
        let mut l = lock();
        l.interpreter = "/older-venv/bin/python3".into();
        assert_eq!(
            decide(Some(&l), running(), expected(), |_| true),
            Decision::KillAndRespawn(Rejected::DifferentInterpreter)
        );
    }

    #[test]
    fn a_config_change_forces_a_restart() {
        let mut l = lock();
        l.config_hash = "stale".into();
        assert_eq!(
            decide(Some(&l), running(), expected(), |_| true),
            Decision::KillAndRespawn(Rejected::ConfigChanged)
        );
    }

    #[test]
    fn a_live_matching_but_unhealthy_process_is_killed() {
        let l = lock();
        assert_eq!(
            decide(Some(&l), running(), expected(), |_| false),
            Decision::KillAndRespawn(Rejected::UnhealthyProbe)
        );
    }

    #[test]
    fn absent_or_dead_means_spawn_with_nothing_to_kill() {
        let l = lock();
        assert_eq!(decide(None, running(), expected(), |_| true), Decision::Spawn(Rejected::NoLock));
        assert_eq!(
            decide(Some(&l), Observed::NoSuchProcess, expected(), |_| true),
            Decision::Spawn(Rejected::ProcessGone)
        );
    }

    #[cfg(windows)]
    #[test]
    fn a_windows_engine_is_adopted_across_separator_and_case_spellings() {
        // The dead-adopt bug: the lock records the backslashed, lower-drive
        // `sys.executable`; the expected value is the '/'-joined path built from
        // `venv_python_rel`. Byte-comparing them always said DifferentInterpreter
        // and taskkill'd a healthy engine (and its trainer) every launch.
        let l = Lock {
            interpreter: r"C:\app\venv\Scripts\python.exe".into(),
            venv_root: r"C:\app\venv".into(),
            ..lock()
        };
        let e = Expected {
            interpreter: "C:\\app\\venv/Scripts/python.exe",
            venv_root: "C:\\app\\venv",
            config_hash: "abc123",
        };
        assert_eq!(decide(Some(&l), running(), e, |_| true), Decision::Adopt { port: 51234 });
    }

    #[test]
    fn same_path_is_exact_off_windows_and_separator_insensitive_on_it() {
        assert!(same_path("/v/bin/python3", "/v/bin/python3"));
        if cfg!(windows) {
            assert!(same_path(r"C:\v\Scripts\python.exe", "C:\\v/Scripts/python.exe"));
            assert!(same_path(r"C:\V\Scripts\Python.exe", r"c:\v\scripts\python.exe"));
        } else {
            // POSIX paths are case-sensitive and already '/'-separated.
            assert!(!same_path("/V/bin/python3", "/v/bin/python3"));
        }
    }

    #[test]
    fn adoption_requires_every_gate_not_merely_a_live_pid() {
        // Guards against a future refactor collapsing the gates into "is it alive".
        let l = lock();
        let mismatches: Vec<Expected> = vec![
            Expected { interpreter: "/x", venv_root: "/v", config_hash: "abc123" },
            Expected { interpreter: "/v/bin/python3", venv_root: "/x", config_hash: "abc123" },
            Expected { interpreter: "/v/bin/python3", venv_root: "/v", config_hash: "x" },
        ];
        for e in mismatches {
            assert!(
                !matches!(decide(Some(&l), running(), e, |_| true), Decision::Adopt { .. }),
                "a mismatching process was adopted"
            );
        }
    }
}
