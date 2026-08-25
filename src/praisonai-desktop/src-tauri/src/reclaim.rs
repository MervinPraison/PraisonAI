//! Reclaiming an engine left behind by a previous run.
//!
//! `Engine::drop` and the reap on `RunEvent::Exit` handle an orderly quit, but
//! neither runs when the shell is killed by a signal or crashes -- and that was
//! observed, not theorised: `kill -TERM` on the app left the Python child
//! running and the lockfile claiming it was live. On the next launch a second
//! engine started alongside the first.
//!
//! So the lockfile is read at startup and acted on. This is what `lockfile.rs`
//! and `adopt.rs` were written for; until now nothing called either of them.

use std::path::{Path, PathBuf};

use crate::adopt::{decide, Decision, Expected, Observed, Rejected};
use crate::lockfile::{parse, LockState};

/// SIGTERM, so the engine's own cleanup runs.
pub fn kill_pid(pid: u32) {
    let _ = std::process::Command::new("/bin/kill")
        .args(["-TERM", &pid.to_string()])
        .status();
}

pub fn lock_path(data_dir: &Path) -> PathBuf {
    data_dir.join("engine.lock")
}

/// FNV-1a over the raw `ps -o lstart=` line.
///
/// Not a parsed timestamp. `ps` prints a locale-dependent date -- on this
/// machine "Tue 25 Aug 15:26:04 2026", day before month -- which neither
/// `strptime` nor `date -j -f "%a %b %e %T %Y"` accepts. Both sides fell back
/// to a different default, never agreed, and every live engine looked like a
/// recycled pid. Hashing the string sidesteps the format entirely; the engine
/// computes the identical hash from the identical bytes.
pub fn fnv1a64(text: &str) -> u64 {
    let mut h: u64 = 0xCBF2_9CE4_8422_2325;
    for b in text.as_bytes() {
        h ^= *b as u64;
        h = h.wrapping_mul(0x0000_0100_0000_01B3);
    }
    h
}

/// Ask the OS when a pid started, so a recycled pid is not mistaken for ours.
pub fn observe(pid: u32) -> Observed {
    let out = std::process::Command::new("/bin/ps")
        .args(["-o", "lstart=", "-p", &pid.to_string()])
        .output();
    match out {
        Ok(o) if o.status.success() => {
            let line = String::from_utf8_lossy(&o.stdout).trim().to_string();
            if line.is_empty() {
                Observed::NoSuchProcess
            } else {
                Observed::Running { start_time: fnv1a64(&line) }
            }
        }
        _ => Observed::NoSuchProcess,
    }
}

