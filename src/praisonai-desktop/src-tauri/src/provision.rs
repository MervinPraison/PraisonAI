//! Building the engine's Python environment on a machine that has none.
//!
//! A notarized `.app` cannot write inside itself, and it cannot assume a
//! checkout exists -- so on a clean machine the shell finds its bundled engine
//! and then finds no interpreter to run it with. Until now that produced
//! "No usable Python", which is true and useless.
//!
//! The plan here mirrors what the reference apps do: locate or fetch `uv`,
//! have it install a managed CPython, create a venv in the user's data
//! directory, and install the engine's dependencies into it. Everything that
//! decides *what* to run is pure and tested; the process spawning lives in
//! `main.rs` where the real filesystem is.

use std::path::{Path, PathBuf};

/// One step, as the user sees it. The copy is deliberately about outcomes
/// rather than commands: "Installing Python" means something to someone who
/// does not know what a venv is.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Step {
    pub id: &'static str,
    pub label: &'static str,
    pub program: String,
    pub args: Vec<String>,
}

/// Where `uv` will be found or put.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Uv {
    /// Already on this machine; use it as-is.
    Found(PathBuf),
    /// Not present. Fetch the official installer into the app's data directory.
    Fetch,
}

/// Prefer an installed `uv` over downloading one. `candidates` is the PATH-like
/// list to check, in order.
pub fn locate_uv(candidates: &[PathBuf], exists: impl Fn(&Path) -> bool) -> Uv {
    for c in candidates {
        if exists(c) {
            return Uv::Found(c.clone());
        }
    }
    Uv::Fetch
}

/// The standard places `uv` lands, in the order they should be tried.
pub fn uv_candidates(home: &Path, data_dir: &Path) -> Vec<PathBuf> {
    vec![
        data_dir.join("bin/uv"),          // ours, from a previous provision
        home.join(".local/bin/uv"),       // the official installer's default
        PathBuf::from("/opt/homebrew/bin/uv"),
        PathBuf::from("/usr/local/bin/uv"),
    ]
}

/// Python version to provision.
///
/// Pinned rather than "latest": 3.13.8 shipped a torch import bug that the
/// reference installers work around by pinning too, and a first run is the
/// worst moment to discover a bad interpreter.
pub const PYTHON_VERSION: &str = "3.12";

/// The venv the engine will run from. Inside the user's data directory,
/// because a signed bundle is read-only and a checkout may not exist.
pub fn venv_dir(data_dir: &Path) -> PathBuf {
    data_dir.join("venv")
}

/// The interpreter that venv will contain, once built.
pub fn venv_python(data_dir: &Path) -> PathBuf {
    venv_dir(data_dir).join("bin/python3")
}

/// The whole plan, in order. `uv` is the resolved binary path.
pub fn plan(uv: &Path, data_dir: &Path, packages: &[&str]) -> Vec<Step> {
    let venv = venv_dir(data_dir);
    let s = |id, label, args: Vec<String>| Step {
        id,
        label,
        program: uv.display().to_string(),
        args,
    };
    let mut steps = vec![
        s(
            "python",
            "Installing Python",
            vec!["python".into(), "install".into(), PYTHON_VERSION.into()],
        ),
        s(
            "venv",
            "Creating the environment",
            vec![
                "venv".into(),
                "--python".into(),
                PYTHON_VERSION.into(),
                venv.display().to_string(),
            ],
        ),
    ];
    // One install invocation, not one per package: uv resolves the whole set
    // together, and N invocations can resolve to a conflicting closure.
    let mut install: Vec<String> = vec![
        "pip".into(),
        "install".into(),
        "--python".into(),
        venv_python(data_dir).display().to_string(),
    ];
    install.extend(packages.iter().map(|p| p.to_string()));
    steps.push(s("deps", "Installing PraisonAI", install));
    steps
}

