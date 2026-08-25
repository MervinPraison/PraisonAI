"""An unknown Agent kwarg must say what to do instead, not just that it is wrong.

`Agent` deliberately rejects unknown keyword arguments rather than swallowing
them -- that part is correct and worth keeping. But several names are near
universal in this ecosystem (`verbose` is accepted by six sibling classes here,
and by crewai and langchain), so users reach for them constantly. A bare
"unexpected keyword argument" leaves them with no next step, and the answer is
not discoverable from the 41-parameter signature.
"""

import pytest

from praisonaiagents import Agent


def _err(**kwargs) -> str:
    with pytest.raises(TypeError) as exc:
        Agent(name="A", role="R", goal="G", **kwargs)
    return str(exc.value)


def test_unknown_kwargs_are_still_rejected():
    """Positive control: the fail-fast behaviour must not be softened into a warning."""
    assert "definitely_not_a_param" in _err(definitely_not_a_param=1)


def test_verbose_explains_where_verbosity_actually_lives():
    """Verbosity was consolidated into `output=`; the error must say so.

    Naming the wrong destination is worse than naming none: it sends the user
    to a setting that does not control this.
    """
    message = _err(verbose=False)
    assert "verbose" in message
    assert "output" in message.lower(), (
        "the error names the bad argument but not the supported alternative; "
        f"got: {message}"
    )


def test_stream_also_points_at_output():
    """`stream` moved the same way, and internal callers were passing both."""
    assert "output" in _err(stream=False).lower()


def test_the_guidance_names_the_offending_argument_not_a_generic_hint():
    """Guidance must be specific, or it is noise on every unrelated typo."""
    generic = _err(some_typo=1)
    assert "some_typo" in generic
    assert "output=" not in generic, (
        "an unrelated typo received the migration guidance meant for `verbose`"
    )


def test_multiple_unknown_kwargs_are_all_listed():
    message = _err(verbose=True, another_bad_one=2)
    assert "verbose" in message and "another_bad_one" in message
