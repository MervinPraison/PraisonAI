"""Opt-in real Agent.start turns through a configured Responses provider."""

import os

import pytest


@pytest.mark.live
def test_agent_continues_with_server_side_conversation(monkeypatch, tmp_path):
    import litellm
    from praisonaiagents import Agent

    model = os.environ.get("PRAISONAI_TEST_RESPONSES_MODEL")
    if not model:
        pytest.skip("Set PRAISONAI_TEST_RESPONSES_MODEL to select a Responses provider")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    requests = []
    responses = litellm.responses

    def capture(**params):
        requests.append(params)
        return responses(**params)

    monkeypatch.setattr(litellm, "responses", capture)
    options = dict(
        instructions="Answer briefly and repeat project names exactly as given.",
        llm={
            "model": model,
            "server_side_conversation": True,
            "temperature": 0,
            "max_tokens": 96,
        },
        reflection=False,
        rules=False,
        output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    with Agent(**options) as agent:
        assert agent.llm_instance._supports_responses_api()
        first = agent.start("My project name is ORANGE-PANDA. Say noted.")
        print("Full first Agent.start output:", first)
        answer = agent.start("What is my project name?")
        print("Full second Agent.start output:", answer)
        assert isinstance(first, str) and first.strip()
        assert "ORANGE-PANDA" in answer
        assert requests[0]["store"] is True
        assert any(p.get("previous_response_id") for p in requests[1:])
