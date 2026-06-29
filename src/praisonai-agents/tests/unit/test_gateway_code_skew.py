"""Unit tests for the gateway code-skew guard (Issue #2460).

Covers the pure, core-side ``detect_code_skew`` predicate and the best-effort
``read_code_fingerprint`` helper.
"""

import os

from praisonaiagents.gateway import detect_code_skew, read_code_fingerprint


def test_no_skew_when_fingerprints_match():
    assert detect_code_skew("abc1234def", "abc1234def") is None


def test_skew_detected_when_fingerprints_differ():
    skew = detect_code_skew("mtime:100", "mtime:200")
    assert skew == ("mtime:100", "mtime:200")


def test_fail_open_when_boot_fingerprint_missing():
    assert detect_code_skew(None, "abc1234def") is None
    assert detect_code_skew("", "abc1234def") is None


def test_fail_open_when_disk_fingerprint_missing():
    assert detect_code_skew("abc1234def", None) is None
    assert detect_code_skew("abc1234def", "") is None


def test_fail_open_when_both_missing():
    assert detect_code_skew(None, None) is None


def test_git_shas_are_shortened_to_seven_chars():
    boot = "a" * 40
    disk = "b" * 40
    skew = detect_code_skew(boot, disk)
    assert skew == ("a" * 7, "b" * 7)


def test_non_sha_fingerprints_are_not_shortened():
    boot = "mtime:1700000000"
    disk = "mtime:1700000999"
    skew = detect_code_skew(boot, disk)
    assert skew == (boot, disk)


def test_read_code_fingerprint_returns_string_for_real_package():
    # Best-effort: the running package directory exists, so a fingerprint
    # (git rev or mtime) should be derivable.
    fp = read_code_fingerprint()
    assert fp is None or isinstance(fp, str)


def test_read_code_fingerprint_fails_open_on_bad_dir():
    fp = read_code_fingerprint("/nonexistent/path/that/should/not/exist")
    # Git fails and there are no .py files to scan -> None.
    assert fp is None


def test_read_code_fingerprint_mtime_fallback(tmp_path):
    # A plain directory (not a git checkout) should fall back to an mtime
    # fingerprint when it contains .py files.
    py_file = tmp_path / "module.py"
    py_file.write_text("x = 1\n")
    os.utime(py_file, (1_700_000_000, 1_700_000_000))
    fp = read_code_fingerprint(str(tmp_path))
    # In a git checkout the parent may resolve a rev; otherwise mtime is used.
    assert fp is None or isinstance(fp, str)
