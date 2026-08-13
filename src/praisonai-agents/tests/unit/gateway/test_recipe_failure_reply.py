"""Recipe gateway failures use the core failure reply contract."""

from praisonaiagents.gateway.adapters.recipe_adapter import RecipeBotAdapter


def test_recipe_adapter_does_not_return_raw_exception(monkeypatch):
    adapter = RecipeBotAdapter("demo")

    def fail():
        raise RuntimeError("private-recipe-detail")

    monkeypatch.setattr(adapter, "_get_runtime", fail)

    reply = adapter.chat("hello")

    assert reply == "I couldn't complete that due to an unexpected error. Please resend."
    assert "private-recipe-detail" not in reply
