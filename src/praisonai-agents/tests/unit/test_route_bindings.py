"""Unit tests for the core route-binding resolver (Issue #2225).

Covers RouteBinding matching/specificity and the pure resolve_route()
priority-ordered resolution contract in praisonaiagents.gateway.protocols.
"""

from praisonaiagents.gateway import (
    RouteBinding,
    RouteFacts,
    RouteMatch,
    resolve_route,
)


class TestRouteBindingMatches:
    def test_empty_binding_matches_anything(self):
        b = RouteBinding(agent="a")
        assert b.matches(RouteFacts(chat_type="dm", peer="1"))

    def test_peer_match(self):
        b = RouteBinding(agent="vip", peer="12345")
        assert b.matches(RouteFacts(peer="12345"))
        assert not b.matches(RouteFacts(peer="99999"))

    def test_peer_match_is_string_coerced(self):
        b = RouteBinding(agent="vip", peer="12345")
        assert b.matches(RouteFacts(peer=12345))  # int facts still match

    def test_chat_type_match(self):
        b = RouteBinding(agent="assistant", chat_type="dm")
        assert b.matches(RouteFacts(chat_type="dm"))
        assert not b.matches(RouteFacts(chat_type="group"))

    def test_channel_id_match(self):
        b = RouteBinding(agent="ops", channel_id="-100999")
        assert b.matches(RouteFacts(channel_id="-100999"))
        assert not b.matches(RouteFacts(channel_id="-100000"))

    def test_account_match(self):
        b = RouteBinding(agent="acc", account="botA")
        assert b.matches(RouteFacts(account="botA"))
        assert not b.matches(RouteFacts(account="botB"))

    def test_role_match(self):
        b = RouteBinding(agent="support", role="support")
        assert b.matches(RouteFacts(roles=["support", "vip"]))
        assert not b.matches(RouteFacts(roles=["general"]))

    def test_role_match_is_string_coerced(self):
        b = RouteBinding(agent="ops", role=12345)
        assert b.matches(RouteFacts(roles=["12345"]))
        assert not b.matches(RouteFacts(roles=["99999"]))

    def test_combined_conditions_require_all(self):
        b = RouteBinding(agent="x", peer="1", chat_type="dm")
        assert b.matches(RouteFacts(peer="1", chat_type="dm"))
        assert not b.matches(RouteFacts(peer="1", chat_type="group"))


class TestSpecificity:
    def test_peer_is_most_specific(self):
        assert RouteBinding(agent="a", peer="1").specificity > \
            RouteBinding(agent="a", role="r").specificity

    def test_role_and_channel_above_account(self):
        assert RouteBinding(agent="a", role="r").specificity > \
            RouteBinding(agent="a", account="x").specificity

    def test_account_above_chat_type(self):
        assert RouteBinding(agent="a", account="x").specificity > \
            RouteBinding(agent="a", chat_type="dm").specificity

    def test_empty_binding_zero_specificity(self):
        assert RouteBinding(agent="a").specificity == 0


