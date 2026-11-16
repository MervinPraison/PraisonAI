from praisonaiagents.agent.context_agent import ContextAgent

NON_ASCII = "日本語 café ☕"


def test_context_engineering_results_written_as_readable_utf8(tmp_path, monkeypatch):
    """Every saved Context Engineering result file keeps non-ASCII content as readable UTF-8."""
    # ContextAgent defaults output to .praisonai/prp under the cwd, so run inside tmp.
    monkeypatch.chdir(tmp_path)
    agent = ContextAgent(llm="gpt-4o-mini", auto_analyze=False)
    agent.output_dir = str(tmp_path)
    agent.codebase_analysis = {"summary": NON_ASCII}
    agent.pattern_library = {"summary": NON_ASCII}
    agent.validation_framework = {"summary": NON_ASCII}
    agent.agent_interactions = [{"response": NON_ASCII}]

    agent._save_context_engineering_results()

    for filename in (
        "comprehensive_analysis.json",
        "pattern_library.json",
        "validation_framework.json",
        "all_agent_interactions.json",
    ):
        saved = (tmp_path / filename).read_text(encoding="utf-8")
        assert NON_ASCII in saved, filename
        assert "\\u" not in saved, filename
