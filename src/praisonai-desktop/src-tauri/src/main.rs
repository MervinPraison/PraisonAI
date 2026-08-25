//! The PraisonAI desktop shell.
//!
//! Deliberately thin. Every decision worth testing lives in the pure modules of
//! `praisonai_desktop_core`, which have no I/O and no Tauri dependency; this file
//! only supplies the real filesystem and the window.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use std::sync::Mutex;
use std::time::Duration;

use praisonai_desktop_core::supervisor::{self, StartError};
use praisonai_desktop_core::venv_resolve::{venv_root_for_python, RealFs};
use serde::Serialize;
use tauri::Manager;

#[derive(Serialize)]
#[serde(tag = "state", rename_all = "snake_case")]
enum EngineStatus {
    /// Confirmed listening. The webview streams from this port directly.
    Ready { port: u16, python: String },
    /// Distinguishable failures, each with the child's own output attached --
    /// a bare exit code is the least useful thing to show a user.
    Failed { reason: String, detail: String, tail: String },
}

struct AppState {
    engine: Mutex<Option<u16>>,
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .map(Path::to_path_buf)
        .unwrap_or_default()
}

/// Pick the interpreter, and prove it owns its own site-packages before using it.
fn resolve_python() -> Result<PathBuf, String> {
    let repo = repo_root();
    for relative in ["src/praisonai-agents/.venv", "src/praisonai-agents/venv", "venv"] {
        let candidate = repo.join(relative).join("bin/python3");
        if !candidate.is_file() {
            continue;
        }
        match venv_root_for_python(&candidate, &RealFs) {
            Ok(layout) if layout.site_packages.starts_with(&layout.root) => return Ok(candidate),
            Ok(layout) => {
                return Err(format!(
                    "{} resolves to site-packages outside its own venv ({})",
                    candidate.display(),
                    layout.site_packages.display()
                ))
            }
            Err(e) => return Err(format!("{}: {:?}", candidate.display(), e)),
        }
    }
    Err("no virtual environment found in this checkout".to_string())
}

#[tauri::command]
fn engine_status(state: tauri::State<'_, AppState>) -> EngineStatus {
    if let Some(port) = *state.engine.lock().unwrap() {
        return EngineStatus::Ready { port, python: "already running".into() };
    }

    let python = match resolve_python() {
        Ok(p) => p,
        Err(e) => {
            return EngineStatus::Failed {
                reason: "No usable Python".into(),
                detail: e,
                tail: String::new(),
            }
        }
    };
    let script = repo_root().join("src/praisonai-desktop/engine/server.py");

    match supervisor::start(
        &python.display().to_string(),
        &script.display().to_string(),
        Duration::from_secs(30),
    ) {
        Ok(engine) => {
            *state.engine.lock().unwrap() = Some(engine.port);
            std::mem::forget(engine); // keep the child alive for the app's lifetime
            EngineStatus::Ready {
                port: *state.engine.lock().unwrap().as_ref().unwrap(),
                python: python.display().to_string(),
            }
        }
        Err(e) => {
            let (reason, detail, tail) = match e {
                StartError::Spawn(m) => ("Could not start Python".into(), m, String::new()),
                StartError::ExitedEarly { status, tail } => {
                    ("Engine exited before it was ready".into(), status, tail)
                }
                StartError::Crashed { reason, tail } => ("Engine crashed".into(), reason, tail),
                StartError::Announce(a) => ("Bad port announcement".into(), format!("{a:?}"), String::new()),
                StartError::Timeout { tail } => {
                    ("Engine did not report ready in time".into(), "30s".into(), tail)
                }
            };
            EngineStatus::Failed { reason, detail, tail }
        }
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            app.manage(AppState { engine: Mutex::new(None) });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![engine_status])
        .run(tauri::generate_context!())
        .expect("error while running the PraisonAI desktop shell");
}
