"""Tests for runtime credential/auth failure as a first-class state (Issue #3348).

A channel whose credential is rejected at runtime (revoked/rotated/expired
token -> 401/403) must:
  * be classified distinctly from transient and generic-fatal errors;
  * enter a named, redacted ``CREDENTIAL_UNAVAILABLE`` degraded state instead of
    the terminal ``FAILED`` state (no full-restart requirement);
  * stop hammering the invalid token in a tight reconnect loop; and
  * auto-recover on ``reconnect()`` (credential repaired) without a restart.
"""

from __future__ import annotations

import asyncio

import pytest

from praisonai_bot.bots._resilience import is_credential_error, is_recoverable_error
from praisonai_bot.gateway.supervisor import ChannelState, ChannelSupervisor


class _AuthError(Exception):
    """Auth rejection carrying an HTTP-style status code."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def test_classifier_401_403_are_credential_not_recoverable():
    assert is_credential_error(_AuthError("nope", 401)) is True
    assert is_credential_error(_AuthError("nope", 403)) is True
    # A credential rejection must NOT be treated as transient/recoverable.
    assert is_recoverable_error(_AuthError("nope", 401)) is False


def test_classifier_platform_text_equivalents():
    assert is_credential_error(Exception("invalid_auth"))
    assert is_credential_error(Exception("Slack error: token_revoked"))
    assert is_credential_error(Exception("401 Unauthorized"))
    assert is_credential_error(Exception("The access token is invalid"))


def test_classifier_ignores_transient():
    assert is_credential_error(Exception("connection reset by peer")) is False
    assert is_credential_error(ConnectionError("timed out")) is False


def test_runtime_credential_rejection_enters_degraded_state():
    """A 401 at runtime -> CREDENTIAL_UNAVAILABLE (not FAILED), then recovers."""

    recovered = asyncio.Event()
    calls = {"n": 0}

    async def start_fn(name, bot):
        calls["n"] += 1
        if calls["n"] == 1:
            # First boot: credential rejected.
            raise _AuthError("401 Unauthorized: invalid token", 401)
        # After the operator fixes the token and reconnects: hold (running).
        recovered.set()
        await asyncio.Event().wait()

    sup = ChannelSupervisor()

    async def scenario():
        task = asyncio.create_task(sup.run("slack", object(), start_fn))
        # Wait until the supervisor parks in the credential-unavailable state.
        for _ in range(200):
            st = sup.get_status("slack")
            if st.state == ChannelState.CREDENTIAL_UNAVAILABLE:
                break
            await asyncio.sleep(0.01)

        st = sup.get_status("slack")
        assert st.state == ChannelState.CREDENTIAL_UNAVAILABLE
        # Redacted: never leaks the token / raw error text.
        assert st.last_error == "credential unavailable"
        assert "token" not in (st.last_error or "").lower()

        # Operator repairs the credential and forces a reconnect: auto-recover.
        assert sup.reconnect("slack") is True
        await asyncio.wait_for(recovered.wait(), timeout=2.0)
        assert sup.get_status("slack").state == ChannelState.RUNNING

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(asyncio.wait_for(scenario(), timeout=5.0))


def test_reconnect_resources_credential_via_refresh_hook():
    """Issue #3348: a bot exposing refresh_credentials() re-sources its token
    on wake so the *same* instance recovers after an out-of-band repair — it
    does not restart still holding the rejected credential."""

    recovered = asyncio.Event()

    class _Bot:
        platform = "slack"

        def __init__(self):
            self.token = "bad"
            self.refreshed = 0

        def refresh_credentials(self):
            # Operator repaired the credential out-of-band (e.g. rotated env).
            self.token = "good"
            self.refreshed += 1

    bot = _Bot()

    async def start_fn(name, b):
        if b.token != "good":
            raise _AuthError("401 Unauthorized: invalid token", 401)
        recovered.set()
        await asyncio.Event().wait()

    sup = ChannelSupervisor()

    async def scenario():
        task = asyncio.create_task(sup.run("slack", bot, start_fn))
        for _ in range(200):
            if sup.get_status("slack").state == ChannelState.CREDENTIAL_UNAVAILABLE:
                break
            await asyncio.sleep(0.01)
        assert sup.get_status("slack").state == ChannelState.CREDENTIAL_UNAVAILABLE

        assert sup.reconnect("slack") is True
        await asyncio.wait_for(recovered.wait(), timeout=2.0)
        assert bot.refreshed == 1
        assert sup.get_status("slack").state == ChannelState.RUNNING

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(asyncio.wait_for(scenario(), timeout=5.0))


def test_generic_fatal_still_failed():
    """A non-auth, non-recoverable error stays terminal FAILED (unchanged)."""

    async def start_fn(name, bot):
        raise ValueError("totally unexpected programming error")

    sup = ChannelSupervisor()
    asyncio.run(asyncio.wait_for(sup.run("slack", object(), start_fn), timeout=5.0))
    assert sup.get_status("slack").state == ChannelState.FAILED
