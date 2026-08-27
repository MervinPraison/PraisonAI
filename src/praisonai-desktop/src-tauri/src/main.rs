//! The PraisonAI desktop shell.
//!
//! Deliberately thin. Every decision worth testing lives in the pure modules of
//! `praisonai_desktop_core`, which have no I/O and no Tauri dependency; this file
//! only supplies the real filesystem and the window.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::{Path, PathBuf};

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use praisonai_desktop_core::adopt::Decision;
use tauri_plugin_window_state::{AppHandleExt, StateFlags};
use praisonai_desktop_core::platform::Platform;
use praisonai_desktop_core::reclaim::{kill_pid, no_console, reclaim};
use praisonai_desktop_core::engine_paths::{
    app_bundle, data_dir, python_candidates, resolve_engine, RealFs as PathFs,
};
use praisonai_desktop_core::supervisor::{self, Engine, StartError};
use praisonai_desktop_core::venv_resolve::{venv_root_for_python, RealFs};
use serde::Serialize;
use tauri::{Emitter, Manager};

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
    /// The child is *held*, not forgotten. `std::mem::forget` left one orphaned
    /// Python per launch: quitting the app dropped every handle to it without
    /// ever waiting on it, so `pgrep python` grew by one each time.
    engine: Mutex<Option<Engine>>,
}

/// The checkout this binary was built in -- development fallback only, and
/// only when it still exists. `resolve_engine` consults it last.
fn checkout_root() -> Option<PathBuf> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).ancestors().nth(3)?.to_path_buf();
    root.is_dir().then_some(root)
}

/// Say what happened to the previous run's engine. Silence here is how an
/// orphan goes unnoticed for weeks.
fn log_decision(d: &Decision) {
    eprintln!("[praisonai] previous engine: {d:?}");
}

fn env_path(key: &str) -> Option<PathBuf> {
    std::env::var_os(key).filter(|v| !v.is_empty()).map(PathBuf::from)
}

/// Pick the interpreter, and prove it owns its own site-packages before using it.
fn resolve_python(user_data: Option<&Path>) -> Result<PathBuf, String> {
    let candidates =
        python_candidates(env_path("PRAISONAI_PYTHON").as_deref(), user_data,
                          checkout_root().as_deref(), Platform::current());
    let mut tried = Vec::new();
    for candidate in candidates {
        if !candidate.is_file() {
            tried.push(candidate.display().to_string());
            continue;
        }
        // Keep looking. Returning on the first bad candidate let a
        // half-built user-space venv permanently mask a working checkout one.
        match venv_root_for_python(&candidate, &RealFs, Platform::current()) {
            Ok(layout) if layout.site_packages.starts_with(&layout.root) => return Ok(candidate),
            Ok(layout) => tried.push(format!(
                "{} (site-packages outside its venv: {})",
                candidate.display(),
                layout.site_packages.display()
            )),
            Err(e) => tried.push(format!("{} ({:?})", candidate.display(), e)),
        }
    }
    Err(format!("no usable Python found. Tried: {}", tried.join("; ")))
}

/// Build the engine's Python environment, reporting each step as it starts.
///
/// Emits `provision` events rather than returning a lump at the end: the whole
/// run takes minutes on a cold machine, and a window that says nothing for
/// three minutes is indistinguishable from one that has hung.
/// The user's home directory, under whichever variable this platform uses.
///
/// `HOME` is normally unset on Windows -- it is `USERPROFILE` -- so a lookup
/// that only knows the one name failed at the first step: no home, no data
/// directory, no engine, and the orphan-reclaim path never ran at all.
fn home_dir() -> Option<PathBuf> {
    let platform = Platform::current();
    // Empty is unset. The engine treats it that way (`if override:`), and for
    // XDG the spec requires it -- so without this filter the two sides pick
    // different directories from the same environment: `XDG_DATA_HOME=""`
    // makes Rust join onto an empty path and produce the *relative* path
    // "PraisonAI", so the shell looks for the lockfile in the working
    // directory while the engine writes it under the home directory. The
    // shell then decides "no lock, spawn" on every single launch.
    non_empty(platform.home_var()).or_else(|| non_empty("HOME"))
}

