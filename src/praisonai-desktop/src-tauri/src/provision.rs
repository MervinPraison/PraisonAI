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

use crate::platform::Platform;

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
pub fn uv_candidates(home: &Path, data_dir: &Path, platform: Platform) -> Vec<PathBuf> {
    let exe = platform.uv_exe();
    let bin = platform.venv_bin_rel();
    let mut out = vec![
        data_dir.join(bin).join(exe),     // ours, from a previous provision
        home.join(".local/bin").join(exe), // the official installer's default
    ];
    match platform {
        Platform::Windows => {
            // Where uv's own installer and winget put it. The Homebrew paths
            // below do not exist on Windows and only slow the search down.
            out.push(home.join("AppData/Local/uv/bin").join(exe));
            out.push(home.join("AppData/Roaming/uv/bin").join(exe));
        }
        Platform::Mac => {
            out.push(PathBuf::from("/opt/homebrew/bin/uv"));
            out.push(PathBuf::from("/usr/local/bin/uv"));
        }
        Platform::Linux => {
            out.push(PathBuf::from("/usr/local/bin/uv"));
            out.push(PathBuf::from("/usr/bin/uv"));
        }
    }
    out
}

/// How to fetch `uv` when it is not already installed, per platform.
///
/// Astral publish two installers -- a shell script and a PowerShell script --
/// and there is no `/bin/sh` on Windows to run the first one with. The command
/// is returned as data rather than run here so the choice can be tested.
///
/// The PowerShell flags are deliberate. `-ExecutionPolicy RemoteSigned` rather
/// than `Bypass`, and no `-WindowStyle Hidden`: that pair is a known malware
/// detection signature and gets installers flagged. The console is suppressed
/// with a creation flag instead, which is not a behavioural signal.
pub fn uv_installer(platform: Platform, install_dir: &Path) -> UvInstaller {
    match platform {
        Platform::Windows => UvInstaller {
            program: "powershell.exe".into(),
            args: vec![
                "-NoLogo".into(),
                "-NoProfile".into(),
                "-NonInteractive".into(),
                "-ExecutionPolicy".into(),
                "RemoteSigned".into(),
                "-Command".into(),
                "irm https://astral.sh/uv/install.ps1 | iex".into(),
            ],
            env: uv_installer_env(install_dir),
            script_on_stdin: None,
        },
        _ => UvInstaller {
            program: "sh".into(),
            args: vec!["-s".into()],
            env: uv_installer_env(install_dir),
            // Downloaded separately and piped in, so the download failing is
            // distinguishable from the install failing.
            script_on_stdin: Some("https://astral.sh/uv/install.sh".into()),
        },
    }
}

