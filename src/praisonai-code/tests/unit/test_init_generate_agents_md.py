"""Tests for `praisonai init --generate` repository-tailored AGENTS.md.

Covers the agent-driven onboarding path added on top of the static scaffold:

- With a provider credential, generation writes an AGENTS.md at the repo root
  containing the agent's analysis (mentioning detected build/test context).
- With no credential, `--generate` degrades to today's static scaffold and
  writes no AGENTS.md.
- An existing AGENTS.md is never overwritten without `--force`.
- Generation failures never break init (static scaffold remains).
"""

from pathlib import Path
from unittest.mock import patch

from praisonai_code.cli.commands import init as init_mod


def _run_init(tmp_path: Path, **kwargs) -> None:
    """Invoke the init callback with a stub context, scoped to tmp_path."""

    class _Ctx:
        invoked_subcommand = None

    with patch.object(init_mod, "get_git_root", return_value=tmp_path):
        init_mod.init(_Ctx(), global_=kwargs.get("global_", False),
                      force=kwargs.get("force", False),
                      generate=kwargs.get("generate", False))


class TestPrescan:
    def test_captures_manifests_and_readme(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "README.md").write_text("# MyProj\nRun tests with pytest.")
        (tmp_path / "src").mkdir()

        snapshot = init_mod._prescan_repo(tmp_path)

        assert "pyproject.toml" in snapshot
        assert "src/" in snapshot
        assert "Run tests with pytest." in snapshot


class TestGenerateWiring:
    def test_generates_agents_md_with_credential(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        generated = "# Agents\nBuild: pip install -e .\nTest: pytest\n"

        with patch.object(init_mod, "_any_provider_credential", return_value=True), \
             patch.object(init_mod, "_generate_agents_md", return_value=generated) as gen:
            _run_init(tmp_path, generate=True)

        agents = tmp_path / "AGENTS.md"
        assert agents.exists()
        assert "pytest" in agents.read_text()
        gen.assert_called_once()

    def test_no_credential_falls_back_to_static_scaffold(self, tmp_path):
        with patch.object(init_mod, "_any_provider_credential", return_value=False), \
             patch.object(init_mod, "_generate_agents_md") as gen:
            _run_init(tmp_path, generate=True)

        # Static scaffold still produced, but no AGENTS.md and no agent call.
        assert (tmp_path / ".praisonai" / "config.yaml").exists()
        assert not (tmp_path / "AGENTS.md").exists()
        gen.assert_not_called()

    def test_existing_agents_md_not_overwritten_without_force(self, tmp_path):
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Existing rules\n")

        with patch.object(init_mod, "_any_provider_credential", return_value=True), \
             patch.object(init_mod, "_generate_agents_md") as gen:
            _run_init(tmp_path, generate=True)

        assert agents.read_text() == "# Existing rules\n"
        gen.assert_not_called()

    def test_existing_agents_md_overwritten_with_force(self, tmp_path):
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Existing rules\n")

        with patch.object(init_mod, "_any_provider_credential", return_value=True), \
             patch.object(init_mod, "_generate_agents_md", return_value="# New\n"):
            _run_init(tmp_path, generate=True, force=True)

        assert agents.read_text() == "# New\n"

    def test_generation_failure_does_not_break_init(self, tmp_path):
        with patch.object(init_mod, "_any_provider_credential", return_value=True), \
             patch.object(init_mod, "_generate_agents_md", side_effect=RuntimeError("boom")):
            _run_init(tmp_path, generate=True)

        # Init still succeeds with the static scaffold; no AGENTS.md written.
        assert (tmp_path / ".praisonai" / "config.yaml").exists()
        assert not (tmp_path / "AGENTS.md").exists()

    def test_no_generate_flag_never_writes_agents_md(self, tmp_path):
        with patch.object(init_mod, "_any_provider_credential", return_value=True), \
             patch.object(init_mod, "_generate_agents_md") as gen:
            _run_init(tmp_path, generate=False)

        assert not (tmp_path / "AGENTS.md").exists()
        gen.assert_not_called()

    def test_global_writes_agents_md_to_repo_root_not_home(self, tmp_path, monkeypatch):
        # --global changes only the static scaffold location; the generated
        # AGENTS.md must still land at the repo root, never ~/AGENTS.md.
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))

        captured = {}

        def _fake_generate(root, model):
            captured["root"] = root
            return "# Repo agents\n"

        with patch.object(init_mod, "_any_provider_credential", return_value=True), \
             patch.object(init_mod, "_generate_agents_md", side_effect=_fake_generate):
            _run_init(tmp_path, generate=True, global_=True)

        assert (tmp_path / "AGENTS.md").exists()
        assert not (home / "AGENTS.md").exists()
        assert captured["root"] == tmp_path


class TestGenerateHelper:
    def test_uses_run_and_returns_string_not_generator(self, tmp_path):
        # _generate_agents_md must call agent.run() (silent, returns str), not
        # start() which can return a streaming generator whose repr would be
        # written to AGENTS.md.
        class _FakeAgent:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, prompt):
                return "# Generated\nBuild: make\n"

            def start(self, prompt):  # pragma: no cover - must not be used
                raise AssertionError("start() must not be used")

        with patch("praisonaiagents.Agent", _FakeAgent):
            out = init_mod._generate_agents_md(tmp_path, "gpt-4o-mini")

        assert out == "# Generated\nBuild: make\n"