/// What to do about whatever the last run left behind.
/// `kill` is injected: a test that passed the real killer and its own pid
/// SIGTERM'd the test runner. Production passes [`kill_pid`].
pub fn reclaim(
    data_dir: &Path,
    interpreter: &str,
    venv_root: &str,
    health_ok: impl FnOnce(u16) -> bool,
    kill: impl FnOnce(u32),
) -> Decision {
    let path = lock_path(data_dir);
    let contents = std::fs::read_to_string(&path).ok();
    let state = parse(contents.as_deref());
    let lock = match &state {
        LockState::Present(l) => Some(l),
        // Corrupt or version-mismatched: a process may still be holding the
        // port and we cannot ask it anything, so respawning without clearing up
        // is how the orphan survives. Treat it as "nothing adoptable".
        _ => None,
    };
    let expected = Expected {
        interpreter,
        venv_root,
        // The engine hashes its settings; the shell does not read settings, so
        // it cannot compare. Pass the lock's own value: config drift is the
        // engine's business, and asserting on it here would reject every run.
        config_hash: lock.map(|l| l.config_hash.as_str()).unwrap_or(""),
    };
    let observed = lock.map(|l| observe(l.pid)).unwrap_or(Observed::NoSuchProcess);
    let decision = decide(lock, observed, expected, |l| health_ok(l.port));

    match (&decision, lock) {
        (Decision::KillAndRespawn(_), Some(l)) => {
            kill(l.pid);
            let _ = std::fs::remove_file(&path);
        }
        (Decision::Spawn(Rejected::NoLock), _) => {}
        (Decision::Spawn(_), _) => {
            let _ = std::fs::remove_file(&path);
        }
        _ => {}
    }
    decision
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::adopt::Lock;
    use crate::lockfile::render;

    fn tmp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("reclaim-test-{name}"));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn write(dir: &Path, pid: u32, start_time: u64, port: u16) {
        std::fs::write(
            lock_path(dir),
            render(&Lock {
                pid,
                start_time,
                port,
                interpreter: "/py".into(),
                venv_root: "/venv".into(),
                config_hash: "abc".into(),
            }),
        )
        .unwrap();
    }

    #[test]
    fn no_lockfile_means_spawn_and_nothing_to_clean() {
        let d = tmp("nolock");
        assert_eq!(reclaim(&d, "/py", "/venv", |_| true, |_| {}), Decision::Spawn(Rejected::NoLock));
    }

    #[test]
    fn a_lock_for_a_dead_process_is_removed_rather_than_left_to_rot() {
        let d = tmp("dead");
        // pid 1 is alive but its start time will not match, and a pid that has
        // certainly never existed keeps this deterministic.
        write(&d, 4_000_000, 1, 51089);
        let decision = reclaim(&d, "/py", "/venv", |_| true, |_| {});
        assert_eq!(decision, Decision::Spawn(Rejected::ProcessGone));
        assert!(!lock_path(&d).exists(), "the stale lock survived");
    }

    #[test]
    fn a_corrupt_lock_does_not_crash_and_still_spawns() {
        let d = tmp("corrupt");
        std::fs::write(lock_path(&d), "").unwrap();
        assert!(matches!(reclaim(&d, "/py", "/venv", |_| true, |_| {}), Decision::Spawn(_)));
    }

    #[test]
    fn an_unhealthy_engine_is_killed_not_adopted() {
        let d = tmp("unhealthy");
        let me = std::process::id();
        let start = match observe(me) {
            Observed::Running { start_time } => start_time,
            Observed::NoSuchProcess => panic!("this process should be observable"),
        };
        write(&d, me, start, 51089);
        // health_ok says no, so adopting would hand the user a dead port.
        let killed = std::cell::Cell::new(None);
        let decision = reclaim(&d, "/py", "/venv", |_| false, |p| killed.set(Some(p)));
        assert!(matches!(decision, Decision::KillAndRespawn(_)), "{decision:?}");
        assert_eq!(killed.get(), Some(me), "decided to kill, then killed nothing");
        assert!(!lock_path(&d).exists(), "the lock outlived the process it named");
    }

    #[test]
    fn a_healthy_engine_from_the_same_venv_is_adopted() {
        let d = tmp("adopt");
        let me = std::process::id();
        let start = match observe(me) {
            Observed::Running { start_time } => start_time,
            Observed::NoSuchProcess => panic!("this process should be observable"),
        };
        write(&d, me, start, 51089);
        assert_eq!(reclaim(&d, "/py", "/venv", |_| true, |_| {}), Decision::Adopt { port: 51089 });
        assert!(lock_path(&d).exists(), "an adopted engine's lock must stay");
    }

    #[test]
    fn a_different_venv_is_never_adopted() {
        let d = tmp("othervenv");
        let me = std::process::id();
        let start = match observe(me) {
            Observed::Running { start_time } => start_time,
            Observed::NoSuchProcess => panic!("observable"),
        };
        write(&d, me, start, 51089);
        let killed = std::cell::Cell::new(None);
        let decision = reclaim(&d, "/py", "/somewhere-else", |_| true, |p| killed.set(Some(p)));
        assert!(matches!(decision, Decision::KillAndRespawn(_)), "{decision:?}");
        assert_eq!(killed.get(), Some(me));
    }
}

#[cfg(test)]
mod hash_agreement {
    use super::fnv1a64;

    /// Values produced by the engine's `_fnv1a64` for the same inputs. If these
    /// ever disagree, a live engine is misread as a recycled pid and the app
    /// starts a second one beside it -- which is exactly what happened.
    #[test]
    fn matches_the_engines_fnv1a() {
        assert_eq!(fnv1a64(""), 0xcbf2_9ce4_8422_2325);
        assert_eq!(fnv1a64("a"), 0xaf63_dc4c_8601_ec8c);
        assert_eq!(fnv1a64("Tue 25 Aug 15:26:04 2026"), 0x1442_a707_ebec_e155);
    }
}
