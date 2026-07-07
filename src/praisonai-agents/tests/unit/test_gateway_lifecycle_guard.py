"""Unit tests for the gateway self-lifecycle command guardrail (Issue #2753).

Covers the pure, core-side decision policy ``LifecycleCommandGuardPolicy`` that
default-denies agent-issued commands whose effect is to stop / restart / kill
*this* gateway process (self-DoS via a shell tool or a scheduled job), while
leaving ordinary commands — and ordinary English — untouched.
"""

import pytest

from praisonaiagents.gateway import (
    LifecycleCommandDecision,
    LifecycleCommandGuardPolicy,
    LifecycleCommandPolicyProtocol,
)


# --- Denials: commands that target this gateway's own lifecycle -------------

@pytest.mark.parametrize(
    "command",
    [
        "praisonai gateway stop",
        "praisonai gateway restart",
        "praisonai gateway reload",
        "sudo praisonai gateway stop",
        "pkill -f 'praisonai gateway'",
        "pkill -f praisonai",
        "killall praisonai",
        "kill -9 $(pgrep -f 'praisonai gateway')" ,
        "systemctl --user stop praisonai-gateway",
        "systemctl stop praisonai",
        "launchctl stop com.praisonai.gateway",
        "service praisonai stop",
    ],
)
def test_self_lifecycle_commands_are_denied(command):
    policy = LifecycleCommandGuardPolicy()
    decision = policy.evaluate(command)
    assert decision.allow is False
    assert decision.reason
    assert decision.matched


def test_denied_in_a_compound_command():
    policy = LifecycleCommandGuardPolicy()
    # A benign prefix chained with a self-stop must still be caught.
    decision = policy.evaluate("echo hi && praisonai gateway stop")
    assert decision.allow is False
    assert "praisonai gateway stop" in decision.matched


def test_denied_when_piped():
    policy = LifecycleCommandGuardPolicy()
    decision = policy.evaluate("ps aux | pkill -f praisonai")
    assert decision.allow is False


# --- Allowances: benign commands and ordinary English -----------------------

@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "echo 'please stop the gateway from spamming'",
        "praisonai gateway status",
        "praisonai gateway start",
        "git commit -m 'restart the pipeline'",
        "pkill -f some-other-daemon",
        "systemctl stop nginx",
        "cat notes-about-how-to-stop-the-gateway.txt",
        "python train.py --restart",
        # Unrelated services whose name merely *contains* a configured token
        # must not be tripped (word-boundary matching, not bare substring).
        "pkill -f api-gateway",
        "pkill -f nginx-gateway",
        "systemctl stop kong-gateway",
        "systemctl restart my-gateway-proxy",
        "killall gatewayd",
    ],
)
def test_benign_commands_are_allowed(command):
    policy = LifecycleCommandGuardPolicy()
    decision = policy.evaluate(command)
    assert decision.allow is True
    assert decision.matched == ""


def test_prose_mentioning_stop_is_not_tripped():
    policy = LifecycleCommandGuardPolicy()
    # Matching is command-anchored, not prose-based.
    decision = policy.evaluate(
        "echo 'the operator asked me to stop and restart the gateway later'"
    )
    assert decision.allow is True


# --- Configuration surface --------------------------------------------------

def test_disabled_guard_allows_everything():
    policy = LifecycleCommandGuardPolicy(enabled=False)
    decision = policy.evaluate("praisonai gateway stop")
    assert decision.allow is True


def test_custom_process_names_are_honoured():
    policy = LifecycleCommandGuardPolicy(process_names=["mybot"])
    assert policy.evaluate("pkill -f mybot").allow is False
    # Default praisonai token is no longer in the deny set for kill matches.
    assert policy.evaluate("pkill -f praisonai").allow is True


def test_custom_process_names_govern_cli_rule():
    # Rule 1 (the ``<cli> gateway <verb>`` form) must honour process_names too,
    # not just the kill/service rules, so a renamed/forked CLI is covered.
    policy = LifecycleCommandGuardPolicy(process_names=["mybot"])
    assert policy.evaluate("mybot gateway stop").allow is False
    # praisonai remains covered by rule 1 as the project's own CLI.
    assert policy.evaluate("praisonai gateway stop").allow is False


def test_cli_rule_requires_adjacency():
    # ``gateway`` and a verb appearing non-adjacently (e.g. in an unrelated
    # argument list) must not trip rule 1 — matching is adjacency-anchored.
    policy = LifecycleCommandGuardPolicy()
    assert policy.evaluate("praisonai gateway status --stop-on-idle").allow is True


def test_empty_command_is_allowed():
    policy = LifecycleCommandGuardPolicy()
    assert policy.evaluate("").allow is True
    assert policy.evaluate("   ").allow is True
    assert policy.evaluate(None).allow is True  # type: ignore[arg-type]


def test_decision_is_frozen_dataclass():
    decision = LifecycleCommandDecision(allow=False, reason="x", matched="y")
    with pytest.raises(Exception):
        decision.allow = True  # type: ignore[misc]


def test_default_guard_satisfies_protocol():
    policy = LifecycleCommandGuardPolicy()
    assert isinstance(policy, LifecycleCommandPolicyProtocol)
