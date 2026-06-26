"""Unit tests for per-route, trust-tiered toolset scoping (Issue #2298).

Covers the core ``ToolPolicy`` filter contract and ``RouteBinding`` declaring a
policy via ``trust`` / ``allow_tools`` / ``deny_tools`` (plus YAML ``from_dict``
parsing), in praisonaiagents.gateway.protocols.
"""

from praisonaiagents.gateway import (
    RouteBinding,
    ToolPolicy,
    UNTRUSTED_DENY_SUBSTRINGS,
    TRUST_TIERS,
)


def _named(name):
    """A simple callable tool with a resolvable name."""
    def _tool():  # pragma: no cover - never invoked
        return None
    _tool.__name__ = name
    return _tool


class TestToolPolicyFilter:
    def test_noop_policy_keeps_everything(self):
        p = ToolPolicy()
        assert p.is_noop
        tools = [_named("shell"), _named("read_file")]
        assert p.filter_tools(tools) == tools

    def test_deny_tools_exact(self):
        p = ToolPolicy(deny_tools={"shell"})
        kept = p.filter_tools([_named("shell"), _named("read_file")])
        assert [t.__name__ for t in kept] == ["read_file"]

    def test_deny_substrings_case_insensitive(self):
        p = ToolPolicy(deny_substrings=["shell"])
        kept = p.filter_tools([_named("RunShellCommand"), _named("search")])
        assert [t.__name__ for t in kept] == ["search"]

    def test_allow_tools_is_a_whitelist(self):
        p = ToolPolicy(allow_tools={"search"})
        kept = p.filter_tools(
            [_named("search"), _named("write_file"), _named("delete_file")]
        )
        assert [t.__name__ for t in kept] == ["search"]

    def test_empty_input_returns_empty(self):
        assert ToolPolicy(deny_tools={"x"}).filter_tools(None) == []
        assert ToolPolicy(deny_tools={"x"}).filter_tools([]) == []

    def test_dict_style_tool_name_resolution(self):
        p = ToolPolicy(deny_tools={"shell"})
        tool = {"type": "function", "function": {"name": "shell"}}
        keep = {"type": "function", "function": {"name": "search"}}
        kept = p.filter_tools([tool, keep])
        assert kept == [keep]


class TestRouteBindingToolPolicy:
    def test_no_constraints_returns_none(self):
        assert RouteBinding(agent="a").tool_policy() is None

    def test_trusted_tier_is_noop(self):
        assert RouteBinding(agent="a", trust="trusted").tool_policy() is None

    def test_standard_tier_is_noop(self):
        assert RouteBinding(agent="a", trust="standard").tool_policy() is None

    def test_untrusted_tier_denies_dangerous_families(self):
        pol = RouteBinding(agent="a", trust="untrusted").tool_policy()
        assert pol is not None
        kept = pol.filter_tools(
            [
                _named("run_shell"),
                _named("write_file"),
                _named("delete_file"),
                _named("delegate_task"),
                _named("schedule_cronjob"),
                _named("web_search"),
                _named("read_file"),
            ]
        )
        names = [t.__name__ for t in kept]
        assert "web_search" in names
        assert "read_file" in names
        assert "run_shell" not in names
        assert "write_file" not in names
        assert "delete_file" not in names
        assert "delegate_task" not in names
        assert "schedule_cronjob" not in names

    def test_explicit_allow_tools(self):
        pol = RouteBinding(agent="a", allow_tools=["search"]).tool_policy()
        assert pol is not None
        kept = pol.filter_tools([_named("search"), _named("shell")])
        assert [t.__name__ for t in kept] == ["search"]

    def test_explicit_deny_tools(self):
        pol = RouteBinding(agent="a", deny_tools=["shell"]).tool_policy()
        assert pol is not None
        kept = pol.filter_tools([_named("search"), _named("shell")])
        assert [t.__name__ for t in kept] == ["search"]

    def test_untrusted_plus_explicit_deny_layer(self):
        pol = RouteBinding(
            agent="a", trust="untrusted", deny_tools=["web_search"]
        ).tool_policy()
        kept = pol.filter_tools(
            [_named("web_search"), _named("run_shell"), _named("read_file")]
        )
        assert [t.__name__ for t in kept] == ["read_file"]


class TestRouteBindingFromDict:
    def test_from_dict_parses_trust_and_lists(self):
        b = RouteBinding.from_dict(
            {
                "agent": "assistant",
                "chat_type": "dm",
                "trust": "untrusted",
                "allow_tools": ["search"],
                "deny_tools": ["shell", "delete_file"],
            }
        )
        assert b.trust == "untrusted"
        assert b.allow_tools == ["search"]
        assert b.deny_tools == ["shell", "delete_file"]

    def test_from_dict_scalar_tool_is_wrapped(self):
        b = RouteBinding.from_dict({"agent": "a", "deny_tools": "shell"})
        assert b.deny_tools == ["shell"]

    def test_from_dict_absent_keys_stay_none(self):
        b = RouteBinding.from_dict({"agent": "a", "chat_type": "dm"})
        assert b.trust is None
        assert b.allow_tools is None
        assert b.deny_tools is None
        assert b.tool_policy() is None

    def test_from_dict_backward_compatible(self):
        b = RouteBinding.from_dict({"agent": "a", "peer": "123", "priority": 5})
        assert b.agent == "a"
        assert b.peer == "123"
        assert b.priority == 5


class TestModuleConstants:
    def test_trust_tiers_order(self):
        assert TRUST_TIERS == ["untrusted", "standard", "trusted"]

    def test_untrusted_deny_substrings_nonempty(self):
        assert "shell" in UNTRUSTED_DENY_SUBSTRINGS
        assert len(UNTRUSTED_DENY_SUBSTRINGS) > 0
