"""Requester-bound pairing and cross-writer persistence regressions (#6022)."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

from praisonai_bot.gateway.pairing import PairingStore
from praisonai_bot.bots._pairing_ui import PairingCallbackHandler
from praisonai_bot.bots._unknown_user import UnknownUserHandler, BotContext
from praisonaiagents.bots import BotMessage, BotUser, BotChannel


def store(tmp_path, **kwargs):
    """Every test uses an exclusive synthetic store and signing secret."""
    return PairingStore(store_dir=str(tmp_path), secret="synthetic-test-secret", **kwargs)


def test_unknown_sender_is_bound_and_reuses_one_slot(tmp_path):
    """Repeated inbound messages cannot consume every pending slot."""
    pairing = store(tmp_path, max_pending=2)
    adapter = SimpleNamespace(reply=AsyncMock(), send_approval_dm=AsyncMock())
    message = BotMessage(content="hi", sender=BotUser(user_id="requester"),
                         channel=BotChannel(channel_id="requester", channel_type="dm"))
    message._channel_type = "telegram"
    context = BotContext(config=SimpleNamespace(unknown_user_policy="pair"),
                         pairing_store=pairing, adapter=adapter)
    for _ in range(3):
        asyncio.run(UnknownUserHandler.handle(message, context))
    pending = pairing.list_pending()
    assert len(pending) == 1
    assert pending[0]["user_id"] == "requester"
    code = pending[0]["code"]
    assert pairing.approve("telegram", code)
    assert pairing.is_paired("requester", "telegram")
    assert not pairing.is_paired(code, "telegram")


def test_missing_binding_does_not_burn_code(tmp_path):
    """A legacy unbound code requires an explicit identity, not the code string."""
    pairing = store(tmp_path)
    code = pairing.generate_code("telegram")
    assert not pairing.approve("telegram", code)
    assert pairing.verify_and_pair(code, "requester", "telegram")


def test_channel_mismatch_preserves_valid_binding(tmp_path):
    """A code cannot authorize another platform or requester."""
    pairing = store(tmp_path)
    code = pairing.generate_code("telegram", "requester")
    assert not pairing.verify_and_pair(code, "requester", "slack")
    assert not pairing.verify_and_pair(code, "other", "telegram")
    assert pairing.verify_and_pair(code, None, "telegram")


def test_deny_consumes_without_creating_pair(tmp_path, monkeypatch):
    """The real callback branch rejects rather than persisting dummy identities."""
    pairing = store(tmp_path)
    code = pairing.generate_code("telegram")  # Legacy unbound pending request.
    handler = PairingCallbackHandler(pairing)
    monkeypatch.setattr(handler, "parse_and_verify_callback", lambda data: {
        "action": "deny", "channel": "telegram", "code": code, "user_id": "requester"})
    result = asyncio.run(handler.handle_approval_callback("signed", "owner", SimpleNamespace()))
    assert result.success
    assert pairing.list_paired() == []
    assert not pairing.verify_and_pair(code, None, "telegram")


def test_existing_instances_see_approvals_and_revocations(tmp_path):
    """A bot neither misses another writer's approval nor restores a revoked pair."""
    bot, gateway = store(tmp_path), store(tmp_path)
    code = bot.generate_code("telegram", "requester")
    assert gateway.approve("telegram", code)
    assert bot.is_paired("requester", "telegram")
    bot.generate_code("slack", "another")
    assert store(tmp_path).is_paired("requester", "telegram")
    assert gateway.revoke("requester", "telegram")
    bot.generate_code("discord", "third")
    assert not bot.is_paired("requester", "telegram")
    assert not store(tmp_path).is_paired("requester", "telegram")


def test_cli_without_explicit_id_approves_requester(tmp_path, monkeypatch):
    """The documented approve PLATFORM CODE command uses the stored requester."""
    from typer.testing import CliRunner
    from praisonai_bot.cli.commands import pairing as cli

    pairing = store(tmp_path)
    code = pairing.generate_code("telegram", "requester")
    monkeypatch.setattr(cli, "PairingStore", lambda store_dir=None: store(tmp_path))
    result = CliRunner().invoke(cli.app, ["approve", "telegram", code])
    assert result.exit_code == 0, result.output
    assert pairing.is_paired("requester", "telegram")
    assert not pairing.is_paired(code, "telegram")


def test_separate_process_approval_is_visible(tmp_path):
    """An existing bot sees a real other process's write without restart."""
    import subprocess
    import sys

    pairing = store(tmp_path)
    code = pairing.generate_code("telegram", "requester")
    script = (
        "import sys; from praisonai_bot.gateway.pairing import PairingStore; "
        "s=PairingStore(store_dir=sys.argv[1], secret='synthetic-test-secret'); "
        "assert s.verify_and_pair(sys.argv[2], None, 'telegram')"
    )
    subprocess.run([sys.executable, "-c", script, str(tmp_path), code], check=True, timeout=15)
    assert pairing.is_paired("requester", "telegram")
    pairing.generate_code("slack", "another")
    assert store(tmp_path).is_paired("requester", "telegram")


def test_concurrent_store_writers_do_not_lose_distinct_approvals(tmp_path):
    """Separate store objects commit complete locked read-modify-write units."""
    original = store(tmp_path)
    codes = [(original.generate_code("telegram", str(i)), str(i)) for i in range(8)]
    writers = [store(tmp_path) for _ in codes]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda pair: pair[0].approve("telegram", pair[1][0]), zip(writers, codes)))
    assert all(results)
    assert {item.channel_id for item in original.list_paired()} == {str(i) for i in range(8)}