/// An environment variable as a path, treating empty exactly like unset.
fn non_empty(name: &str) -> Option<PathBuf> {
    std::env::var_os(name)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

/// %APPDATA% on Windows, $XDG_DATA_HOME on Linux, neither on macOS.
fn app_data_root() -> Option<PathBuf> {
    match Platform::current() {
        Platform::Windows => non_empty("APPDATA"),
        Platform::Linux => non_empty("XDG_DATA_HOME"),
        Platform::Mac => None,
    }
}

fn user_data_dir() -> Option<PathBuf> {
    data_dir(
        env_path("PRAISONAI_DESKTOP_HOME").as_deref(),
        home_dir().as_deref(),
        Platform::current(),
        app_data_root().as_deref(),
    )
}

#[tauri::command]
async fn provision_engine(app: tauri::AppHandle) -> Result<String, String> {
    use praisonai_desktop_core::provision::{
        locate_uv, plan, uv_candidates, uv_installer, venv_python, Uv, ENGINE_PACKAGES,
    };

    let platform = Platform::current();
    let home = home_dir().ok_or_else(|| "no home directory".to_string())?;
    let data = user_data_dir().ok_or_else(|| "no data directory".to_string())?;
    std::fs::create_dir_all(&data).map_err(|e| format!("cannot create {}: {e}", data.display()))?;

    let say = |id: &str, label: &str, state: &str, detail: &str| {
        let _ = app.emit("provision", serde_json::json!({
            "id": id, "label": label, "state": state, "detail": detail,
        }));
    };

    let uv = match locate_uv(&uv_candidates(&home, &data, platform), |p| p.is_file()) {
        Uv::Found(p) => p,
        Uv::Fetch => {
            // The official installer, run with an explicit target so it cannot
            // land somewhere outside the directory we control.
            say("uv", "Fetching the installer", "running", "");
            let installer = uv_installer(platform, &data.join(platform.venv_bin_rel()));
            let mut command = std::process::Command::new(&installer.program);
            command.args(&installer.args);
            for (key, value) in &installer.env {
                command.env(key, value);
            }
            no_console(&mut command);
            command
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::piped());

            let out = if let Some(url) = &installer.script_on_stdin {
                // Downloaded separately and piped in, so "could not reach
                // astral.sh" is distinguishable from "the installer failed".
                // `curl` by name, not /usr/bin/curl: it lives in /bin on some
                // distributions and is absent from minimal images entirely.
                let mut fetch = std::process::Command::new("curl");
                fetch.args(["-fsSL", url]);
                no_console(&mut fetch);
                let script = fetch
                    .output()
                    .map_err(|e| format!("could not reach astral.sh: {e}"))?;
                if !script.status.success() {
                    return Err("could not download the installer".into());
                }
                let mut child = command
                    .stdin(std::process::Stdio::piped())
                    .spawn()
                    .map_err(|e| format!("could not run the installer: {e}"))?;
                use std::io::Write;
                child.stdin.take().unwrap().write_all(&script.stdout)
                    .map_err(|e| format!("installer refused input: {e}"))?;
                child.wait_with_output().map_err(|e| e.to_string())?
            } else {
                command.output().map_err(|e| format!("could not run the installer: {e}"))?
            };
            if !out.status.success() {
                return Err(format!("installer failed: {}",
                    String::from_utf8_lossy(&out.stderr).lines().last().unwrap_or("")));
            }
            say("uv", "Fetching the installer", "done", "");
            let installed = data.join(platform.venv_bin_rel()).join(platform.uv_exe());
            // An exit code is not evidence. `powershell -Command "irm … | iex"`
            // can exit 0 having installed nothing -- a non-terminating error
            // does not set the exit status -- and the user then meets a
            // confusing failure at "Installing Python" rather than being told
            // the uv install is what went wrong.
            if !installed.is_file() {
                return Err(format!(
                    "the uv installer reported success but left nothing at {}",
                    installed.display()));
            }
            installed
        }
    };

    for step in plan(&uv, &data, ENGINE_PACKAGES, platform) {
        say(step.id, step.label, "running", "");
        let mut step_command = std::process::Command::new(&step.program);
        no_console(&mut step_command);
        let out = step_command
            .args(&step.args)
            .output()
            .map_err(|e| format!("{}: {e}", step.label))?;
        if !out.status.success() {
            // The last stderr line is what a user can act on; the rest is noise.
            let why = String::from_utf8_lossy(&out.stderr)
                .lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("").to_string();
            say(step.id, step.label, "failed", &why);
            return Err(format!("{} failed. {why}", step.label));
        }
        say(step.id, step.label, "done", "");
    }

    let py = venv_python(&data, platform);
    if !py.is_file() {
        return Err(format!("finished, but {} is not there", py.display()));
    }
    Ok(py.display().to_string())
}

