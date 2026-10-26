from praisonaiagents.agent.context_agent import ContextAgent

NON_ASCII = "日本語 café ☕"


def test_context_engineering_results_written_as_readable_utf8(tmp_path, monkeypatch):
    """Saved Context Engineering results keep non-ASCII content as readable UTF-8."""
    # ContextAgent defaults output to .praisonai/prp under the cwd, so run inside tmp.
    monkeypatch.chdir(tmp_path)
    agent = ContextAgent(llm="gpt-4o-mini", auto_analyze=False)
    agent.output_dir = str(tmp_path)
    agent.codebase_analysis = {"summary": NON_ASCII}
    agent.pattern_library = {}
    agent.validation_framework = {}
    agent.agent_interactions = []

    agent._save_context_engineering_results()

    saved = (tmp_path / "comprehensive_analysis.json").read_text(encoding="utf-8")
    assert NON_ASCII in saved
    assert "\\u" not in saved
