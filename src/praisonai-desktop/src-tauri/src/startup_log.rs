//! A breadcrumb written before anything can silently exit.
//!
//! The Windows first-run report was "double-click, nothing happens, no window,
//! no folder, no logs". The single-instance plugin exits a *secondary* launch
//! with code 0 after raising the window the first launch put in the tray, so a
//! bare `Start-Process -PassThru` handle can read `ExitCode=0` while the real
//! shell is alive and hidden -- indistinguishable, from the outside, from a
//! shell that started and died. The only way to tell those two apart after the
//! fact is a line on disk that says which launch this was, written *before* the
//! guard runs and before the window is built.
//!
//! Everything here is pure over its inputs so the path rule and the line format
//! are tested without a real filesystem, a real clock, or a real Windows.

use std::path::{Path, PathBuf};

use crate::platform::Platform;

/// Where the breadcrumb goes, chosen so it exists before `%APPDATA%\PraisonAI`
/// does: the whole point is to have a log when the data directory is absent.
///
/// The temp directory is passed in rather than read here so the choice is
/// testable; production passes `std::env::temp_dir()`, which honours `TEMP`
/// on Windows and `TMPDIR` elsewhere and always resolves to a writable place.
pub fn log_path(temp_dir: &Path) -> PathBuf {
    temp_dir.join("PraisonAI-startup.log")
}

/// One line describing a launch: the timestamp, whether this process is the
/// primary shell or a secondary that will be told to exit, and its pid.
///
/// `primary` is the fact the report was missing -- a secondary exiting 0 looks
/// like a crash unless the log says it was a secondary.
pub fn line(unix_secs: u64, platform: Platform, primary: bool, pid: u32) -> String {
    let role = if primary { "primary" } else { "secondary" };
    format!("{unix_secs}\t{}\t{role}\tpid={pid}\n", platform_tag(platform))
}

fn platform_tag(platform: Platform) -> &'static str {
    match platform {
        Platform::Windows => "windows",
        Platform::Mac => "macos",
        Platform::Linux => "linux",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_log_sits_in_temp_where_it_exists_before_appdata_does() {
        let got = log_path(Path::new(r"C:\Users\me\AppData\Local\Temp"));
        assert!(got.ends_with("PraisonAI-startup.log"), "{got:?}");
        assert!(
            got.to_string_lossy().contains("Temp"),
            "the breadcrumb must land somewhere writable without a data dir: {got:?}"
        );
    }

    #[test]
    fn a_secondary_launch_is_named_as_one() {
        // The exact confounder in the report: a secondary that exits 0 must be
        // distinguishable on disk from a shell that died.
        let l = line(1_700_000_000, Platform::Windows, false, 4242);
        assert!(l.contains("secondary"), "{l}");
        assert!(l.contains("pid=4242"), "{l}");
        assert!(l.contains("windows"), "{l}");
        assert!(l.ends_with('\n'), "each launch is its own line: {l:?}");
    }

    #[test]
    fn the_primary_launch_says_so() {
        let l = line(1_700_000_000, Platform::Mac, true, 7);
        assert!(l.contains("\tprimary\t"), "{l}");
        assert!(l.contains("macos"), "{l}");
    }

    #[test]
    fn the_timestamp_leads_so_the_lines_sort() {
        let l = line(1_700_000_123, Platform::Linux, true, 1);
        assert!(l.starts_with("1700000123\t"), "{l}");
    }
}
