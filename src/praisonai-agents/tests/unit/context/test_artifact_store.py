"""Tests for artifact storage functionality."""

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ToolConfig
from praisonaiagents.context import ArtifactMetadata, FileSystemArtifactStore
from praisonaiagents.tools import tool


@tool
def generate_large_output(size: int = 20000) -> str:
    """Generate a large string for testing artifact storage."""
    return "X" * size


def test_artifact_storage():
    """Test that large tool outputs are stored as artifacts."""
    agent = Agent(
        name="TestAgent",
        instructions="You are a test agent",
        tools=[generate_large_output],
        tool_config=ToolConfig(
            output_limit=1000,
            enable_artifacts=True,
            artifact_retention_days=1,
        ),
    )

    assert agent._artifact_store is not None

    store = FileSystemArtifactStore()
    metadata = ArtifactMetadata(
        agent_id="test_agent",
        run_id="test_run",
        tool_name="test_tool",
        turn_id=1,
    )

    large_content = "TEST" * 5000
    ref = store.store(large_content, metadata)

    assert ref is not None
    assert ref.size_bytes == len(large_content)

    head = store.head(ref, lines=2)
    assert "TEST" in head

    tail = store.tail(ref, lines=2)
    assert "TEST" in tail

    matches = store.grep(ref, "TEST", context_lines=1, max_matches=5)
    assert len(matches) > 0

    chunk = store.chunk(ref, start_line=1, end_line=3)
    assert "TEST" in chunk

    loaded = store.load(ref)
    assert loaded == large_content

    deleted = store.delete(ref)
    assert deleted
