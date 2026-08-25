//! Spawning the Python engine and learning where it listens.
//!
//! The shell's only job in the token path is to get the engine running and hand
//! the webview a validated port. After that the webview talks to the engine
//! directly over loopback and nothing streams through Tauri IPC.

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

/// Start the engine, returning once it has announced a usable port.
///
/// Output is captured from the instant of spawn -- attaching a reader later is
/// how a first-run failure ends up reported as an exit code with no explanation.
pub fn start(python: &str, script: &str, timeout: Duration) -> Result<Engine, StartError> {
    let mut child = Command::new(python)
        .arg("-u") // unbuffered, or the announcement sits in a pipe buffer
        .arg(script)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| StartError::Spawn(e.to_string()))?;

    let stdout = child.stdout.take().expect("piped");
    let stderr = child.stderr.take().expect("piped");
    let (tx, rx) = mpsc::channel::<String>();

    for (stream, tx) in [
        (Box::new(stdout) as Box<dyn std::io::Read + Send>, tx.clone()),
        (Box::new(stderr) as Box<dyn std::io::Read + Send>, tx),
    ] {
        std::thread::spawn(move || {
            for line in BufReader::new(stream).lines().map_while(Result::ok) {
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
                    if let Some(port) = announced.confirm(|p| probe_health(p)) {
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

/// Confirm the engine answers on `port` with the shape we expect.
pub fn probe_health(port: u16) -> bool {
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
}

fn tail(buffer: &str) -> String {
    buffer.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n")
}
