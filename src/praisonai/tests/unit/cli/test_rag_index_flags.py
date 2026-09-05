"""`praisonai rag index` must honour --chunking and --chunk-size.

Both were declared as typer options and shown in the command's own docstring
example:

    praisonai rag index ./data --chunking semantic --chunk-size 256

and then never read. `knowledge_config` was built with a `vector_store` key
only, so Knowledge fell back to its defaults (recursive / 512) whatever the
user asked for. The one place in the codebase that documents the flags is the
help text of the command that ignores them.

The second half is the reporting: the loop counted chunks, printed a green
tick regardless, and ended with "Indexing complete!" unconditionally — so a
run in which every source indexed nothing still finished green and exited 0.
"""
import os
import tempfile

import pytest
from typer.testing import CliRunner

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import praisonaiagents.knowledge as knowledge_module
import praisonai.cli.commands.rag as rag


@pytest.fixture
def src_dir():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "x.md"), "w", encoding="utf-8") as fh:
            fh.write("Authentication uses bcrypt.\n")
        yield d


@pytest.fixture
def fake_knowledge(monkeypatch):
    """Replace Knowledge, and record the config it was handed."""
    seen = {}

    def make(results):
        class _K:
            def __init__(self, config=None, verbose=False):
                seen["config"] = config

            def add(self, source):
                return {"results": list(results)}
        return _K

    def install(results):
        monkeypatch.setattr(knowledge_module, "Knowledge", make(results))
        return seen

    return install


class TestChunkingFlagsReachKnowledge:

    def test_chunking_strategy_is_passed_through(self, src_dir, fake_knowledge):
        seen = fake_knowledge(["a"])
        CliRunner().invoke(rag.app, ["index", src_dir, "--chunking", "semantic"])
        assert seen["config"].get("chunker", {}).get("type") == "semantic"

    def test_chunk_size_is_passed_through(self, src_dir, fake_knowledge):
        seen = fake_knowledge(["a"])
        CliRunner().invoke(rag.app, ["index", src_dir, "--chunk-size", "256"])
        assert seen["config"].get("chunker", {}).get("chunk_size") == 256

    def test_the_documented_example_works(self, src_dir, fake_knowledge):
        """The exact line from the command's own docstring."""
        seen = fake_knowledge(["a"])
        CliRunner().invoke(rag.app, [
            "index", src_dir, "--chunking", "semantic", "--chunk-size", "256"])
        assert seen["config"]["chunker"] == {"type": "semantic", "chunk_size": 256}

    def test_defaults_are_still_sent(self, src_dir, fake_knowledge):
        seen = fake_knowledge(["a"])
        CliRunner().invoke(rag.app, ["index", src_dir])
        assert seen["config"]["chunker"]["type"] == "recursive"
        assert seen["config"]["chunker"]["chunk_size"] == 512

    def test_the_vector_store_config_is_untouched(self, src_dir, fake_knowledge):
        seen = fake_knowledge(["a"])
        CliRunner().invoke(rag.app, ["index", src_dir, "--collection", "research"])
        vs = seen["config"]["vector_store"]["config"]
        assert vs["collection_name"] == "research"


class TestConfigFileDoesNotSilentlyDropCliChunker:
    """A --config file that sets its own chunker must not wipe the explicit
    --chunking / --chunk-size the user typed on the same command line."""

    def _write_config(self, d, body):
        path = os.path.join(d, "cfg.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def test_explicit_flags_survive_a_config_without_a_chunker(self, src_dir, fake_knowledge):
        seen = fake_knowledge(["a"])
        cfg = self._write_config(src_dir, "knowledge:\n  vector_store:\n    provider: chroma\n")
        CliRunner().invoke(rag.app, [
            "index", src_dir, "--chunking", "semantic", "--chunk-size", "256",
            "--config", cfg])
        assert seen["config"]["chunker"] == {"type": "semantic", "chunk_size": 256}

    def test_config_chunker_field_overrides_only_that_field(self, src_dir, fake_knowledge):
        seen = fake_knowledge(["a"])
        cfg = self._write_config(src_dir, "knowledge:\n  chunker:\n    type: token\n")
        CliRunner().invoke(rag.app, [
            "index", src_dir, "--chunking", "semantic", "--chunk-size", "256",
            "--config", cfg])
        assert seen["config"]["chunker"]["type"] == "token"
        assert seen["config"]["chunker"]["chunk_size"] == 256


class TestIndexingNothingIsNotSuccess:

    def test_exit_code_is_nonzero_when_nothing_was_indexed(self, src_dir, fake_knowledge):
        fake_knowledge([])
        result = CliRunner().invoke(rag.app, ["index", src_dir])
        assert result.exit_code != 0, (
            "a run that stored nothing still reported success"
        )

    def test_it_does_not_claim_completion(self, src_dir, fake_knowledge):
        fake_knowledge([])
        result = CliRunner().invoke(rag.app, ["index", src_dir])
        assert "Indexing complete" not in result.output

    def test_intentional_exit_does_not_print_a_redundant_error(self, src_dir, fake_knowledge):
        fake_knowledge([])
        result = CliRunner().invoke(rag.app, ["index", src_dir])
        assert "Error:" not in result.output

    def test_a_real_success_still_exits_zero(self, src_dir, fake_knowledge):
        fake_knowledge(["a", "b"])
        result = CliRunner().invoke(rag.app, ["index", src_dir])
        assert result.exit_code == 0
        assert "Indexing complete" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
