//! Where the engine and its interpreter live -- resolved, not assumed.
//!
//! The previous shape baked `env!("CARGO_MANIFEST_DIR")` into the binary and
//! joined a checkout-relative path onto it. That works only on the machine that
//! ran `cargo build`: a shipped `.app` looks for the engine inside whatever
//! directory the build happened to use, finds nothing, and reports "no virtual
//! environment found in this checkout" to a user who never had a checkout.
//!
//! Everything here is pure over a `Fs` trait so the bundled case can be tested
//! on a machine that has no bundle.

use std::path::{Path, PathBuf};

use crate::platform::Platform;

pub trait Fs {
    fn is_file(&self, p: &Path) -> bool;
    fn is_dir(&self, p: &Path) -> bool;
}

pub struct RealFs;
impl Fs for RealFs {
    fn is_file(&self, p: &Path) -> bool {
        p.is_file()
    }
    fn is_dir(&self, p: &Path) -> bool {
        p.is_dir()
    }
}

/// What the shell was able to find, and where each part came from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Layout {
    pub script: PathBuf,
    /// How the script was found, for the failure message and for tests.
    pub origin: Origin,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Origin {
    /// `PRAISONAI_ENGINE` -- an explicit override always wins.
    Override,
    /// Bundled as a Tauri resource next to the executable. The shipping case.
    Resource,
    /// A source checkout. Development only.
    Checkout,
}

/// Search order: explicit override, then the bundle, then a checkout.
///
/// `resource_dir` is `app.path().resource_dir()`; `checkout_root` is the
/// compiled-in build path, which is consulted **last** and only if it still
/// exists, so a stale build path can never shadow a real bundle.
pub fn resolve_engine(
    env_override: Option<&Path>,
    resource_dir: Option<&Path>,
    checkout_root: Option<&Path>,
    fs: &impl Fs,
) -> Result<Layout, String> {
    if let Some(p) = env_override {
        return if fs.is_file(p) {
            Ok(Layout { script: p.to_path_buf(), origin: Origin::Override })
        } else {
            Err(format!("PRAISONAI_ENGINE is set to {} but no file is there", p.display()))
        };
    }
    if let Some(dir) = resource_dir {
        let p = dir.join("engine/server.py");
        if fs.is_file(&p) {
            return Ok(Layout { script: p, origin: Origin::Resource });
        }
    }
    if let Some(root) = checkout_root {
        let p = root.join("src/praisonai-desktop/engine/server.py");
        if fs.is_file(&p) {
            return Ok(Layout { script: p, origin: Origin::Checkout });
        }
    }
    Err("engine/server.py was not found in the app bundle or in a checkout".to_string())
}

/// Interpreter candidates, in the order a shipped app should try them.
///
/// User-space first: a notarized bundle cannot write inside itself, so the
/// provisioned venv lives in Application Support. The checkout venvs are the
/// development case and come after.
pub fn python_candidates(
    env_override: Option<&Path>,
    user_data: Option<&Path>,
    checkout_root: Option<&Path>,
    platform: Platform,
) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Some(p) = env_override {
        out.push(p.to_path_buf());
    }
    // A Windows venv keeps its interpreter in `Scripts\python.exe`. Looking
    // only for `bin/python3` meant every candidate failed `is_file()` and the
    // app reported "no usable Python found" on every launch, including
    // immediately after provisioning one successfully.
    let rel = platform.venv_python_rel();
    if let Some(d) = user_data {
        out.push(d.join("venv").join(rel));
    }
    if let Some(root) = checkout_root {
        for venv in ["src/praisonai-agents/.venv", "src/praisonai-agents/venv", "venv"] {
            out.push(root.join(venv).join(rel));
        }
    }
    out
}

