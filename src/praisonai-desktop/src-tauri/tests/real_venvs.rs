//! Runs the resolver against whatever venvs actually exist on this machine.
//!
//! Skips silently when none are present, so CI on a clean runner stays green,
//! but on a developer machine it is the test that would have caught a resolver
//! that only ever worked against a fixture.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use praisonai_desktop_core::platform::Platform;
use praisonai_desktop_core::venv_resolve::{spawn_env, venv_root_for_python, RealFs};

fn candidate_interpreters() -> Vec<PathBuf> {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repo root")
        .to_path_buf();
    let mut found = Vec::new();
    for relative in [
        "venv",
        "src/praisonai-agents/venv",
        "src/praisonai-agents/.venv",
        "src/praisonai/.venv",
        "src/praisonai-platform/.venv",
    ] {
        for exe in ["bin/python3", "bin/python"] {
            let path = repo.join(relative).join(exe);
            if path.is_file() {
                found.push(path);
                break;
            }
        }
    }
    found
}

#[test]
fn every_real_venv_resolves_to_itself_and_never_to_a_sibling() {
    let interpreters = candidate_interpreters();
    if interpreters.is_empty() {
        eprintln!("no venvs on this machine; skipping");
        return;
    }

    let mut seen_roots = Vec::new();
    for interpreter in &interpreters {
        let layout = venv_root_for_python(interpreter, &RealFs, Platform::current())
            .unwrap_or_else(|e| panic!("{}: {:?}", interpreter.display(), e));

        assert!(
            interpreter.starts_with(&layout.root),
            "resolved root {:?} does not contain the interpreter {:?}",
            layout.root,
            interpreter
        );
        assert!(
            layout.site_packages.starts_with(&layout.root),
            "site-packages {:?} escaped the venv {:?}",
            layout.site_packages,
            layout.root
        );

        let env = spawn_env(&layout, &BTreeMap::new(), Platform::current());
        assert_eq!(env["VIRTUAL_ENV"], layout.root.display().to_string());
        assert!(!env.contains_key("PYTHONPATH"));

        eprintln!(
            "{:<52} -> {} @ {}",
            interpreter.display(),
            layout.version,
            layout.root.display()
        );
        seen_roots.push(layout.root);
    }

    seen_roots.sort();
    let before = seen_roots.len();
    seen_roots.dedup();
    assert_eq!(before, seen_roots.len(), "two interpreters collapsed onto one venv root");
}

/// A poisoned PYTHONHOME/PYTHONPATH in the inherited environment must not reach
/// the spawned engine. `supervisor::start` applies the resolved environment
/// verbatim after `env_clear`, so what `spawn_env` strips is what the child
/// never sees. Before the fix the whole defence was dead code -- every caller
/// was a test -- and an exported PYTHONHOME redirected the engine's stdlib.
///
/// Driven through a real interpreter so it observes the child's *actual*
/// environment, not the map in isolation. Skips when no venv is present.
#[test]
fn a_poisoned_pythonhome_never_reaches_the_spawned_child() {
    let Some(interpreter) = candidate_interpreters().into_iter().next() else {
        eprintln!("no venvs on this machine; skipping");
        return;
    };

    let layout = venv_root_for_python(&interpreter, &RealFs, Platform::current())
        .expect("a real venv resolves");

    // Exactly the shape the audit describes: the vars a shell might export that
    // would point the engine at another interpreter.
    let inherited = BTreeMap::from([
        ("PYTHONHOME".to_string(), "/nonexistent".to_string()),
        ("PYTHONPATH".to_string(), "/some/other/venv/site-packages".to_string()),
    ]);
    let spawn = spawn_env(&layout, &inherited, Platform::current());

    // The map `supervisor::start` applies must have dropped both.
    assert!(!spawn.contains_key("PYTHONHOME"), "PYTHONHOME survived into the spawn env");
    assert!(!spawn.contains_key("PYTHONPATH"), "PYTHONPATH survived into the spawn env");

    // And prove it against a real process: run the resolved interpreter with the
    // resolved environment (the same `env_clear` + `envs` that `start` does) and
    // let Python report what it actually inherited.
    let output = std::process::Command::new(&interpreter)
        .arg("-c")
        .arg("import os; print(os.environ.get('PYTHONHOME','')); print(os.environ.get('PYTHONPATH',''))")
        .env_clear()
        .envs(&spawn)
        .output()
        .expect("the resolved interpreter runs");

    assert!(
        output.status.success(),
        "interpreter did not start under the resolved env: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let seen = String::from_utf8_lossy(&output.stdout);
    let mut lines = seen.lines();
    assert_eq!(lines.next().unwrap_or("").trim(), "", "the child inherited a poisoned PYTHONHOME");
    assert_eq!(lines.next().unwrap_or("").trim(), "", "the child inherited a poisoned PYTHONPATH");
}
