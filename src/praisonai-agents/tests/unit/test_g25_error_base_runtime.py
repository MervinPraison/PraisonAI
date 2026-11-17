"""G-25 step 2 (runtime): these errors also subclass PraisonAIError.

Each keeps its built-in base first, so existing ``except ValueError`` (etc.)
still catches it, and str()/args are unchanged. Expected values were recorded
before the change, on 3.12 and 3.14.
"""
import importlib
import pickle

import pytest

from praisonaiagents.errors import PraisonAIError

CASES = [
    ('knowledge.cloud', 'CloudSourceError', ('boom',), 'boom', ('boom',)),
    ('runtime.portable', 'PortableRunError', ('boom',), 'boom', ('boom',)),
    ('session.encrypted_store', 'SessionEncryptionError', ('boom',), 'boom', ('boom',)),
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