/// Where the engine keeps its state -- the same rule the engine applies, so
/// both sides name the same directory.
///
/// Tauri's `app_data_dir()` returns a path built from the bundle identifier;
/// the engine uses `~/Library/Application Support/PraisonAI`. Using
/// `app_data_dir()` meant the shell looked for the lockfile somewhere the
/// engine never wrote one, so every launch decided `Spawn(NoLock)` and an
/// orphaned engine was never reclaimed.
pub fn data_dir(
    env_override: Option<&Path>,
    home: Option<&Path>,
    platform: Platform,
    app_data: Option<&Path>,
) -> Option<PathBuf> {
    if let Some(p) = env_override {
        return Some(p.to_path_buf());
    }
    // Must match `default_data_dir` in engine/server.py exactly. If the two
    // disagree the shell looks for a lockfile the engine never wrote there,
    // decides `Spawn(NoLock)` every launch, and orphans accumulate.
    match platform {
        Platform::Mac => home.map(|h| h.join("Library/Application Support/PraisonAI")),
        // %APPDATA% on Windows, $XDG_DATA_HOME on Linux -- passed in as
        // `app_data` so the lookup stays testable.
        Platform::Windows => app_data
            .map(Path::to_path_buf)
            .or_else(|| home.map(|h| h.join("AppData/Roaming")))
            .map(|base| base.join("PraisonAI")),
        Platform::Linux => app_data
            .map(Path::to_path_buf)
            .or_else(|| home.map(|h| h.join(".local/share")))
            .map(|base| base.join("PraisonAI")),
    }
}

