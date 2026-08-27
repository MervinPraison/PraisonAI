//! Which operating system we are running on, as a value rather than a `cfg`.
//!
//! Every path and process decision that differs between platforms goes through
//! a function taking one of these. `#[cfg(windows)]` would make the Windows
//! branches invisible to a test suite that only ever runs on macOS and Linux
//! CI -- which is precisely how the branches nobody runs come to be wrong.
//! Here they are ordinary code, and the tests pick the platform.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Platform {
    Mac,
    Windows,
    Linux,
}

impl Platform {
    /// The platform this binary was compiled for.
    pub const fn current() -> Self {
        #[cfg(target_os = "macos")]
        {
            Platform::Mac
        }
        #[cfg(target_os = "windows")]
        {
            Platform::Windows
        }
        #[cfg(not(any(target_os = "macos", target_os = "windows")))]
        {
            Platform::Linux
        }
    }

    pub const fn is_windows(self) -> bool {
        matches!(self, Platform::Windows)
    }

    /// The environment variable holding the user's home directory.
    ///
    /// `HOME` is normally unset on Windows, so a lookup that only knows that
    /// name fails at the first step: no home, no data directory, no engine,
    /// and the reclaim path never runs at all.
    pub const fn home_var(self) -> &'static str {
        match self {
            Platform::Windows => "USERPROFILE",
            _ => "HOME",
        }
    }

    /// Where a virtualenv puts its interpreter, relative to the venv root.
    pub const fn venv_python_rel(self) -> &'static str {
        match self {
            // Backslash on purpose: `Path::join` appends a relative path
            // verbatim, so a '/' here survives into the string the lockfile is
            // compared against -- and `sys.executable` is always backslashed on
            // Windows. `adopt::decide` also normalises separators, but keeping
            // the produced path canonical means the two agree at the source.
            Platform::Windows => "Scripts\\python.exe",
            _ => "bin/python3",
        }
    }

    /// Where a virtualenv puts its console scripts.
    pub const fn venv_bin_rel(self) -> &'static str {
        match self {
            Platform::Windows => "Scripts",
            _ => "bin",
        }
    }

    /// The separator between entries of the PATH variable.
    pub const fn path_separator(self) -> char {
        match self {
            Platform::Windows => ';',
            _ => ':',
        }
    }

    /// The filename `uv` is installed as.
    ///
    /// `uvw.exe` exists on Windows specifically because `uv.exe` flashes a
    /// console window even when it is launching a windowless interpreter, but
    /// the plain name is what the installer guarantees, so that is what we
    /// look for.
    pub const fn uv_exe(self) -> &'static str {
        match self {
            Platform::Windows => "uv.exe",
            _ => "uv",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn windows_looks_up_userprofile_not_home() {
        assert_eq!(Platform::Windows.home_var(), "USERPROFILE");
        assert_eq!(Platform::Mac.home_var(), "HOME");
        assert_eq!(Platform::Linux.home_var(), "HOME");
    }

    #[test]
    fn windows_venvs_keep_their_interpreter_in_scripts() {
        // Backslash-separated so the joined path matches the backslashed
        // `sys.executable` the engine records in its lockfile.
        assert_eq!(Platform::Windows.venv_python_rel(), "Scripts\\python.exe");
        assert_eq!(Platform::Mac.venv_python_rel(), "bin/python3");
    }

    #[test]
    fn path_is_semicolon_separated_on_windows_only() {
        assert_eq!(Platform::Windows.path_separator(), ';');
        assert_eq!(Platform::Mac.path_separator(), ':');
        assert_eq!(Platform::Linux.path_separator(), ':');
    }

    #[test]
    fn the_compiled_platform_is_one_of_the_three() {
        let me = Platform::current();
        assert!(matches!(me, Platform::Mac | Platform::Windows | Platform::Linux));
        assert_eq!(me.is_windows(), cfg!(target_os = "windows"));
    }
}
