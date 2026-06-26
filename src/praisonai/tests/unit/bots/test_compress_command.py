"""Regression tests for /compress bot command handler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from praisonai.bots._commands import handle_compress_command


def test_compress_error_path_does_not_crash_on_optimizer_failure():
    """Error handling must not raise NameError when logging failures."""
    session = MagicMock()
    session._histories = {"user-1": [{"role": "user", "content": f"m{i}"} for i in range(12)]}
    session._storage_key = lambda user_id: user_id

    with patch(
        "praisonaiagents.context.optimizer.SummarizeOptimizer",
        side_effect=RuntimeError("optimizer blew up"),
    ):
        response = handle_compress_command(session, "user-1", agent=None)

    assert response.startswith("❌ Compression failed:")
    assert "optimizer blew up" in response
