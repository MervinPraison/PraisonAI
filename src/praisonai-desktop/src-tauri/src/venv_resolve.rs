//! One function decides which Python the backend runs, and it returns the
//! interpreter and the site-packages that belong to the *same* venv.
//!
//! Splitting that decision across two call sites is the defect this module
//! exists to prevent. On a developer machine with several venvs it has two
//! failure modes, and the second is the dangerous one:
//!
//!   loud   -- 3.14 interpreter against 3.13 site-packages: the ABI differs and
//!             the import of a native wheel fails immediately.
//!   silent -- 3.13.2 against 3.13.7: both resolve to `lib/python3.13/site-packages`,
//!             the ABI matches, nothing raises, and the process runs against
//!             dependencies it never resolved.

use crate::platform::Platform;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Filesystem reads this module needs, injected so tests need no real venv.
pub trait VenvFs {
    fn is_file(&self, path: &Path) -> bool;
    fn read_to_string(&self, path: &Path) -> Option<String>;
}

#[derive(Debug, PartialEq, Eq)]
pub struct VenvLayout {
    pub root: PathBuf,
    pub interpreter: PathBuf,
    pub site_packages: PathBuf,
    pub version: String,
}

#[derive(Debug, PartialEq, Eq)]
pub enum VenvError {
    NotInsideVenv { interpreter: PathBuf },
    MissingConfig { expected: PathBuf },
    UnreadableConfig { path: PathBuf },
    NoVersionInConfig { path: PathBuf },
}

/// Variables that let a coherent venv still import another venv's packages.
/// They are removed rather than overwritten: an empty value is not the same as
/// absent, and only absence is reliably ignored by CPython.
const POISONING_VARS: [&str; 3] = ["PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"];

/// Resolve the venv that owns `interpreter`, returning the interpreter and the
/// site-packages that belong to the same root.
///
/// Errors are distinct rather than collapsed into `None`, because the caller
/// must restart in one case and refuse in another.
pub fn venv_root_for_python(
    interpreter: &Path,
    fs: &dyn VenvFs,
    platform: Platform,
) -> Result<VenvLayout, VenvError> {
    let root = interpreter
        .ancestors()
        .skip(1)
        .find(|dir| fs.is_file(&dir.join("pyvenv.cfg")))
        .ok_or_else(|| VenvError::NotInsideVenv { interpreter: interpreter.to_path_buf() })?;

    let config_path = root.join("pyvenv.cfg");
    let contents = fs
        .read_to_string(&config_path)
        .ok_or_else(|| VenvError::UnreadableConfig { path: config_path.clone() })?;

    let version = parse_version(&contents)
        .ok_or_else(|| VenvError::NoVersionInConfig { path: config_path.clone() })?;

    // A Windows venv is `Lib\site-packages` with no version segment; the
    // POSIX layout is `lib/python3.13/site-packages`. Deriving the POSIX shape
    // on Windows produced a path that does not exist -- and the caller's only
    // check is that it sits under the venv root, so the guard passed while
    // pointing at nothing, which is worse than failing.
    let site_packages = match platform {
        Platform::Windows => root.join("Lib").join("site-packages"),
        _ => root
            .join("lib")
            .join(format!("python{}", major_minor(&version)))
            .join("site-packages"),
    };

    Ok(VenvLayout {
        root: root.to_path_buf(),
        interpreter: interpreter.to_path_buf(),
        site_packages,
        version,
    })
}

/// `pyvenv.cfg` spells the version two ways depending on the tool that wrote it:
/// stdlib `venv` writes `version`, `uv` writes `version_info`.
fn parse_version(contents: &str) -> Option<String> {
    contents.lines().find_map(|line| {
        let (key, value) = line.split_once('=')?;
        match key.trim() {
            "version" | "version_info" => {
                let value = value.trim();
                (!value.is_empty()).then(|| value.to_string())
            }
            _ => None,
        }
    })
}

fn major_minor(version: &str) -> String {
    let mut parts = version.split('.');
    match (parts.next(), parts.next()) {
        (Some(major), Some(minor)) => format!("{major}.{minor}"),
        _ => version.to_string(),
    }
}