class TestResolveRoute:
    def test_no_bindings_uses_default(self):
        m = resolve_route([], RouteFacts(peer="1"), default_agent="general")
        assert isinstance(m, RouteMatch)
        assert m.agent == "general"
        assert m.binding is None

    def test_peer_beats_chat_type_by_specificity(self):
        bindings = [
            RouteBinding(agent="assistant", chat_type="dm"),
            RouteBinding(agent="vip", peer="12345"),
        ]
        m = resolve_route(bindings, RouteFacts(chat_type="dm", peer="12345"))
        assert m.agent == "vip"

    def test_priority_overrides_specificity(self):
        bindings = [
            RouteBinding(agent="vip", peer="12345"),
            RouteBinding(agent="override", chat_type="dm", priority=100),
        ]
        m = resolve_route(bindings, RouteFacts(chat_type="dm", peer="12345"))
        assert m.agent == "override"

    def test_role_routes_to_support(self):
        bindings = [
            RouteBinding(agent="support", role="support"),
            RouteBinding(agent="general", chat_type="group"),
        ]
        m = resolve_route(bindings, RouteFacts(chat_type="group", roles=["support"]))
        assert m.agent == "support"

    def test_channel_id_routes_to_ops(self):
        bindings = [RouteBinding(agent="ops", channel_id="-100999")]
        m = resolve_route(
            bindings,
            RouteFacts(chat_type="group", channel_id="-100999"),
            default_agent="general",
        )
        assert m.agent == "ops"

    def test_unmatched_falls_back_to_default(self):
        bindings = [RouteBinding(agent="vip", peer="12345")]
        m = resolve_route(
            bindings, RouteFacts(peer="99999"), default_agent="general"
        )
        assert m.agent == "general"
        assert m.binding is None

    def test_tie_broken_by_declaration_order(self):
        bindings = [
            RouteBinding(agent="first", chat_type="dm"),
            RouteBinding(agent="second", chat_type="dm"),
        ]
        m = resolve_route(bindings, RouteFacts(chat_type="dm"))
        assert m.agent == "first"

    def test_reason_is_populated(self):
        bindings = [RouteBinding(agent="vip", peer="1")]
        m = resolve_route(bindings, RouteFacts(peer="1"))
        assert "matched binding" in m.reason


class TestFromDict:
    def test_from_dict_basic(self):
        b = RouteBinding.from_dict({"peer": 12345, "agent": "vip"})
        assert b.agent == "vip"
        assert b.peer == "12345"

    def test_from_dict_defaults_agent(self):
        b = RouteBinding.from_dict({"chat_type": "dm"})
        assert b.agent == "default"

    def test_from_dict_ignores_unknown_keys(self):
        b = RouteBinding.from_dict({"agent": "a", "future_field": "x"})
        assert b.agent == "a"


class TestProfileIsolation:
    """Per-route isolated tenant-profile dimension (Issue #3189)."""

    def test_profile_defaults_to_none(self):
        assert RouteBinding(agent="a").profile is None

    def test_from_dict_parses_profile(self):
        b = RouteBinding.from_dict({"agent": "support", "profile": "acme"})
        assert b.profile == "acme"

    def test_from_dict_profile_is_string_coerced(self):
        b = RouteBinding.from_dict({"agent": "a", "profile": 42})
        assert b.profile == "42"

    def test_resolve_surfaces_matched_profile(self):
        bindings = [
            RouteBinding(agent="support", channel_id="discord-acme", profile="acme"),
            RouteBinding(agent="support", channel_id="slack-globex", profile="globex"),
        ]
        m = resolve_route(bindings, RouteFacts(channel_id="slack-globex"))
        assert m.agent == "support"
        assert m.profile == "globex"

    def test_unmatched_route_fails_closed_no_profile(self):
        # A route with no matching binding must never inherit another
        # tenant's profile — the fallback carries profile=None.
        bindings = [RouteBinding(agent="support", channel_id="discord-acme", profile="acme")]
        m = resolve_route(
            bindings,
            RouteFacts(channel_id="unknown"),
            default_agent="support",
        )
        assert m.binding is None
        assert m.profile is None

    def test_unscoped_binding_has_no_profile(self):
        bindings = [RouteBinding(agent="support", chat_type="dm")]
        m = resolve_route(bindings, RouteFacts(chat_type="dm"))
        assert m.binding is not None
        assert m.profile is None

    def test_blank_profile_is_normalised_to_none(self):
        # An empty or whitespace-only profile must be treated as unscoped
        # (None), not as an empty-named scope, to honour the fail-closed
        # contract a wrapper checking ``if profile is not None`` relies on.
        assert RouteBinding(agent="a", profile="").profile is None
        assert RouteBinding(agent="a", profile="   ").profile is None
        assert RouteBinding.from_dict({"agent": "a", "profile": ""}).profile is None
        assert RouteBinding.from_dict({"agent": "a", "profile": "  "}).profile is None


