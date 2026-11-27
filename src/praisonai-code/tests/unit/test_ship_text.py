"""Shared untrusted-text fencing and noisy-diff stripping for ``praisonai ship``."""

from praisonai_code.ship._text import MAX_UNTRUSTED, fence_untrusted, strip_noisy_diff


def _hunk(path: str, body: str = "+x = 1\n") -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n{body}"


def test_strip_noisy_diff_drops_lockfiles_and_minified_bundles():
    diff = (
        _hunk("uv.lock", "+" + ("lock\n" * 6_000))
        + _hunk("web/package-lock.json", '+{"a": 1}\n')
        + _hunk("web/pnpm-lock.yaml", "+lockfileVersion: 9\n")
        + _hunk("web/yarn.lock", "+pkg:\n")
        + _hunk("static/bundle.min.js", "+var a=1;\n")
        + _hunk("static/app.min.css", "+body{}\n")
        + _hunk("src/app.py", "+def real_fix():\n+    return 42\n")
    )
    cleaned = strip_noisy_diff(diff)
    assert "src/app.py" in cleaned and "def real_fix" in cleaned
    for noisy in ("uv.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bundle.min.js", "app.min.css"):
        assert noisy not in cleaned


def test_strip_noisy_diff_returns_note_when_only_noisy_files():
    diff = _hunk("uv.lock", "+pkg\n") + _hunk("dist/app.min.js", "+x\n")
    assert strip_noisy_diff(diff) == "(only lockfile/minified changes)"


def test_strip_noisy_diff_preserves_plain_non_git_text():
    plain = "+def f():\n+    return 1\n"
    assert strip_noisy_diff(plain) == plain


def test_fence_untrusted_caps_strips_and_uses_longer_backtick_fence():
    huge_lock = _hunk("uv.lock", "+" + ("L" * (MAX_UNTRUSTED + 5_000)) + "\n")
    real = _hunk("src/real.py", "+```ignore```\n+return 1\n")
    fenced = fence_untrusted(huge_lock + real, lang="diff", strip_noise=True)
    assert fenced.startswith("````diff\n") and fenced.endswith("\n````")
    assert "src/real.py" in fenced and "uv.lock" not in fenced
    assert "(diff truncated)" not in fenced


def test_fence_untrusted_truncates_text_and_diff_with_expected_suffix():
    big = "A" * (MAX_UNTRUSTED + 500)
    assert "(diff truncated)" in fence_untrusted(big, lang="diff")
    assert "(truncated)" in fence_untrusted(big, lang="text")
    assert "(diff truncated)" not in fence_untrusted(big, lang="text")
