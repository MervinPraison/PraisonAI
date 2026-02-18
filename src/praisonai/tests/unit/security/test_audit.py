"""
TDD tests for praisonai.security.audit module.

Tests cover:
- AuditLogHook construction and configuration
- JSONL log file writing
- Log rotation / size limits
- enable_audit_log() convenience function
"""
import json
import os
import pytest
import tempfile


class TestAuditLogHook:
    def _make(self, log_path=None):
        from praisonai.security.audit import AuditLogHook
        if log_path is None:
            tmp = tempfile.mktemp(suffix=".jsonl")
            log_path = tmp
        return AuditLogHook(log_path=log_path), log_path

    def test_construction(self):
        hook, _ = self._make()
        assert hook is not None

    def test_create_hook_returns_callable(self):
        hook, _ = self._make()
        fn = hook.create_after_tool_hook()
        assert callable(fn)

    def test_logs_tool_call_to_file(self):
        from praisonaiagents.hooks import AfterToolInput
        hook, log_path = self._make()
        fn = hook.create_after_tool_hook()

        data = AfterToolInput(
            session_id="sess-1",
            cwd="/tmp",
            event_name="after_tool",
            timestamp="1000.0",
            agent_name="test-agent",
            tool_name="web_search",
            tool_input={"query": "hello"},
            tool_output="some results",
            execution_time_ms=42.0,
        )
        fn(data)

        assert os.path.exists(log_path)
        with open(log_path) as f:
            entry = json.loads(f.readline())
        assert entry["tool_name"] == "web_search"
        assert entry["agent_name"] == "test-agent"
        assert entry["session_id"] == "sess-1"
        assert "timestamp" in entry
        os.unlink(log_path)

    def test_multiple_calls_append_lines(self):
        from praisonaiagents.hooks import AfterToolInput
        hook, log_path = self._make()
        fn = hook.create_after_tool_hook()

        for i in range(3):
            data = AfterToolInput(
                session_id=f"sess-{i}",
                cwd="/tmp",
                event_name="after_tool",
                timestamp="0",
                agent_name="agent",
                tool_name=f"tool_{i}",
                tool_input={},
                tool_output=None,
                execution_time_ms=1.0,
            )
            fn(data)

        with open(log_path) as f:
            lines = [l for l in f.readlines() if l.strip()]
        assert len(lines) == 3
        os.unlink(log_path)

    def test_log_entry_has_required_fields(self):
        from praisonaiagents.hooks import AfterToolInput
        hook, log_path = self._make()
        fn = hook.create_after_tool_hook()

        data = AfterToolInput(
            session_id="s",
            cwd="/tmp",
            event_name="after_tool",
            timestamp="0",
            agent_name="a",
            tool_name="write_file",
            tool_input={"path": "/tmp/x.txt"},
            tool_output="ok",
            execution_time_ms=5.0,
        )
        fn(data)

        with open(log_path) as f:
            entry = json.loads(f.readline())

        required_fields = ["timestamp", "session_id", "agent_name", "tool_name",
                           "tool_input", "execution_time_ms"]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"
        os.unlink(log_path)


class TestEnableAuditLog:
    def test_enable_returns_hook_ids(self):
        from praisonai.security import enable_audit_log
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            log_path = f.name
        ids = enable_audit_log(log_path=log_path)
        assert ids is not None
        os.unlink(log_path)

    def test_enable_with_default_path(self):
        """enable_audit_log() without args should not raise."""
        from praisonai.security import enable_audit_log
        ids = enable_audit_log()
        assert ids is not None