#[tauri::command]
fn engine_status(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> EngineStatus {
    if let Some(engine) = state.engine.lock().unwrap().as_ref() {
        return EngineStatus::Ready { port: engine.port, python: "already running".into() };
    }

    // Not `app.path().app_data_dir()` -- that is the bundle identifier's
    // directory, which is not where the engine writes.
    let user_data = user_data_dir();
    let resource_dir = app.path().resource_dir().ok();

    praisonai_desktop_core::tray::set_engine_label(&app, "Engine: starting\u{2026}");
    let python = match resolve_python(user_data.as_deref()) {
        Ok(p) => p,
        Err(e) => {
            praisonai_desktop_core::tray::set_engine_label(&app, "Engine: no Python found");
            return EngineStatus::Failed {
                reason: "No usable Python".into(),
                detail: e,
                tail: String::new(),
            }
        }
    };
    // The engine exposes this beside its own package version in /health. Read
    // from Tauri package metadata, which the release workflow derives from the
    // tag, rather than from Cargo.toml's development-only package version.
    let shell_version = app.package_info().version.to_string();
    // Reap or adopt whatever the last run left. Neither `Drop` nor the reap on
    // exit runs when the shell is killed by a signal, and that was observed:
    // `kill -TERM` on the app left the Python child alive with a lockfile still
    // claiming it, and the next launch started a second engine beside it.
    if let Some(dir) = user_data.as_deref() {
        let venv = venv_root_for_python(&python, &RealFs, Platform::current())
            .map(|l| l.root.display().to_string())
            .unwrap_or_default();
        match reclaim(
            dir,
            &python.display().to_string(),
            &venv,
            |port| supervisor::probe_health(port, &shell_version),
            kill_pid,
        ) {
            Decision::Adopt { port } => {
                log_decision(&Decision::Adopt { port });
                praisonai_desktop_core::tray::set_engine_label(
                    &app, &format!("Engine: adopted on :{port}"));
                *state.engine.lock().unwrap() = None;
                return EngineStatus::Ready { port, python: python.display().to_string() };
            }
            other => log_decision(&other),
        }
    }

    let layout = match resolve_engine(
        env_path("PRAISONAI_ENGINE").as_deref(),
        resource_dir.as_deref(),
        checkout_root().as_deref(),
        &PathFs,
    ) {
        Ok(l) => l,
        Err(e) => {
            return EngineStatus::Failed {
                reason: "Engine not found".into(),
                detail: e,
                tail: String::new(),
            }
        }
    };

    // The engine writes the login item, and can only do so against a real
    // bundle -- so tell it whether there is one instead of letting it guess.
    match std::env::current_exe().ok().as_deref().and_then(app_bundle) {
        Some(b) => std::env::set_var("PRAISONAI_APP_BUNDLE", b),
        None => std::env::remove_var("PRAISONAI_APP_BUNDLE"),
    }
    match supervisor::start(
        &python.display().to_string(),
        &layout.script.display().to_string(),
        Duration::from_secs(30),
        &shell_version,
    ) {
        Ok(engine) => {
            let port = engine.port;
            *state.engine.lock().unwrap() = Some(engine);
            // The menubar read "Engine: starting..." forever: this function
            // existed and had no callers.
            praisonai_desktop_core::tray::set_engine_label(
                &app, &format!("Engine: ready on :{port}"));
            EngineStatus::Ready { port, python: python.display().to_string() }
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
            praisonai_desktop_core::tray::set_engine_label(
                &app, &format!("Engine: {reason}"));
            EngineStatus::Failed { reason, detail, tail }
        }
    }
}

/// Debounce flag for geometry saves; see the window event handler.
static SAVE_PENDING: AtomicBool = AtomicBool::new(false);

/// Leave a line on disk saying this launch happened, before anything can exit.
///
/// The Windows first-run report was a launch that left "no window, no folder,
/// no logs" -- and with the single-instance guard exiting a secondary with
/// code 0, there was no way after the fact to tell a shell that died from one
/// that simply handed off to the primary and quit. This writes that fact
/// somewhere that exists whether or not `%APPDATA%\PraisonAI` does. Best
/// effort: a shell must never fail to start because it could not write a log.
fn breadcrumb(primary: bool) {
    use praisonai_desktop_core::startup_log::{line, log_path};
    use std::io::Write;
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let entry = line(secs, Platform::current(), primary, std::process::id());
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path(&std::env::temp_dir()))
    {
        let _ = f.write_all(entry.as_bytes());
    }
}

