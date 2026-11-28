"""D-08: Agent and AgentTeam entry points declare what they return.

chat()/achat()/run()/arun()/execute()/aexecute() return the parsed model
instance when output_pydantic is given, and @overload signatures narrow
chat/achat/start for static type checkers. AgentTeam/AutoAgents entry points
declare Union[str, Dict[str, Any]]. The annotations only document; behaviour
is unchanged and importing Agent must not eagerly load pydantic.
"""

import inspect
import subprocess
import sys
import typing

import pytest

from praisonaiagents import Agent, AgentTeam, AutoAgents

CHAT_FAMILY = ["chat", "achat", "run", "arun", "execute", "aexecute"]
TEAM_ENTRY_POINTS = ["start", "astart", "run", "arun"]


def _ret(cls, name):
    return str(inspect.signature(getattr(cls, name)).return_annotation)


def test_every_entry_point_has_a_return_annotation():
    for name in CHAT_FAMILY + ["start", "astart"]:
        assert _ret(Agent, name) != str(inspect.Signature.empty), name


def test_chat_family_includes_the_output_pydantic_model():
    for name in CHAT_FAMILY:
        assert "BaseModel" in _ret(Agent, name), (name, _ret(Agent, name))


def test_start_includes_the_model_and_the_stream():
    for name in ("start", "astart"):
        ret = _ret(Agent, name)
        assert "BaseModel" in ret and "str" in ret, (name, ret)
    assert "Generator" in _ret(Agent, "start")


@pytest.mark.skipif(not hasattr(typing, "get_overloads"), reason="Python 3.11+ typing.get_overloads")
def test_chat_and_achat_overloads_distinguish_str_and_model():
    for name in ("chat", "achat"):
        overloads = typing.get_overloads(getattr(Agent, name))
        assert len(overloads) >= 2, (name, overloads)
        rets = [str(inspect.signature(fn).return_annotation) for fn in overloads]
        assert any("str" in r and "BaseModel" not in r for r in rets), (name, rets)
        # Model overload returns Optional[_OutputT] where _OutputT is bound to BaseModel
        has_model_tv = False
        for fn in overloads:
            sig = inspect.signature(fn)
            ann = sig.return_annotation
            for arg in typing.get_args(ann):
                if isinstance(arg, typing.TypeVar) and "BaseModel" in str(arg.__bound__):
                    has_model_tv = True
        assert has_model_tv, (name, rets)


@pytest.mark.skipif(not hasattr(typing, "get_overloads"), reason="Python 3.11+ typing.get_overloads")
def test_start_overloads_distinguish_stream_model_and_str():
    overloads = typing.get_overloads(Agent.start)
    assert len(overloads) >= 3, overloads
    sigs = [inspect.signature(fn) for fn in overloads]
    rets = [str(s.return_annotation) for s in sigs]
    assert any("Generator" in r for r in rets), rets
    assert any("str" in r and "Generator" not in r and "BaseModel" not in r for r in rets), rets
    has_model_tv = any(
        isinstance(arg, typing.TypeVar) and "BaseModel" in str(arg.__bound__)
        for s in sigs
        for arg in typing.get_args(s.return_annotation)
    )
    assert has_model_tv, rets


def test_agent_team_and_autoagents_entry_points_have_return_annotations():
    for name in TEAM_ENTRY_POINTS:
        ret = _ret(AgentTeam, name)
        assert ret != str(inspect.Signature.empty), name
        assert "str" in ret and "Dict" in ret, (name, ret)
    for name in ("start", "astart"):
        ret = _ret(AutoAgents, name)
        assert ret != str(inspect.Signature.empty), name
        assert "str" in ret and "Dict" in ret, (name, ret)


@pytest.mark.skipif(not hasattr(typing, "get_overloads"), reason="Python 3.11+ typing.get_overloads")
def test_agent_team_overloads_narrow_return_dict_true():
    for name in TEAM_ENTRY_POINTS:
        overloads = typing.get_overloads(getattr(AgentTeam, name))
        assert len(overloads) >= 2, (name, overloads)
        has_dict_only = False
        for fn in overloads:
            sig = inspect.signature(fn)
            rd = str(sig.parameters["return_dict"].annotation)
            ret = str(sig.return_annotation)
            if "Literal[True]" in rd and "Dict" in ret and "str" not in ret.split("[", 1)[0]:
                # Return annotation should be Dict[str, Any], not Union[str, Dict[...]]
                if not ret.startswith("typing.Union"):
                    has_dict_only = True
        assert has_dict_only, (name, [str(inspect.signature(fn)) for fn in overloads])


def test_agent_import_and_overloads_do_not_eagerly_import_pydantic():
    code = "\n".join([
        "import inspect, sys, typing",
        "from praisonaiagents import Agent",
        "assert 'pydantic' not in sys.modules, 'pydantic eagerly imported'",
        "for n in ('chat', 'achat', 'start'):",
        "    inspect.signature(getattr(Agent, n))",
        "    if hasattr(typing, 'get_overloads'):",
        "        assert len(typing.get_overloads(getattr(Agent, n))) >= 2, n",
        "assert 'pydantic' not in sys.modules, 'pydantic imported by overload inspection'",
    ])
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr or res.stdout
