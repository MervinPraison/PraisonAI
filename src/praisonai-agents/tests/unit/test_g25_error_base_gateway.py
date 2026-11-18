"""G-25 step 2 (gateway): these errors also subclass PraisonAIError.

Each keeps its built-in base first, so existing ``except ValueError`` (etc.)
still catches it, and str()/args are unchanged. Expected values were recorded
before the change, on 3.12 and 3.14.
"""
import importlib
import pickle

import pytest

from praisonaiagents.errors import PraisonAIError

CASES = [
    ('gateway.config', 'ConfigValidationError', ('cfg.yaml', ['bad_key'], 'good_key'), "cfg.yaml: unknown key(s): bad_key (did you mean 'good_key'?)", ("cfg.yaml: unknown key(s): bad_key (did you mean 'good_key'?)",)),
    ('gateway.config', 'ConfigVersionError', ('boom',), 'boom', ('boom',)),
    ('gateway.protocols', 'InsecureGatewayTransportError', ('boom',), 'boom', ('boom',)),
    ('gateway.protocols', 'ScheduleTargetError', ('no target', 'use x'), 'no target use x', ('no target use x',)),
    ('bots.base', 'CapabilityContractError', ('boom',), 'boom', ('boom',)),
    ('bots.protocols', 'GatewayAdapterContractError', ('boom',), 'boom', ('boom',)),
    ('auth.subscription.protocols', 'AuthError', ('boom',), 'boom', ('boom',)),
]


@pytest.mark.parametrize("module,name,args,text,exc_args", CASES, ids=[c[1] for c in CASES])
def test_error_has_the_common_base_and_keeps_its_behaviour(module, name, args, text, exc_args):
    cls = getattr(importlib.import_module("praisonaiagents." + module), name)
    builtin = cls.__mro__[1]
    assert builtin in (ValueError, RuntimeError, TypeError)
    e = cls(*args)
    assert isinstance(e, PraisonAIError)
    assert (str(e), e.args) == (text, exc_args)
    assert e.agent_id == "unknown"
    with pytest.raises(builtin):
        raise e
    if len(args) == 1:
        assert str(pickle.loads(pickle.dumps(e))) == text