/// What the engine needs to import. Kept here so the provisioning plan and the
/// failure message cannot disagree about it.
pub const ENGINE_PACKAGES: &[&str] = &["praisonaiagents"];

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    fn present(paths: &[&str]) -> impl Fn(&Path) -> bool {
        let set: HashSet<PathBuf> = paths.iter().map(PathBuf::from).collect();
        move |p: &Path| set.contains(p)
    }

    #[test]
    fn an_installed_uv_is_preferred_over_downloading_one() {
        let c = uv_candidates(Path::new("/Users/me"), Path::new("/data"));
        let got = locate_uv(&c, present(&["/opt/homebrew/bin/uv"]));
        assert_eq!(got, Uv::Found(PathBuf::from("/opt/homebrew/bin/uv")));
    }

    #[test]
    fn our_own_copy_wins_over_the_systems() {
        // A provision that already ran should not depend on a system uv that
        // might be upgraded or removed underneath it.
        let c = uv_candidates(Path::new("/Users/me"), Path::new("/data"));
        let got = locate_uv(&c, present(&["/data/bin/uv", "/opt/homebrew/bin/uv"]));
        assert_eq!(got, Uv::Found(PathBuf::from("/data/bin/uv")));
    }

    #[test]
    fn no_uv_anywhere_means_fetch() {
        let c = uv_candidates(Path::new("/Users/me"), Path::new("/data"));
        assert_eq!(locate_uv(&c, present(&[])), Uv::Fetch);
    }

    #[test]
    fn the_venv_lives_in_user_space_not_in_the_bundle() {
        // A notarized .app is read-only; writing a venv inside it fails at
        // install time on a machine that has never seen a developer build.
        let v = venv_dir(Path::new("/Users/me/Library/Application Support/PraisonAI"));
        assert!(v.starts_with("/Users/me/Library"), "{v:?}");
        assert!(!v.to_string_lossy().contains(".app"));
    }

    #[test]
    fn the_plan_is_python_then_venv_then_dependencies() {
        let steps = plan(Path::new("/uv"), Path::new("/data"), ENGINE_PACKAGES);
        assert_eq!(
            steps.iter().map(|s| s.id).collect::<Vec<_>>(),
            ["python", "venv", "deps"]
        );
    }

    #[test]
    fn dependencies_are_installed_in_one_resolution() {
        // Separate invocations can each succeed and still leave a closure that
        // does not resolve together.
        let steps = plan(Path::new("/uv"), Path::new("/data"), &["a", "b", "c"]);
        let deps: Vec<_> = steps.iter().filter(|s| s.id == "deps").collect();
        assert_eq!(deps.len(), 1);
        for p in ["a", "b", "c"] {
            assert!(deps[0].args.iter().any(|a| a == p), "{p} missing");
        }
    }

    #[test]
    fn the_install_targets_the_venv_we_just_made() {
        // Without --python, uv installs into whatever it considers current,
        // and the engine starts against an environment with no dependencies.
        let steps = plan(Path::new("/uv"), Path::new("/data"), ENGINE_PACKAGES);
        let deps = steps.iter().find(|s| s.id == "deps").unwrap();
        let i = deps.args.iter().position(|a| a == "--python").unwrap();
        assert_eq!(deps.args[i + 1], venv_python(Path::new("/data")).display().to_string());
    }

    #[test]
    fn every_step_has_copy_a_person_can_read() {
        for s in plan(Path::new("/uv"), Path::new("/data"), ENGINE_PACKAGES) {
            assert!(!s.label.is_empty());
            assert!(s.label.chars().next().unwrap().is_uppercase(), "{}", s.label);
            assert!(!s.label.contains("venv"), "jargon in user copy: {}", s.label);
            assert!(!s.label.contains("uv"), "jargon in user copy: {}", s.label);
        }
    }

    #[test]
    fn the_python_version_is_pinned() {
        assert!(PYTHON_VERSION.starts_with("3."), "{PYTHON_VERSION}");
        assert!(!PYTHON_VERSION.contains("latest"));
    }
}
