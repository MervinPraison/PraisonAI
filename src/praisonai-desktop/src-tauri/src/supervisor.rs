//! Spawning the Python engine and learning where it listens.
//!
//! The shell's only job in the token path is to get the engine running and hand
//! the webview a validated port. After that the webview talks to the engine
//! directly over loopback and nothing streams through Tauri IPC.

use std::collections::BTreeMap;
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

use crate::port_announce::{scan, AnnounceError};
use crate::readiness::{classify_crash, is_ready_line};

pub struct Engine {
    pub port: u16,
    child: Child,
}

impl Engine {
    /// Stop the child and wait for it. Idempotent: a child that has already
    /// exited returns `Ok`, because "already gone" is the outcome we wanted.
    pub fn shutdown(&mut self) {
        // Ask first, briefly. A hard kill alone skipped the engine's own
        // cleanup, so every quit left a lockfile claiming a live engine.
        //
        // On Windows "ask" is taskkill /T, which is not graceful -- there is no
        // SIGTERM, and a console-less process has no window to send WM_CLOSE
        // to. The stale lockfile that leaves behind is harmless: `observe`
        // compares the recorded process start time, so a dead pid reads as
        // gone rather than as a live engine. /T matters more, because it takes
        // any training run the engine spawned with it.
        crate::reclaim::kill_pid(self.child.id());
        for _ in 0..40 {
            match self.child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) => std::thread::sleep(std::time::Duration::from_millis(50)),
                Err(_) => break,
            }
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        // Without this, dropping the handle detaches the process instead of
        // reaping it -- the app quits and Python keeps holding its port.
        self.shutdown();
    }
}

#[derive(Debug)]
pub enum StartError {
    Spawn(String),
    /// The child died before announcing. Carries the tail of its output, because
    /// a bare exit code is the least useful thing to show a user.
    ExitedEarly { status: String, tail: String },
    Crashed { reason: String, tail: String },
    Announce(AnnounceError),
    Timeout { tail: String },
}

/// Put the child in its own process group, so stopping it stops its children.
///
/// Without this, SIGTERM to the engine pid leaves anything the engine spawned
/// running -- and the engine spawns training runs, which hold a GPU.
fn detach_group(command: &mut Command) {
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    #[cfg(not(unix))]
    {
        let _ = command;
    }
}

/// Read lines, replacing undecodable bytes rather than stopping at them.
///
/// `BufRead::lines()` yields `Err(InvalidData)` on invalid UTF-8, and
/// `map_while(Result::ok)` *stops the iterator* on the first error rather than
/// skipping it -- so a single stray byte from a non-UTF-8 locale silently
/// ended the reader thread for the rest of the session. The port announcement
/// after it would never be seen, and the log would simply stop.
pub fn read_lines_lossy(stream: impl std::io::Read) -> impl Iterator<Item = String> {
    let mut reader = BufReader::new(stream);
    std::iter::from_fn(move || {
        let mut raw = Vec::new();
        match reader.read_until(b'\n', &mut raw) {
            Ok(0) => None,
            Ok(_) => {
                while matches!(raw.last(), Some(b'\n') | Some(b'\r')) {
                    raw.pop();
                }
                Some(String::from_utf8_lossy(&raw).into_owned())
            }
            Err(_) => None,
        }
    })
}

/// Start the engine, returning once it has announced a usable port.
///
/// Output is captured from the instant of spawn -- attaching a reader later is
/// how a first-run failure ends up reported as an exit code with no explanation.
pub fn start(
    python: &str,
    script: &str,
    timeout: Duration,
    shell_version: &str,
    env: &BTreeMap<String, String>,
) -> Result<Engine, StartError> {
    let mut command = Command::new(python);
    command
        .arg("-u") // unbuffered, or the announcement sits in a pipe buffer
        .arg(script)
        // The resolved environment, not the inherited one. An exported
        // PYTHONHOME or PYTHONPATH points the engine at another interpreter's
        // stdlib or site-packages, so the venv the resolver just proved is
        // discarded at spawn -- the module written to prevent exactly that
        // never ran. Clear first, then apply what `spawn_env` produced.
        .env_clear()
        .envs(env)
        // Force UTF-8 on both sides of the pipe. Python encodes redirected
        // streams with the locale code page on Windows -- cp1252, or cp932 on
        // a Japanese install -- and those bytes are not valid UTF-8. One of
        // them arriving before the port announcement makes startup fail at the
        // 30-second deadline with "Engine did not report ready in time", which
        // is a lie about what happened and depends on the user's locale.
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PRAISONAI_DESKTOP_VERSION", shell_version)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // No console window, and its own process group so stopping the engine also
    // stops what the engine spawned -- a training run must not outlive the app
    // holding a GPU.
    crate::reclaim::no_console(&mut command);
    detach_group(&mut command);
    let mut child = command.spawn().map_err(|e| StartError::Spawn(e.to_string()))?;

    let stdout = child.stdout.take().expect("piped");
    let stderr = child.stderr.take().expect("piped");
    let (tx, rx) = mpsc::channel::<String>();

    for (stream, tx) in [
        (Box::new(stdout) as Box<dyn std::io::Read + Send>, tx.clone()),
        (Box::new(stderr) as Box<dyn std::io::Read + Send>, tx),
    ] {
        std::thread::spawn(move || {
            for line in read_lines_lossy(stream) {
                if tx.send(line).is_err() {
                    break;
                }
            }
        });
    }

    let deadline = Instant::now() + timeout;
    let mut buffer = String::new();

    loop {
        if let Ok(line) = rx.recv_timeout(Duration::from_millis(120)) {
            buffer.push_str(&line);
            buffer.push('\n');

            let lower = line.to_lowercase();
            if let Some(crash) = classify_crash(&lower) {
                let _ = child.kill();
                return Err(StartError::Crashed {
                    reason: format!("{crash:?}"),
                    tail: tail(&buffer),
                });
            }

            match scan(&buffer) {
                Err(e) => {
                    let _ = child.kill();
                    return Err(StartError::Announce(e));
                }
                Ok(Some(announced)) => {
                    // A port parsed from a log line is a claim. Confirm it before
                    // handing it to the UI, or the first message goes to whatever
                    // else happens to be listening.
                    if let Some(port) = announced.confirm(|port| probe_health(port, shell_version)) {
                        return Ok(Engine { port, child });
                    }
                }
                Ok(None) => {}
            }

            if is_ready_line(&lower) && scan(&buffer).ok().flatten().is_none() {
                // Ready but no port: keep reading rather than guessing one.
                continue;
            }
        }

        if let Ok(Some(status)) = child.try_wait() {
            return Err(StartError::ExitedEarly {
                status: status.to_string(),
                tail: tail(&buffer),
            });
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            return Err(StartError::Timeout { tail: tail(&buffer) });
        }
    }
}