class TestThreadGuildParentMatching:
    """Thread-, guild-, and parent-chain route matching (Issue #4839)."""

    def test_new_facts_default_to_none(self):
        f = RouteFacts()
        assert f.thread_id is None
        assert f.guild_id is None
        assert f.parent_channel_id is None

    def test_new_bindings_default_to_none(self):
        b = RouteBinding(agent="a")
        assert b.thread_id is None
        assert b.guild_id is None

    def test_thread_id_match(self):
        b = RouteBinding(agent="escalations", thread_id="77")
        assert b.matches(RouteFacts(thread_id="77"))
        assert not b.matches(RouteFacts(thread_id="88"))

    def test_thread_id_is_string_coerced(self):
        b = RouteBinding(agent="a", thread_id="77")
        assert b.matches(RouteFacts(thread_id=77))

    def test_guild_id_match(self):
        b = RouteBinding(agent="support", guild_id="9001")
        assert b.matches(RouteFacts(guild_id="9001"))
        assert not b.matches(RouteFacts(guild_id="9002"))

    def test_guild_matches_any_channel_in_it(self):
        # One rule covers every channel in the guild, current and future.
        b = RouteBinding(agent="support", guild_id="9001")
        assert b.matches(RouteFacts(guild_id="9001", channel_id="111"))
        assert b.matches(RouteFacts(guild_id="9001", channel_id="999-new"))

    def test_channel_id_parent_chain_match(self):
        # A channel_id condition also matches a thread whose parent is that
        # channel, without listing each thread.
        b = RouteBinding(agent="sales", channel_id="333")
        assert b.matches(RouteFacts(channel_id="333"))
        assert b.matches(
            RouteFacts(channel_id="thread-abc", parent_channel_id="333")
        )
        assert not b.matches(
            RouteFacts(channel_id="thread-abc", parent_channel_id="444")
        )

    def test_thread_is_most_specific(self):
        assert RouteBinding(agent="a", thread_id="1").specificity > \
            RouteBinding(agent="a", peer="1").specificity

    def test_guild_specificity_below_channel(self):
        assert RouteBinding(agent="a", channel_id="1").specificity > \
            RouteBinding(agent="a", guild_id="1").specificity

    def test_thread_beats_guild_in_resolution(self):
        bindings = [
            RouteBinding(agent="support", guild_id="9001", profile="acme"),
            RouteBinding(agent="escalations", thread_id="77", profile="acme"),
        ]
        facts = RouteFacts(
            chat_type="channel", channel_id="333", thread_id="77",
            guild_id="9001", parent_channel_id="333",
        )
        m = resolve_route(bindings, facts)
        assert m.agent == "escalations"

    def test_channel_route_covers_its_threads(self):
        bindings = [
            RouteBinding(agent="support", guild_id="9001"),
            RouteBinding(agent="sales", channel_id="333"),
        ]
        # A message in a thread under channel 333 hits the channel rule (more
        # specific than the guild rule).
        facts = RouteFacts(
            channel_id="thread-abc", parent_channel_id="333", guild_id="9001",
        )
        m = resolve_route(bindings, facts)
        assert m.agent == "sales"

    def test_whole_server_routing(self):
        bindings = [RouteBinding(agent="support", guild_id="9001", profile="acme")]
        m = resolve_route(
            bindings,
            RouteFacts(guild_id="9001", channel_id="brand-new-channel"),
            default_agent="general",
        )
        assert m.agent == "support"
        assert m.profile == "acme"

    def test_from_dict_parses_thread_and_guild(self):
        b = RouteBinding.from_dict(
            {"agent": "a", "thread_id": 77, "guild_id": 9001}
        )
        assert b.thread_id == "77"
        assert b.guild_id == "9001"

    def test_backward_compatible_ignores_new_facts(self):
        # A legacy channel-only binding resolves exactly as before even when
        # the richer facts are present.
        bindings = [RouteBinding(agent="ops", channel_id="333")]
        m = resolve_route(
            bindings,
            RouteFacts(channel_id="333", thread_id="77", guild_id="9001"),
        )
        assert m.agent == "ops"
