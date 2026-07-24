"""apply_bot_smart_defaults roots /undo at the workspace (bug 2 regression).

Before this fix, ``Agent.undo`` restored files relative to the gateway process
cwd, not the workspace the bot's file tools actually write to. The wrapper now
calls ``Agent.set_snapshot_root(workspace.root)`` when attaching the workspace.
"""

import os
import tempfile

from praisonaiagents import Agent
from praisonaiagents.bots import BotConfig
from praisonai_bot.bots._defaults import apply_bot_smart_defaults


def test_smart_defaults_roots_snapshot_at_workspace():
    with tempfile.TemporaryDirectory() as ws:
        config = BotConfig(workspace_dir=ws)
        agent = Agent(name="t", instructions="test")

        apply_bot_smart_defaults(agent, config, session_key="chatA")

        workspace = getattr(agent, "_workspace", None)
        assert workspace is not None
        snapshot = getattr(agent, "_file_snapshot", None)
        # Git may be unavailable; only assert rooting when a snapshot exists.
        if snapshot is not None:
            assert snapshot.project_path == os.path.abspath(str(workspace.root))