/// Confirm the engine answers on `port` with the shape and shell version we expect.
pub fn probe_health(port: u16, expected_shell_version: &str) -> bool {
    use std::io::{Read, Write};
    use std::net::TcpStream;

    let Ok(mut s) = TcpStream::connect(("127.0.0.1", port)) else {
        return false;
    };
    let _ = s.set_read_timeout(Some(Duration::from_millis(1500)));
    if s.write_all(
        b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
    )
    .is_err()
    {
        return false;
    }
    let mut body = String::new();
    let _ = s.read_to_string(&mut body);

    let status = body
        .split_whitespace()
        .nth(1)
        .and_then(|c| c.parse::<u16>().ok())
        .unwrap_or(0);
    let payload = body.split("\r\n\r\n").nth(1).unwrap_or("");

    crate::health::classify(
        crate::health::Probe::Responded { status, body: payload },
        crate::health::EXPECTED_VERSION,
    )
    .is_ok()
        && crate::health::shell_version_matches(payload, expected_shell_version)
}

fn tail(buffer: &str) -> String {
    buffer.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n")
}

#[cfg(test)]
mod lossy_reader {
    //! One undecodable byte must cost one character, not the whole session.
    use super::read_lines_lossy;

    #[test]
    fn a_bad_byte_does_not_end_the_stream() {
        // cp1252 output from a non-English Windows install. The previous reader
        // used lines().map_while(Result::ok), which *stops* on the first
        // Err(InvalidData) rather than skipping it -- so everything after this
        // byte, including the port announcement, was never seen, and startup
        // failed 30 seconds later blaming a timeout.
        let raw: &[u8] = b"before\n\xff\xfe bad\nPRAISONAI_PORT=54321\nafter\n";
        let lines: Vec<String> = read_lines_lossy(raw).collect();
        assert_eq!(lines.len(), 4, "{lines:?}");
        assert_eq!(lines[0], "before");
        assert!(lines[1].contains("bad"), "{:?}", lines[1]);
        assert_eq!(lines[2], "PRAISONAI_PORT=54321", "the port announcement was lost");
        assert_eq!(lines[3], "after");
    }

    #[test]
    fn ordinary_utf8_survives_unchanged() {
        let raw = "caf\u{e9} \u{2014} \u{1f9a5}\n".as_bytes();
        let lines: Vec<String> = read_lines_lossy(raw).collect();
        assert_eq!(lines, vec!["caf\u{e9} \u{2014} \u{1f9a5}"]);
    }

    #[test]
    fn windows_line_endings_leave_no_stray_carriage_return() {
        let raw: &[u8] = b"one\r\ntwo\r\n";
        let lines: Vec<String> = read_lines_lossy(raw).collect();
        assert_eq!(lines, vec!["one", "two"]);
    }

    #[test]
    fn a_final_line_without_a_newline_is_still_delivered() {
        // A crashing engine's last words usually arrive without a newline.
        let raw: &[u8] = b"traceback line";
        let lines: Vec<String> = read_lines_lossy(raw).collect();
        assert_eq!(lines, vec!["traceback line"]);
    }

    #[test]
    fn an_empty_stream_yields_nothing_rather_than_hanging() {
        let lines: Vec<String> = read_lines_lossy(&b""[..]).collect();
        assert!(lines.is_empty());
    }
}
