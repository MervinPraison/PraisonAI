"""Every chat channel applies the sender allow-list before the agent runs.

The email channels (IMAP/SMTP and AgentMail) handed any sender's mail to the
agent, ignoring ``allowed_users`` and ``unknown_user_policy``. They now use
the shared ``is_sender_allowed``. The guard test walks every adapter module
that runs the agent and fails if it has no allow-list check and is not on the
reasoned exemption list.
"""

import ast
import asyncio
from pathlib import Path

import pytest

from praisonaiagents.bots import BotChannel, BotConfig, BotMessage, BotUser, MessageType

BOTS_DIR = Path(__file__).resolve().parents[3] / "praisonai_bot" / "bots"
BOSS, STRANGER = "boss@corp.example", "stranger@foreign.example"


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))


def _mail(sender):
    return BotMessage(
        message_id="m1", content="Subject: hi\n\nrun the payroll export", message_type=MessageType.TEXT,
        sender=BotUser(user_id=sender, username=sender, display_name=sender),
        channel=BotChannel(channel_id=sender, name=sender, channel_type="dm"),
        metadata={"subject": "hi"},
    )


def _email_bot(config):
    from praisonai_bot.bots.email import EmailBot

    return EmailBot(token="x", agent=object(), config=config, email_address="bot@corp.example")


def _agentmail_bot(config):
    pytest.importorskip("agentmail")
    from praisonai_bot.bots.agentmail import AgentMailBot

    return AgentMailBot(token="x", agent=object(), config=config)


@pytest.mark.parametrize("factory", [_email_bot, _agentmail_bot])
@pytest.mark.parametrize("sender, policy, reached", [
    (BOSS, "deny", True),
    (STRANGER, "deny", False),
    (STRANGER, "pair", False),
    (STRANGER, "allow", True),
])
def test_email_channels_apply_the_allow_list(factory, sender, policy, reached):
    bot = factory(BotConfig(token="x", allowed_users=[BOSS], unknown_user_policy=policy))
    seen = []

    class Session:
        async def chat(self, agent, user_id, body, **kw):
            seen.append(user_id)
            return None

    bot._session = Session()
    asyncio.run(bot._handle_message(_mail(sender)))
    assert bool(seen) is reached


# Adapters that run the agent without the user allow-list, and why.
EXEMPT = {
    "local.py": "the operator's own terminal; owner-trusted by design",
    "webhook.py": "machine triggers authenticated by HMAC (enforce_webhook_verification)",
    "linear.py": "Linear agent-session webhooks, signature-verified; Linear workspace access is the boundary",
    "whatsapp.py": "own allowed_numbers / allowed_groups filter",
    "signal.py": "own allowed_users filter (phone numbers)",
}
ALLOW_LIST_NAMES = {"is_sender_allowed", "is_explicitly_allowed", "UnknownUserHandler",
                    "process_inbound_telegram_message"}


def test_every_chat_adapter_checks_senders():
    unchecked = []
    runners = []
    for path in sorted(BOTS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        runs_agent = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "chat"
            for n in ast.walk(tree)
        )
        if not runs_agent:
            continue
        runners.append(path.name)
        if path.name not in EXEMPT and not names & ALLOW_LIST_NAMES:
            unchecked.append(path.name)
    assert {"telegram.py", "slack.py", "discord.py", "email.py", "agentmail.py"} <= set(runners)
    assert not unchecked, f"apply the sender allow-list (is_sender_allowed) in: {unchecked}"
