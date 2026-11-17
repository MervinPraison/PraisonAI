"""G-25 step 1: PraisonAIError works as an extra base class.

The scattered *Error classes keep their own __init__ and built-in base. With
PraisonAIError added as a second base, str(e) used to raise AttributeError
(its __str__ read attributes only its own __init__ sets). It must fall back
to the plain message, and the structured fields must read as defaults.
"""
import pytest

from praisonaiagents.errors import PraisonAIError


class _ValueStyle(ValueError, PraisonAIError):
    pass


class _OwnInit(PraisonAIError):
    def __init__(self, path):
        Exception.__init__(self, f"not found: {path}")
        self.path = path


@pytest.mark.parametrize("exc, text", [
    (_ValueStyle("bad value"), "bad value"),
    (_OwnInit("/x"), "not found: /x"),
])
def test_mixin_keeps_the_plain_message(exc, text):
    assert str(exc) == text
    assert (exc.agent_id, exc.run_id, exc.error_category, exc.is_retryable) == ("unknown", None, "unknown", False)
    assert exc.context == {}
    with pytest.raises(ValueError if isinstance(exc, ValueError) else PraisonAIError):
        raise exc


def test_normal_message_unchanged():
    e = PraisonAIError("boom", agent_id="a1", run_id="r1", error_category="rate_limit")
    assert str(e) == "[rate_limit] boom (agent: a1, run: r1)"
    assert e.context == {}
    e.context["k"] = 1
    assert PraisonAIError("x").context == {}, "context is per instance"