/// The `.app` the executable is running from, if any.
///
/// `Foo.app/Contents/MacOS/foo` -> `Foo.app`. Returns `None` for a bare binary,
/// which is exactly what "launch at login is only available in the installed
/// app" needs to be able to say truthfully.
pub fn app_bundle(exe: &Path) -> Option<PathBuf> {
    exe.ancestors()
        .find(|a| a.extension().is_some_and(|e| e == "app"))
        .map(Path::to_path_buf)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    struct FakeFs {
        files: HashSet<PathBuf>,
    }
    impl FakeFs {
        fn new(paths: &[&str]) -> Self {
            Self { files: paths.iter().map(PathBuf::from).collect() }
        }
    }
    impl Fs for FakeFs {
        fn is_file(&self, p: &Path) -> bool {
            self.files.contains(p)
        }
        fn is_dir(&self, _p: &Path) -> bool {
            false
        }
    }

    // The regression this module exists for.
    #[test]
    fn bundled_app_finds_its_engine_with_no_checkout_present() {
        let fs = FakeFs::new(&["/Applications/PraisonAI.app/Contents/Resources/engine/server.py"]);
        let got = resolve_engine(
            None,
            Some(Path::new("/Applications/PraisonAI.app/Contents/Resources")),
            Some(Path::new("/Users/builder/praisonai-package")),
            &fs,
        )
        .unwrap();
        assert_eq!(got.origin, Origin::Resource);
    }

    #[test]
    fn a_stale_build_path_never_shadows_the_bundle() {
        let fs = FakeFs::new(&[
            "/Applications/PraisonAI.app/Contents/Resources/engine/server.py",
            "/Users/builder/praisonai-package/src/praisonai-desktop/engine/server.py",
        ]);
        let got = resolve_engine(
            None,
            Some(Path::new("/Applications/PraisonAI.app/Contents/Resources")),
            Some(Path::new("/Users/builder/praisonai-package")),
            &fs,
        )
        .unwrap();
        assert_eq!(got.origin, Origin::Resource, "the bundle must win");
    }

    #[test]
    fn checkout_is_used_when_there_is_no_bundle() {
        let fs = FakeFs::new(&["/repo/src/praisonai-desktop/engine/server.py"]);
        let got = resolve_engine(None, None, Some(Path::new("/repo")), &fs).unwrap();
        assert_eq!(got.origin, Origin::Checkout);
    }

    #[test]
    fn missing_everywhere_is_an_error_not_a_default_path() {
        let fs = FakeFs::new(&[]);
        let err = resolve_engine(None, Some(Path::new("/res")), Some(Path::new("/repo")), &fs)
            .unwrap_err();
        assert!(err.contains("not found"), "{err}");
    }

    #[test]
    fn override_wins_over_both() {
        let fs = FakeFs::new(&["/tmp/dev/server.py", "/res/engine/server.py"]);
        let got = resolve_engine(
            Some(Path::new("/tmp/dev/server.py")),
            Some(Path::new("/res")),
            None,
            &fs,
        )
        .unwrap();
        assert_eq!(got.origin, Origin::Override);
    }

    #[test]
    fn a_broken_override_fails_loudly_rather_than_falling_back() {
        // Silently ignoring a set-but-wrong override is how someone debugs the
        // wrong engine for an hour.
        let fs = FakeFs::new(&["/res/engine/server.py"]);
        let err =
            resolve_engine(Some(Path::new("/nope.py")), Some(Path::new("/res")), None, &fs)
                .unwrap_err();
        assert!(err.contains("PRAISONAI_ENGINE"), "{err}");
    }

    #[test]
    fn user_space_python_is_tried_before_any_checkout() {
        let c = python_candidates(
            None,
            Some(Path::new("/Users/me/Library/Application Support/PraisonAI")),
            Some(Path::new("/repo")),
            Platform::Mac,
        );
        assert!(c[0].starts_with("/Users/me/Library"), "{c:?}");
        assert!(c.iter().any(|p| p.starts_with("/repo")));
    }

    #[test]
    fn python_override_is_first() {
        let c = python_candidates(
            Some(Path::new("/usr/bin/python3")),
            Some(Path::new("/d")),
            None,
            Platform::Mac,
        );
        assert_eq!(c[0], PathBuf::from("/usr/bin/python3"));
    }

    #[test]
    fn a_windows_venv_is_looked_for_in_scripts_not_bin() {
        // Every candidate ended in bin/python3, so `is_file()` failed on all of
        // them and the app said "no usable Python found" even straight after
        // provisioning one successfully.
        let c = python_candidates(None, Some(Path::new(r"C:\d")), None, Platform::Windows);
        assert!(
            c.iter().all(|p| p.to_string_lossy().contains("Scripts")),
            "{c:?}"
        );
        assert!(
            !c.iter().any(|p| p.to_string_lossy().contains("bin/python3")),
            "{c:?}"
        );
    }

    #[test]
    fn linux_venvs_use_the_posix_layout() {
        let c = python_candidates(None, Some(Path::new("/home/me/.local/share/PraisonAI")), None,
                                  Platform::Linux);
        assert!(c[0].ends_with("venv/bin/python3"), "{c:?}");
    }

    #[test]
    fn the_data_dir_matches_what_the_engine_writes() {
        // engine/server.py: home / "Library/Application Support/PraisonAI"
        assert_eq!(
            data_dir(None, Some(Path::new("/Users/me")), Platform::Mac, None),
            Some(PathBuf::from("/Users/me/Library/Application Support/PraisonAI"))
        );
    }

    #[test]
    fn windows_keeps_its_data_in_appdata_not_a_library_folder() {
        let got = data_dir(
            None,
            Some(Path::new(r"C:\Users\me")),
            Platform::Windows,
            Some(Path::new(r"C:\Users\me\AppData\Roaming")),
        );
        let shown = got.as_ref().unwrap().to_string_lossy().to_string();
        assert!(shown.contains("AppData"), "{shown}");
        assert!(!shown.contains("Library"), "{shown}");
    }

    #[test]
    fn windows_without_appdata_still_lands_under_the_home_directory() {
        let got = data_dir(None, Some(Path::new(r"C:\Users\me")), Platform::Windows, None);
        let shown = got.as_ref().unwrap().to_string_lossy().to_string();
        assert!(shown.contains("AppData"), "{shown}");
        assert!(!shown.contains("Library"), "{shown}");
    }

    #[test]
    fn linux_follows_the_xdg_data_directory() {
        // A value that is NOT the fallback, so this proves the variable is
        // read rather than merely matching the default by coincidence.
        let got = data_dir(None, Some(Path::new("/home/me")), Platform::Linux,
                           Some(Path::new("/mnt/data/xdg")));
        assert_eq!(got, Some(PathBuf::from("/mnt/data/xdg/PraisonAI")));
    }

    #[test]
    fn linux_without_xdg_uses_the_spec_default() {
        assert_eq!(
            data_dir(None, Some(Path::new("/home/me")), Platform::Linux, None),
            Some(PathBuf::from("/home/me/.local/share/PraisonAI"))
        );
    }

    #[test]
    fn the_data_dir_honours_the_same_override_the_engine_does() {
        for platform in [Platform::Mac, Platform::Windows, Platform::Linux] {
            assert_eq!(
                data_dir(Some(Path::new("/tmp/alt")), Some(Path::new("/Users/me")), platform, None),
                Some(PathBuf::from("/tmp/alt")),
                "{platform:?}"
            );
        }
    }

    #[test]
    fn app_bundle_is_found_from_the_executable() {
        assert_eq!(
            app_bundle(Path::new("/Applications/PraisonAI.app/Contents/MacOS/praisonai")),
            Some(PathBuf::from("/Applications/PraisonAI.app"))
        );
    }

    #[test]
    fn a_bare_binary_has_no_bundle() {
        assert_eq!(app_bundle(Path::new("/repo/target/debug/praisonai")), None);
    }
}
