"""T-08: a litellm capability lookup that raises is logged at debug, not
swallowed, and the answer is unchanged.

When litellm raises, these checks fall back (for example gpt-4o then reports
no function calling); before, nothing said why.
"""
import logging

import pytest

import praisonaiagents.llm.model_capabilities as mc


class _Boom:
    """Every attribute exists and every call raises, like a broken litellm."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Boom()

    def __call__(self, *a, **k):
        raise RuntimeError("litellm exploded")


# Recorded on main 33d767a0ce with the same raising litellm.
EXPECTED = {
    "supports_structured_outputs": False, "supports_function_calling": False,
    "supports_parallel_function_calling": False, "supports_web_search": False,
    "supports_prompt_caching": False, "supports_vision": False,
    "supports_pdf_input": False, "supports_audio_input": False,
    "is_reasoning_model": False, "max_output_tokens": None,
}
LOOKUPS = {"max_output_tokens": 2}  # get_model_info, then model_cost


@pytest.fixture
def broken_litellm(monkeypatch):
    monkeypatch.setattr(mc, "_get_litellm", lambda: _Boom())
    for name in EXPECTED:
        getattr(mc, name).cache_clear()
    yield
    for name in EXPECTED:
        getattr(mc, name).cache_clear()


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_failure_is_logged_and_answer_unchanged(name, broken_litellm, caplog):
    with caplog.at_level(logging.DEBUG, logger=mc.__name__):
        assert getattr(mc, name)("gpt-4o") == EXPECTED[name]
    records = [r for r in caplog.records if r.name == mc.__name__ and r.exc_info]
    assert len(records) == LOOKUPS.get(name, 1)
    assert all(name in r.getMessage() and "gpt-4o" in r.getMessage() for r in records)
    assert all(isinstance(r.exc_info[1], RuntimeError) for r in records)
