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


class _SetsMessage(RuntimeError, PraisonAIError):
    # Like LLMResponseError / RecipeError: own __init__ that sets self.message.
    def __init__(self, message):
        self.message = message
        super().__init__(message)


@pytest.mark.parametrize("exc, text", [
    (_ValueStyle("bad value"), "bad value"),
    (_OwnInit("/x"), "not found: /x"),
    (_SetsMessage("loop failed"), "loop failed"),
])
def test_mixin_keeps_the_plain_message(exc, text):
    assert str(exc) == text
    assert (exc.agent_id, exc.error_category, exc.is_retryable) == ("unknown", "unknown", False)
    # None, or a generated id where the MRO reaches PraisonAIError.__init__ (3.14+).
    assert exc.run_id is None or isinstance(exc.run_id, str)
    assert exc.context == {}
    with pytest.raises(ValueError if isinstance(exc, ValueError) else PraisonAIError):
        raise exc


class _PlainValue(ValueError):
    pass


@pytest.mark.parametrize("args", [(), ("m",), ("m", "x")])
def test_mixin_constructs_like_the_builtin(args):
    # On 3.14 ValueError has no own __init__, so PraisonAIError.__init__ used to
    # run: X() raised TypeError and X("m", "x") took "x" as agent_id.
    import pickle
    plain, mixed = _PlainValue(*args), _ValueStyle(*args)
    assert (mixed.args, str(mixed)) == (plain.args, str(plain))
    assert mixed.agent_id == "unknown"
    assert pickle.loads(pickle.dumps(mixed)).args == plain.args


def test_subclass_of_a_structured_error_stays_structured():
    from praisonaiagents.errors import ToolExecutionError

    class _Mine(ToolExecutionError):
        pass

    e = _Mine("boom", tool_name="t", agent_id="a1", run_id="r1")
    assert str(e) == str(ToolExecutionError("boom", tool_name="t", agent_id="a1", run_id="r1"))


def test_normal_message_unchanged():
    e = PraisonAIError("boom", agent_id="a1", run_id="r1", error_category="rate_limit")
    assert str(e) == "[rate_limit] boom (agent: a1, run: r1)"
    assert e.context == {}
    e.context["k"] = 1
    assert PraisonAIError("x").context == {}, "context is per instance"


def test_pickle_and_copy_keep_format():
    import copy, pickle
    e = PraisonAIError("boom", agent_id="a1", run_id="r1")
    for clone in (pickle.loads(pickle.dumps(e)), copy.deepcopy(e)):
        assert str(clone) == str(e)
    m = _ValueStyle("bad")
    assert str(pickle.loads(pickle.dumps(m))) == "bad"