/// Build the environment for spawning the backend from `layout`.
///
/// Activation is expressed the way CPython itself defines it -- `VIRTUAL_ENV`
/// plus the venv's `bin` at the front of `PATH` -- and never by injecting
/// site-packages onto `PYTHONPATH`. That distinction is the whole point: a
/// `PYTHONPATH` entry is additive, so it can only ever *add* a second venv's
/// packages to a resolution order that already had its own.
pub fn spawn_env(
    layout: &VenvLayout,
    inherited: &BTreeMap<String, String>,
    platform: Platform,
) -> BTreeMap<String, String> {
    let mut env: BTreeMap<String, String> = inherited
        .iter()
        .filter(|(key, _)| !POISONING_VARS.contains(&key.as_str()))
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect();

    let bin = layout.root.join(platform.venv_bin_rel());
    let separator = platform.path_separator();
    let path = match inherited.get("PATH") {
        Some(existing) => format!("{}{separator}{}", bin.display(), existing),
        None => bin.display().to_string(),
    };

    env.insert("VIRTUAL_ENV".to_string(), layout.root.display().to_string());
    env.insert("PATH".to_string(), path);
    env
}

#[cfg(test)]
mod platform_layout {
    //! The two places a venv's layout differs between platforms.
    use super::*;
    use std::collections::BTreeMap;

    fn windows_layout() -> VenvLayout {
        VenvLayout {
            root: PathBuf::from("C:/data/venv"),
            interpreter: PathBuf::from("C:/data/venv/Scripts/python.exe"),
            site_packages: PathBuf::from("C:/data/venv/Lib/site-packages"),
            version: "3.12.4".to_string(),
        }
    }

    #[test]
    fn windows_path_entries_are_separated_by_semicolons() {
        // Joining with ':' turns the whole PATH into one unusable entry, and
        // nothing reports it -- the venv's tools simply are not found.
        let inherited: BTreeMap<String, String> =
            [("PATH".to_string(), "C:/Windows/System32".to_string())]
                .into_iter()
                .collect();
        // The whole value, not a substring search: a drive letter contains a
        // colon of its own, so "does it contain ':'" cannot tell a separator
        // from a path and would pass either way.
        let env = spawn_env(&windows_layout(), &inherited, Platform::Windows);
        // Split on the separator rather than comparing the whole string: the
        // separator *between entries* is what this is about, and asserting the
        // whole value also pins the separator *inside* a path, which is the
        // host's business -- PathBuf::join writes a backslash when the tests
        // themselves run on Windows, and this failed there for that reason
        // while the product was correct.
        let entries: Vec<&str> = env["PATH"].split(';').collect();
        assert_eq!(entries.len(), 2, "PATH did not split into two entries: {}", env["PATH"]);
        assert!(entries[0].ends_with("Scripts"), "{}", entries[0]);
        assert_eq!(entries[1], "C:/Windows/System32");
    }

    #[test]
    fn windows_prepends_scripts_not_bin() {
        let env = spawn_env(&windows_layout(), &BTreeMap::new(), Platform::Windows);
        assert!(env["PATH"].contains("Scripts"), "{}", env["PATH"]);
    }

    #[test]
    fn posix_still_uses_colons_and_bin() {
        let inherited: BTreeMap<String, String> =
            [("PATH".to_string(), "/usr/bin".to_string())].into_iter().collect();
        let layout = VenvLayout {
            root: PathBuf::from("/data/venv"),
            interpreter: PathBuf::from("/data/venv/bin/python3"),
            site_packages: PathBuf::from("/data/venv/lib/python3.12/site-packages"),
            version: "3.12.4".to_string(),
        };
        let env = spawn_env(&layout, &inherited, Platform::Mac);
        let entries: Vec<&str> = env["PATH"].split(':').collect();
        assert_eq!(entries.len(), 2, "PATH did not split into two entries: {}", env["PATH"]);
        assert!(entries[0].ends_with("bin"), "{}", entries[0]);
        assert_eq!(entries[1], "/usr/bin");
    }

