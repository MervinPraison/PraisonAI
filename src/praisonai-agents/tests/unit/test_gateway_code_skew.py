"""Unit tests for the gateway code-skew predicate (Issue #2460).

Covers the pure, core-side ``detect_code_skew`` predicate. The concrete
``read_code_fingerprint`` helper is wrapper-side (subprocess + filesystem walk)
and is tested under the ``praisonai`` package.
"""

from praisonaiagents.gateway import detect_code_skew


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


def test_combined_sha_mtime_fingerprint_shortens_leading_sha():
    # Dirty/source checkout fingerprints combine the rev with the newest mtime
    # as "<sha>+mtime:<ns>"; the leading SHA should still be shortened to 7.
    boot = "a" * 40 + "+mtime:100"
    disk = "a" * 40 + "+mtime:200"
    skew = detect_code_skew(boot, disk)
    assert skew == ("aaaaaaa+mtime:100", "aaaaaaa+mtime:200")
