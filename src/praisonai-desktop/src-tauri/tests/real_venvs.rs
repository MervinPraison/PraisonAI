//! Runs the resolver against whatever venvs actually exist on this machine.
//!
//! Skips silently when none are present, so CI on a clean runner stays green,
//! but on a developer machine it is the test that would have caught a resolver
//! that only ever worked against a fixture.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

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
        let layout = venv_root_for_python(interpreter, &RealFs)
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

        let env = spawn_env(&layout, &BTreeMap::new());
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
