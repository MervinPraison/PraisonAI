"""
Unit tests for the wrapper-resident knowledge command
(`praisonai.cli.commands.knowledge`).

Regression coverage for #2809: `praisonai knowledge search` crashed with
"'SearchResult' object is not subscriptable" because the wrapper handler
treated Knowledge.search() output as a dict/sliceable sequence. PR #2779
only fixed the parallel feature module, not this shipped command path.
"""
import pytest


@pytest.fixture
def cli_runner():
    try:
        from typer.testing import CliRunner
    except ImportError:
        pytest.skip("typer not installed")
    return CliRunner()


@pytest.fixture
def knowledge_wrapper_app():
    try:
        from praisonai.cli.commands.knowledge import app
    except ImportError:
        pytest.skip("knowledge wrapper CLI not installed")
    return app


def test_wrapper_search_handles_search_result_dataclass(
    cli_runner, knowledge_wrapper_app, monkeypatch
):
    """`praisonai knowledge search` must not crash on a SearchResult dataclass."""
    try:
        from praisonaiagents.knowledge.models import (
            SearchResult, SearchResultItem,
        )
        import praisonaiagents.knowledge as knowledge_mod
    except ImportError:
        pytest.skip("praisonaiagents.knowledge not installed")

    search_result = SearchResult(
        results=[
            SearchResultItem(
                id="1",
                text="Paris is the capital of France.",
                score=0.9,
                metadata={"filename": "kb-retest.txt"},
            )
        ]
    )

    class _FakeKnowledge:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return search_result

    monkeypatch.setattr(knowledge_mod, "Knowledge", _FakeKnowledge)

    result = cli_runner.invoke(
        knowledge_wrapper_app, ["search", "Paris", "--user-id", "u"]
    )
    assert result.exit_code == 0
    output = result.output
    assert "not subscriptable" not in output
    assert "Paris is the capital of France." in output


def test_wrapper_search_handles_empty_search_result(
    cli_runner, knowledge_wrapper_app, monkeypatch
):
    """Empty SearchResult must yield a graceful 'No results found.' message.

    An empty SearchResult(results=[]) is truthy, so the old `if not results`
    guard failed and execution fell through to the slice crash.
    """
    try:
        from praisonaiagents.knowledge.models import SearchResult
        import praisonaiagents.knowledge as knowledge_mod
    except ImportError:
        pytest.skip("praisonaiagents.knowledge not installed")

    class _FakeKnowledge:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return SearchResult(results=[])

    monkeypatch.setattr(knowledge_mod, "Knowledge", _FakeKnowledge)

    result = cli_runner.invoke(
        knowledge_wrapper_app, ["search", "anything", "--user-id", "u"]
    )
    assert result.exit_code == 0
    output = result.output
    assert "not subscriptable" not in output
    assert "No results found" in output


def test_wrapper_search_handles_legacy_dict(
    cli_runner, knowledge_wrapper_app, monkeypatch
):
    """Legacy dict output from Knowledge.search() must still work."""
    try:
        import praisonaiagents.knowledge as knowledge_mod
    except ImportError:
        pytest.skip("praisonaiagents.knowledge not installed")

    class _FakeKnowledge:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return {
                "results": [
                    {
                        "memory": "Paris is the capital of France.",
                        "score": 0.9,
                        "metadata": {"filename": "kb-retest.txt"},
                    }
                ]
            }

    monkeypatch.setattr(knowledge_mod, "Knowledge", _FakeKnowledge)

    result = cli_runner.invoke(
        knowledge_wrapper_app, ["search", "Paris", "--user-id", "u"]
    )
    assert result.exit_code == 0
    output = result.output
    assert "not subscriptable" not in output
    assert "Paris is the capital of France." in output