    #[test]
    fn a_windows_venv_derives_lib_site_packages_with_no_version_segment() {
        // Forward slashes, which Windows accepts equally: `Path::ancestors`
        // splits on the *host* separator, so a backslash path is a single
        // component when this runs on macOS or Linux CI. What is under test is
        // which directory names are chosen, not how Windows parses a
        // separator -- that is only ever exercised on Windows itself.
        struct Fs;
        impl VenvFs for Fs {
            fn is_file(&self, p: &Path) -> bool {
                p == Path::new("C:/data/venv/pyvenv.cfg")
            }
            fn read_to_string(&self, p: &Path) -> Option<String> {
                if p == Path::new("C:/data/venv/pyvenv.cfg") {
                    Some("version = 3.12.4\n".to_string())
                } else {
                    None
                }
            }
        }
        let layout = venv_root_for_python(
            Path::new("C:/data/venv/Scripts/python.exe"),
            &Fs,
            Platform::Windows,
        )
        .expect("a real Windows venv layout should resolve");
        let shown = layout.site_packages.to_string_lossy().to_string();
        assert!(shown.contains("Lib"), "{shown}");
        assert!(!shown.contains("python3.12"), "no version segment on Windows: {shown}");
        // The caller's only check is that it sits under the root, so a wrong
        // path passes the guard while pointing at nothing.
        assert!(layout.site_packages.starts_with(&layout.root), "{shown}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// In-memory filesystem: `path -> contents`. Directories are implied.
    struct FakeFs(BTreeMap<PathBuf, String>);

    impl FakeFs {
        fn with(files: &[(&str, &str)]) -> Self {
            FakeFs(files.iter().map(|(p, c)| (PathBuf::from(p), c.to_string())).collect())
        }
    }

    impl VenvFs for FakeFs {
        fn is_file(&self, path: &Path) -> bool {
            self.0.contains_key(path)
        }
        fn read_to_string(&self, path: &Path) -> Option<String> {
            self.0.get(path).cloned()
        }
    }

    /// The layout actually present on a PraisonAI developer machine: four venvs,
    /// four Python versions, two of which share a site-packages path.
    fn real_world_fs() -> FakeFs {
        FakeFs::with(&[
            // /repo is itself a venv, so interpreters below it have two ancestor
            // venvs. Nested venvs are not hypothetical: ~/.praisonai ships one.
            ("/repo/pyvenv.cfg", "home = /opt/py311/bin\nversion = 3.11.13\n"),
            ("/repo/bin/python3", ""),
            ("/repo/venv/pyvenv.cfg", "home = /opt/py314/bin\nversion = 3.14.3\n"),
            ("/repo/venv/bin/python3", ""),
            ("/repo/src/praisonai-agents/venv/pyvenv.cfg", "home = /opt/py3132/bin\nversion = 3.13.2\n"),
            ("/repo/src/praisonai-agents/venv/bin/python3", ""),
            ("/repo/src/praisonai-agents/.venv/pyvenv.cfg", "home = /opt/py3137/bin\nversion_info = 3.13.7\n"),
            ("/repo/src/praisonai-agents/.venv/bin/python3", ""),
        ])
    }

    #[test]
    fn venv_root_for_python_returns_the_venv_that_owns_the_interpreter() {
        let fs = real_world_fs();
        let layout =
            venv_root_for_python(Path::new("/repo/src/praisonai-agents/venv/bin/python3"), &fs, Platform::Mac)
                .expect("interpreter is inside a venv");

        // 1. the root is the venv containing the interpreter, not the outermost venv
        assert_eq!(layout.root, PathBuf::from("/repo/src/praisonai-agents/venv"));
        // 2. the interpreter is the one we asked about
        assert_eq!(
            layout.interpreter,
            PathBuf::from("/repo/src/praisonai-agents/venv/bin/python3")
        );
        // 3. site-packages is derived from that same root, never from another venv
        assert_eq!(
            layout.site_packages,
            PathBuf::from("/repo/src/praisonai-agents/venv/lib/python3.13/site-packages")
        );
        // 4. the spawn environment cannot point elsewhere -- this is the assertion
        //    that catches the silent case, where paths match but the venv does not
        let env = spawn_env(&layout, &BTreeMap::new(), Platform::Mac);
        assert_eq!(env.get("VIRTUAL_ENV").map(String::as_str), Some("/repo/src/praisonai-agents/venv"));
    }

    #[test]
    fn the_silent_case_two_venvs_sharing_a_site_packages_path_stay_distinct() {
        // 3.13.2 and 3.13.7 both write lib/python3.13/site-packages. The ABI
        // matches, so pairing them raises nothing at all -- only the venv root
        // distinguishes them.
        let fs = real_world_fs();
        let a = venv_root_for_python(Path::new("/repo/src/praisonai-agents/venv/bin/python3"), &fs, Platform::Mac).unwrap();
        let b = venv_root_for_python(Path::new("/repo/src/praisonai-agents/.venv/bin/python3"), &fs, Platform::Mac).unwrap();

        assert_eq!(
            a.site_packages.strip_prefix(&a.root),
            b.site_packages.strip_prefix(&b.root),
            "precondition: both venvs really do use the same relative site-packages path"
        );
        assert_ne!(a.root, b.root, "the two venvs must never collapse into one");
        assert_ne!(a.site_packages, b.site_packages, "absolute paths must stay distinct");
        assert_ne!(a.version, b.version);
    }

    #[test]
    fn a_nested_venv_resolves_to_the_innermost_one_that_owns_the_interpreter() {
        // The outer venv is a real venv on a real ancestor path. Walking to the
        // outermost match instead of the nearest yields a 3.11 site-packages for
        // a 3.13 interpreter -- coherent-looking, and wrong.
        let fs = real_world_fs();
        let layout =
            venv_root_for_python(Path::new("/repo/src/praisonai-agents/venv/bin/python3"), &fs, Platform::Mac)
                .unwrap();

        assert_eq!(layout.root, PathBuf::from("/repo/src/praisonai-agents/venv"));
        assert_ne!(layout.root, PathBuf::from("/repo"), "must not walk past the owning venv");
        assert_eq!(layout.version, "3.13.2");
        assert!(
            layout.site_packages.starts_with("/repo/src/praisonai-agents/venv"),
            "site-packages escaped the owning venv: {:?}",
            layout.site_packages
        );
    }

    #[test]
    fn an_interpreter_outside_any_venv_is_an_error_not_a_guess() {
        let fs = real_world_fs();
        let err = venv_root_for_python(Path::new("/usr/bin/python3"), &fs, Platform::Mac)
            .expect_err("a system interpreter owns no venv");
        assert_eq!(
            err,
            VenvError::NotInsideVenv { interpreter: PathBuf::from("/usr/bin/python3") }
        );
    }

    #[test]
    fn a_venv_missing_its_version_is_an_error_not_a_default() {
        let fs = FakeFs::with(&[
            ("/repo/broken/pyvenv.cfg", "home = /opt/py/bin\n"),
            ("/repo/broken/bin/python3", ""),
        ]);
        let err = venv_root_for_python(Path::new("/repo/broken/bin/python3"), &fs, Platform::Mac)
            .expect_err("no version means we cannot know site-packages");
        assert_eq!(
            err,
            VenvError::NoVersionInConfig { path: PathBuf::from("/repo/broken/pyvenv.cfg") }
        );
    }

    #[test]
    fn spawn_env_removes_inherited_pythonpath() {
        // An inherited PYTHONPATH is how a coherent venv still ends up importing
        // another venv's packages. The fix is to never carry it, not to overwrite it.
        let fs = real_world_fs();
        let layout = venv_root_for_python(Path::new("/repo/venv/bin/python3"), &fs, Platform::Mac).unwrap();
        let inherited = BTreeMap::from([
            ("PYTHONPATH".to_string(), "/some/other/venv/site-packages".to_string()),
            ("PYTHONHOME".to_string(), "/opt/py311".to_string()),
            ("HOME".to_string(), "/Users/x".to_string()),
        ]);
        let env = spawn_env(&layout, &inherited, Platform::Mac);

        assert!(!env.contains_key("PYTHONPATH"), "PYTHONPATH must be removed, not overwritten");
        assert!(!env.contains_key("PYTHONHOME"), "PYTHONHOME redirects the stdlib and must be removed");
        assert_eq!(env.get("HOME").map(String::as_str), Some("/Users/x"), "unrelated vars pass through");
    }
}

/// The real filesystem. Kept trivial on purpose: everything worth testing lives
/// in `venv_root_for_python`, which never touches it directly.
pub struct RealFs;

impl VenvFs for RealFs {
    fn is_file(&self, path: &Path) -> bool {
        path.is_file()
    }
    fn read_to_string(&self, path: &Path) -> Option<String> {
        std::fs::read_to_string(path).ok()
    }
}
