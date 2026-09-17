"""`praisonai context compact/export` must not report success on an empty store.

``praisonaiagents.context.get_global_store()`` is an in-memory, process-local
singleton that the agent runtime never populates, so in a fresh CLI process it
is always empty. The commands used to iterate zero agents and print
"Compaction complete." -- success reported for work that did not happen.
"""

import pytest

typer_testing = pytest.importorskip("typer.testing")
CliRunner = typer_testing.CliRunner


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _empty_store():
    store = pytest.importorskip("praisonaiagents.context")
    store.reset_global_store()
    yield
    store.reset_global_store()


def _app():
    from praisonai.cli.commands.context import app
    return app


def test_compact_does_not_claim_success_on_an_empty_store(runner):
    result = runner.invoke(_app(), ["compact"])

    assert "Compaction complete" not in result.output, result.output
    assert "process-local" in result.output, result.output
    assert result.exit_code == 1


def test_compact_dry_run_reports_the_empty_store(runner):
    result = runner.invoke(_app(), ["compact", "--dry-run"])

    assert "process-local" in result.output, result.output
    assert result.exit_code == 1


def test_export_does_not_write_a_file_for_an_empty_store(runner, tmp_path):
    target = tmp_path / "ctx.json"
    result = runner.invoke(_app(), ["export", str(target)])

    assert not target.exists(), "exported a file for a store with no content"
    assert "process-local" in result.output, result.output
    assert result.exit_code == 1


def test_compact_still_works_when_the_store_has_content(runner):
    from praisonaiagents.context import get_global_store

    mutator = get_global_store().get_mutator("agent-1")
    mutator.append({"role": "user", "content": "hi"})
    mutator.commit()

    result = runner.invoke(_app(), ["compact"])

    assert result.exit_code == 0, result.output
    assert "Compaction complete" in result.output
    assert "agent-1" in result.output


def test_export_writes_a_shared_context_only_store(runner, tmp_path):
    """A store holding only shared context is still exportable (snapshot()
    serialises shared_context), so export must not reject it as empty."""
    from praisonaiagents.context import get_global_store

    get_global_store().add_shared_context({"role": "system", "content": "shared"})

    target = tmp_path / "ctx.json"
    result = runner.invoke(_app(), ["export", str(target)])

    assert result.exit_code == 0, result.output
    assert target.exists(), "shared-context-only store was rejected as empty"


def test_compact_reports_shared_only_store_honestly(runner):
    """Compaction cleans per-agent history only; a shared-context-only store
    has nothing to compact and must say so rather than claim success."""
    from praisonaiagents.context import get_global_store

    get_global_store().add_shared_context({"role": "system", "content": "shared"})

    result = runner.invoke(_app(), ["compact"])

    assert result.exit_code == 1, result.output
    assert "Compaction complete" not in result.output
    assert "shared context" in result.output
