"""Top-level YAML ``llm`` is the crew default model (issue #6200)."""

from praisonai.agents_generator import AgentsGenerator
from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter


def _gen(config_list, cli_config=None):
    gen = AgentsGenerator.__new__(AgentsGenerator)
    gen.config_list = config_list
    gen.cli_config = cli_config or {}
    return gen


CATALOGUE = [{"model": "gpt-5.5", "base_url": "https://x", "api_key": "k"}]


def test_yaml_llm_overrides_catalogue_model():
    gen = _gen(CATALOGUE)
    result = gen._run_config_list({"llm": "gpt-4o-mini"})
    assert result[0]["model"] == "gpt-4o-mini"
    assert result[0]["base_url"] == "https://x"
    # caller-owned config_list is not mutated
    assert CATALOGUE[0]["model"] == "gpt-5.5"


def test_yaml_llm_dict_form():
    gen = _gen(CATALOGUE)
    assert gen._run_config_list({"llm": {"model": "gpt-4o"}})[0]["model"] == "gpt-4o"


def test_yaml_llm_with_empty_config_list():
    assert _gen([])._run_config_list({"llm": "gpt-4o-mini"}) == [{"model": "gpt-4o-mini"}]


def test_cli_model_overrides_yaml_llm():
    gen = _gen([{"model": "gpt-4o"}], cli_config={"model": "gpt-4o"})
    assert gen._run_config_list({"llm": "gpt-4o-mini"})[0]["model"] == "gpt-4o"


def test_no_yaml_llm_keeps_config_list():
    gen = _gen(CATALOGUE)
    assert gen._run_config_list({}) is CATALOGUE


def test_per_agent_llm_still_wins():
    adapter = PraisonAIAdapter()
    default = adapter._pick_model(_gen(CATALOGUE)._run_config_list({"llm": "gpt-4o-mini"}))
    assert adapter._resolve_agent_model({}, default) == "gpt-4o-mini"
    assert adapter._resolve_agent_model({"llm": "gpt-4o"}, default) == "gpt-4o"
