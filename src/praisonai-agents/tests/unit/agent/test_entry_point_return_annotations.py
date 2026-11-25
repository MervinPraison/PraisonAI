"""D-08: Agent entry points declare what they return.

chat()/achat()/run()/arun()/execute()/aexecute() return the parsed model
instance when output_pydantic is given, but were annotated Optional[str] (or
not at all). The annotations only document; behaviour is unchanged.
"""

import inspect

from praisonaiagents import Agent

CHAT_FAMILY = ["chat", "achat", "run", "arun", "execute", "aexecute"]


def _ret(name):
    return str(inspect.signature(getattr(Agent, name)).return_annotation)


def test_every_entry_point_has_a_return_annotation():
    for name in CHAT_FAMILY + ["start", "astart"]:
        assert _ret(name) != str(inspect.Signature.empty), name


def test_chat_family_includes_the_output_pydantic_model():
    for name in CHAT_FAMILY:
        assert "BaseModel" in _ret(name), (name, _ret(name))


def test_start_includes_the_model_and_the_stream():
    for name in ("start", "astart"):
        ret = _ret(name)
        assert "BaseModel" in ret and "str" in ret, (name, ret)
    assert "Generator" in _ret("start")