fn main() {
    // Before the single-instance guard can quit this process: a launch that
    // hands off to the primary and exits 0 must still leave a trace, or it is
    // indistinguishable from one that crashed on the way up. Every launch
    // records itself as `secondary` here -- honest, because this process does
    // not yet know it is the first, and the pid is its own. The true primary
    // upgrades its own line from `setup()` below, which the single-instance
    // plugin runs only in the first instance. That keeps each line's pid and
    // role telling the truth about the *same* process: a secondary that exits 0
    // leaves `secondary pid=<its own>`, and the primary leaves `primary
    // pid=<its own>`. Writing `primary` here and `secondary` in the guard
    // callback (which runs in the primary, not the secondary) reversed both.
    breadcrumb(false);
    // First, before anything can open an X connection. GTK will not do this
    // for us and the failure without it is a silent exit(1) with no message.
    praisonai_desktop_core::x11_threads::init();
    tauri::Builder::default()
        // Must be registered first: the guard has to run before anything else
        // touches the lockfile or the engine.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // Runs in the *primary* when a secondary launches. The secondary has
            // already recorded its own `secondary` line and is exiting 0; the
            // primary already recorded its own `primary` line in `setup()`. Do
            // not write here: this process is the primary, and its pid is not
            // the secondary's, so any line written here would mislabel one of
            // them.
            //
            // A second launch raises the window that already exists rather than
            // starting a rival shell.
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // Only the first instance reaches `setup()`; a secondary is told to
            // exit by the guard before it gets here. So this is where the
            // primary honestly upgrades its own breadcrumb, with its own pid.
            breadcrumb(true);
            app.manage(AppState { engine: Mutex::new(None) });
            // Deliberately not `?`. On Linux the tray goes through
            // libappindicator, which is dlopen'd at first use and *panics* if
            // neither the ayatana nor the classic library is present -- and
            // with panic=abort that is not catchable. A missing tray would
            // take the whole app down before a window ever existed: the
            // package would install cleanly and then do nothing when clicked.
            // The same applies to a Wayland compositor with no tray protocol.
            // An app with no tray icon is a small loss; an app that will not
            // open is a total one.
            if let Err(e) = praisonai_desktop_core::tray::build(app.handle()) {
                eprintln!("tray unavailable, continuing without it: {e}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // With a menubar item present, closing the window means "put it
            // away", not "quit" -- tearing down an engine that takes seconds to
            // start because someone hit the red button is the wrong trade.
            // Persist geometry as it changes, not only at exit. Saving on
            // close and exit alone means a crash or a signal kill loses
            // whatever size the user chose -- and neither handler runs on
            // SIGTERM, which is how this went unverified in the first place.
            if matches!(event, tauri::WindowEvent::Moved(_) | tauri::WindowEvent::Resized(_)) {
                let app = window.app_handle().clone();
                // Coalesced: a drag emits these continuously, and each save is
                // a file write.
                if !SAVE_PENDING.swap(true, Ordering::SeqCst) {
                    std::thread::spawn(move || {
                        std::thread::sleep(Duration::from_millis(400));
                        SAVE_PENDING.store(false, Ordering::SeqCst);
                        let _ = app.save_window_state(StateFlags::all());
                    });
                }
            }
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // Save before hiding. The plugin persists on a real close, and
                // this window never has one -- so without this the geometry a
                // user chose is only ever written if the process happens to
                // exit cleanly, which a signal kill does not.
                let _ = window.app_handle().save_window_state(StateFlags::all());
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![engine_status, provision_engine])
        .build(tauri::generate_context!())
        .expect("error while building the PraisonAI desktop shell")
        .run(|app, event| {
            // Dropping managed state on exit is not guaranteed, so reap here
            // explicitly. Verified by `pgrep -f server.py` after quit.
            if matches!(event, tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit) {
                let _ = app.save_window_state(StateFlags::all());
                if let Some(state) = app.try_state::<AppState>() {
                    if let Some(mut engine) = state.engine.lock().unwrap().take() {
                        engine.shutdown();
                    }
                }
            }
        });
}
