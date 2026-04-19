"""Tests for skill inline shell substitution."""

from praisonaiagents.skills.shell_render import render_shell_blocks


class TestDisabledByDefault:
    def test_inline_not_expanded_when_disabled(self):
        body = "Version: !`echo hi`"
        out = render_shell_blocks(body, enabled=False)
        assert "[shell execution disabled]" in out
        assert "echo hi" not in out or out.count("hi") == 0

    def test_fenced_block_disabled(self):
        body = "```!\necho hello\n```"
        out = render_shell_blocks(body, enabled=False)
        assert "[shell execution disabled]" in out


class TestEnabledExecution:
    def test_inline_backtick_is_executed(self):
        body = "Answer: !`echo 42`"
        out = render_shell_blocks(body, enabled=True, timeout=5)
        assert "Answer: 42" in out

    def test_fenced_block_executed(self):
        body = "```!\necho start\necho end\n```"
        out = render_shell_blocks(body, enabled=True, timeout=5)
        assert "start" in out and "end" in out
        assert "```!" not in out

    def test_timeout_produces_marker(self):
        body = "Slow: !`sleep 5`"
        out = render_shell_blocks(body, enabled=True, timeout=1)
        assert "[shell timeout" in out.lower() or "error" in out.lower()

    def test_no_shell_blocks_leaves_body_intact(self):
        body = "No shell here."
        out = render_shell_blocks(body, enabled=True)
        assert out == body