fn uv_installer_env(install_dir: &Path) -> Vec<(String, String)> {
    vec![
        ("UV_INSTALL_DIR".into(), install_dir.display().to_string()),
        ("UV_UNMANAGED_INSTALL".into(), install_dir.display().to_string()),
        // Otherwise the installer edits the user's shell profiles, which is
        // not something an app should do to get its own dependency.
        ("UV_NO_MODIFY_PATH".into(), "1".into()),
    ]
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UvInstaller {
    pub program: String,
    pub args: Vec<String>,
    pub env: Vec<(String, String)>,
    /// A URL to download and feed to the program on stdin, if it needs one.
    pub script_on_stdin: Option<String>,
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
pub fn venv_python(data_dir: &Path, platform: Platform) -> PathBuf {
    venv_dir(data_dir).join(platform.venv_python_rel())
}

/// The whole plan, in order. `uv` is the resolved binary path.
pub fn plan(uv: &Path, data_dir: &Path, packages: &[&str], platform: Platform) -> Vec<Step> {
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
        venv_python(data_dir, platform).display().to_string(),
    ];
    install.extend(packages.iter().map(|p| p.to_string()));
    steps.push(s("deps", "Installing PraisonAI", install));
    steps
}

/// What the engine needs to import. Kept here so the provisioning plan and the
/// failure message cannot disagree about it.
// Pinned to a floor, not left open.
//
// The desktop app installs this once, on first run, and never again -- so an
// unpinned name resolves to whatever was on PyPI that day and stays there
// forever. 1.7.1 ends a tool-using turn without ever asking the model for its
// answer: the stream yields nothing, the engine reports "the engine produced
// no output", and the user sees a failure for a turn whose tools all ran. The
// fix is in 1.7.2.
//
// A floor rather than an exact pin, so a user who already has something newer
// is not downgraded.
pub const ENGINE_PACKAGES: &[&str] = &["praisonaiagents>=1.7.2"];

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
        let c = uv_candidates(Path::new("/Users/me"), Path::new("/data"), Platform::Mac);
        let got = locate_uv(&c, present(&["/opt/homebrew/bin/uv"]));
        assert_eq!(got, Uv::Found(PathBuf::from("/opt/homebrew/bin/uv")));
    }

    #[test]
    fn our_own_copy_wins_over_the_systems() {
        // A provision that already ran should not depend on a system uv that
        // might be upgraded or removed underneath it.
        let c = uv_candidates(Path::new("/Users/me"), Path::new("/data"), Platform::Mac);
        let got = locate_uv(&c, present(&["/data/bin/uv", "/opt/homebrew/bin/uv"]));
        assert_eq!(got, Uv::Found(PathBuf::from("/data/bin/uv")));
    }

    #[test]
    fn no_uv_anywhere_means_fetch() {
        let c = uv_candidates(Path::new("/Users/me"), Path::new("/data"), Platform::Mac);
        assert_eq!(locate_uv(&c, present(&[])), Uv::Fetch);
    }

    #[test]
    fn a_windows_venv_interpreter_is_scripts_python_exe() {
        // venv_python returned bin/python3 unconditionally, so after a
        // *successful* uv venv the app reported the interpreter "is not there".
        let p = venv_python(Path::new(r"C:\data"), Platform::Windows);
        let shown = p.to_string_lossy().to_string();
        assert!(shown.contains("Scripts"), "{shown}");
        assert!(shown.ends_with("python.exe"), "{shown}");
    }

    #[test]
    fn windows_looks_for_uv_where_windows_puts_it() {
        let c = uv_candidates(Path::new(r"C:\Users\me"), Path::new(r"C:\data"), Platform::Windows);
        let shown: Vec<String> = c.iter().map(|p| p.to_string_lossy().to_string()).collect();
        assert!(shown.iter().all(|p| p.ends_with("uv.exe")), "{shown:?}");
        assert!(shown.iter().any(|p| p.contains("AppData")), "{shown:?}");
        assert!(!shown.iter().any(|p| p.contains("homebrew")), "{shown:?}");
    }

    #[test]
    fn linux_does_not_search_homebrew() {
        let c = uv_candidates(Path::new("/home/me"), Path::new("/data"), Platform::Linux);
        let shown: Vec<String> = c.iter().map(|p| p.to_string_lossy().to_string()).collect();
        assert!(!shown.iter().any(|p| p.contains("homebrew")), "{shown:?}");
        assert!(shown.iter().any(|p| p.contains(".local/bin")), "{shown:?}");
    }

    #[test]
    fn windows_installs_uv_with_powershell_not_a_shell_that_does_not_exist() {
        let i = uv_installer(Platform::Windows, Path::new(r"C:\data\bin"));
        assert!(i.program.contains("powershell"), "{}", i.program);
        assert!(i.script_on_stdin.is_none(), "there is no /bin/sh to pipe into");
    }

    #[test]
    fn the_windows_installer_avoids_the_flags_that_get_it_flagged_as_malware() {
        // -WindowStyle Hidden together with -ExecutionPolicy Bypass is a known
        // detection signature. The console is suppressed with a creation flag.
        let i = uv_installer(Platform::Windows, Path::new(r"C:\data\bin"));
        assert!(!i.args.iter().any(|a| a == "Bypass"), "{:?}", i.args);
        assert!(!i.args.iter().any(|a| a.contains("Hidden")), "{:?}", i.args);
        assert!(i.args.iter().any(|a| a == "RemoteSigned"), "{:?}", i.args);
        assert!(i.args.iter().any(|a| a == "-NonInteractive"), "{:?}", i.args);
    }

    #[test]
    fn the_posix_installer_pipes_the_shell_script_in() {
        let i = uv_installer(Platform::Mac, Path::new("/data/bin"));
        assert_eq!(i.program, "sh");
        assert!(i.script_on_stdin.as_deref().unwrap().ends_with("install.sh"));
    }

    #[test]
    fn no_installer_edits_the_users_shell_profiles() {
        for platform in [Platform::Mac, Platform::Windows, Platform::Linux] {
            let i = uv_installer(platform, Path::new("/data/bin"));
            assert!(
                i.env.iter().any(|(k, v)| k == "UV_NO_MODIFY_PATH" && v == "1"),
                "{platform:?} would rewrite the user's rc files to install its own dependency"
            );
        }
    }

    #[test]
    fn every_installer_targets_the_directory_we_control() {
        for platform in [Platform::Mac, Platform::Windows, Platform::Linux] {
            let i = uv_installer(platform, Path::new("/data/bin"));
            assert!(i.env.iter().any(|(k, v)| k == "UV_INSTALL_DIR" && v.contains("/data/bin")),
                    "{platform:?}");
        }
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
        let steps = plan(Path::new("/uv"), Path::new("/data"), ENGINE_PACKAGES, Platform::Mac);
        assert_eq!(
            steps.iter().map(|s| s.id).collect::<Vec<_>>(),
            ["python", "venv", "deps"]
        );
    }

    #[test]
    fn dependencies_are_installed_in_one_resolution() {
        // Separate invocations can each succeed and still leave a closure that
        // does not resolve together.
        let steps = plan(Path::new("/uv"), Path::new("/data"), &["a", "b", "c"], Platform::Mac);
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
        let steps = plan(Path::new("/uv"), Path::new("/data"), ENGINE_PACKAGES, Platform::Mac);
        let deps = steps.iter().find(|s| s.id == "deps").unwrap();
        let i = deps.args.iter().position(|a| a == "--python").unwrap();
        assert_eq!(deps.args[i + 1], venv_python(Path::new("/data"), Platform::Mac).display().to_string());
    }

    #[test]
    fn every_step_has_copy_a_person_can_read() {
        for s in plan(Path::new("/uv"), Path::new("/data"), ENGINE_PACKAGES, Platform::Mac) {
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
