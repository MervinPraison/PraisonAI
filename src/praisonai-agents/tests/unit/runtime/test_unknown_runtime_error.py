"""A typo'd runtime id must name the valid ones, not raise ImportError.

``RuntimeResolver.resolve_runtime_instance`` catches the registry's ValueError
and re-raises it with the list of available runtimes appended. To build that
list it imported ``list_available_runtimes`` -- a name the registry does not
define; it exports ``list_runtimes()``, returning ids. So the branch raised

    ImportError: cannot import name 'list_available_runtimes' from
    'praisonaiagents.runtime.registry'

at the one moment its message is worth having: the user has just mistyped a
runtime id.

Nothing caught this. The existing tests patch both ``resolve_runtime`` and the
listing function, so the real import never runs. These drive the unmocked path.
"""

import pytest

from praisonaiagents.runtime.config import AgentRuntimeConfig
from praisonaiagents.runtime.resolver import (
    RuntimeResolutionContext,
    RuntimeResolver,
)


def _resolve_unknown():
    return RuntimeResolver().resolve_runtime_instance(
        context=RuntimeResolutionContext(model_name="m"),
        model_runtime_configs={
            "m": AgentRuntimeConfig.from_runtime_id("no-such-runtime")
        },
    )


def test_an_unknown_runtime_raises_valueerror_not_importerror():
    with pytest.raises(ValueError) as excinfo:
        _resolve_unknown()
    assert not isinstance(excinfo.value, ImportError)


def test_the_error_names_the_bad_id_and_the_available_ones():
    from praisonaiagents.runtime.registry import list_runtimes

    with pytest.raises(ValueError) as excinfo:
        _resolve_unknown()

    message = str(excinfo.value)
    assert "no-such-runtime" in message

    # Assert the *enhanced* wording specifically. The resolver falls back to a
    # plain ValueError if the listing itself fails, and the registry's own error
    # happens to mention the runtimes too -- so checking only for an id here
    # would pass even with the listing broken, which is exactly the bug.
    assert "Available runtimes:" in message, message

    available = list_runtimes()
    assert available, "the registry reported no runtimes at all"
    enhanced = message.split("Available runtimes:", 1)[1]
    assert any(runtime_id in enhanced for runtime_id in available), message
