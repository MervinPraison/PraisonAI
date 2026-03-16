"""
Email Bot Example — Deploy an AI Agent to Your Mailbox

This example shows how to deploy PraisonAI agents as email bots
using IMAP/SMTP. The bot monitors an inbox, processes incoming emails,
and replies intelligently using an LLM-powered agent.

Supported providers:
  - Gmail (with App Password)
  - Outlook/Microsoft 365
  - Any IMAP/SMTP server

Environment Variables:
    export OPENAI_API_KEY=your_key
    export EMAIL_ADDRESS=support@example.com
    export EMAIL_APP_PASSWORD=your_app_password
    export EMAIL_IMAP_SERVER=imap.gmail.com    # optional, default: imap.gmail.com
    export EMAIL_SMTP_SERVER=smtp.gmail.com    # optional, default: smtp.gmail.com

Usage:
    python bot_email_example.py
"""

import asyncio
import os
from praisonaiagents import Agent


# ── Example 1: Minimal — Bot() wrapper (recommended) ──────────────

def example_minimal():
    """Minimal email bot — 3 lines to start."""
    from praisonai.bots import Bot

    agent = Agent(
        name="email_assistant",
        instructions="You are a helpful email assistant. Reply concisely and professionally.",
        llm="gpt-4o-mini",
    )

    # Token and server resolved from env vars automatically:
    #   EMAIL_APP_PASSWORD, EMAIL_ADDRESS, EMAIL_IMAP_SERVER, EMAIL_SMTP_SERVER
    bot = Bot("email", agent=agent)
    bot.run()  # Blocks until Ctrl+C


# ── Example 2: Custom configuration ───────────────────────────────

def example_with_config():
    """Email bot with explicit configuration."""
    from praisonai.bots import Bot
    from praisonaiagents import BotConfig

    config = BotConfig(
        polling_interval=30.0,         # Check inbox every 30s
        allowed_users=[                # Only respond to these senders
            "alice@example.com",
            "bob@example.com",
        ],
        max_message_length=10000,      # Allow long email replies
        session_ttl=86400,             # Clear session after 24h inactivity
        metadata={
            "imap_folder": "INBOX",    # Which folder to monitor
        },
    )

    agent = Agent(
        name="support_agent",
        instructions="""You are a technical support agent for ExampleCo.
        
        Guidelines:
        - Be professional and empathetic
        - Provide clear step-by-step solutions
        - If you don't know the answer, escalate to support@exampleco.com
        - Keep replies under 500 words
        """,
        llm="gpt-4o-mini",
    )

    bot = Bot("email", agent=agent, config=config)
    bot.run()


# ── Example 3: Direct EmailBot with custom handlers ──────────────

def example_direct():
    """Direct EmailBot usage with custom message handler and commands."""
    from praisonai.bots import EmailBot

    agent = Agent(
        name="smart_inbox",
        instructions="You help triage and respond to support emails.",
        llm="gpt-4o-mini",
    )

    bot = EmailBot(
        token=os.environ.get("EMAIL_APP_PASSWORD", ""),
        agent=agent,
        email_address=os.environ.get("EMAIL_ADDRESS", ""),
        imap_server=os.environ.get("EMAIL_IMAP_SERVER", "imap.gmail.com"),
        smtp_server=os.environ.get("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
    )

    # Custom message handler — runs on every incoming email
    @bot.on_message
    async def log_incoming(message):
        print(f"📧 New email from: {message.sender.username}")
        print(f"   Subject: {message.metadata.get('subject', '(no subject)')}")

    # Custom command — triggered when subject starts with "/status"
    @bot.on_command("status")
    async def handle_status(message):
        await bot.send_message(
            channel_id=message.sender.user_id,
            content={
                "subject": "Re: Bot Status",
                "body": f"🤖 Bot is running!\nProcessed emails: {bot._emails_processed}",
            },
            reply_to=message.message_id,
        )

    asyncio.run(bot.start())


# ── Example 4: Multi-platform with BotOS ─────────────────────────

def example_multi_platform():
    """Run email bot alongside Telegram and Discord bots."""
    from praisonai.bots import BotOS, Bot

    agent = Agent(
        name="omni_assistant",
        instructions="You are a helpful assistant available on email, Telegram, and Discord.",
        llm="gpt-4o-mini",
    )

    botos = BotOS(agent=agent, platforms=["email", "telegram", "discord"])
    botos.run()  # All three bots run concurrently


# ── Example 5: Probe connectivity ─────────────────────────────────

async def example_probe():
    """Test email server connectivity without starting the bot."""
    from praisonai.bots import Bot

    bot = Bot("email")
    result = await bot.probe()

    print(f"Connection OK: {result.ok}")
    print(f"Platform: {result.platform}")
    if result.bot_username:
        print(f"Email: {result.bot_username}")
    if result.error:
        print(f"Error: {result.error}")
    print(f"Latency: {result.elapsed_ms:.0f}ms")


# ── Example 6: YAML config (for praisonai bot CLI) ───────────────

YAML_EXAMPLE = """
# bot.yaml — Save this file and run: praisonai bot --config bot.yaml
agent:
  name: email_support
  instructions: >
    You are a professional support agent.
    Reply concisely and helpfully.
  llm: gpt-4o-mini
  tools:
    - search_web

platforms:
  email:
    token: ${EMAIL_APP_PASSWORD}
"""


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    examples = {
        "minimal": ("Minimal email bot", example_minimal),
        "config": ("With custom config", example_with_config),
        "direct": ("Direct EmailBot with handlers", example_direct),
        "multi": ("Multi-platform (email+telegram+discord)", example_multi_platform),
        "probe": ("Test connectivity", lambda: asyncio.run(example_probe())),
    }

    if len(sys.argv) > 1 and sys.argv[1] in examples:
        name = sys.argv[1]
        desc, fn = examples[name]
        print(f"Running: {desc}")
        fn()
    else:
        print("PraisonAI Email Bot Examples")
        print("=" * 40)
        print()
        print("Usage: python bot_email_example.py <example>")
        print()
        print("Available examples:")
        for key, (desc, _) in examples.items():
            print(f"  {key:10s}  {desc}")
        print()
        print("Required environment variables:")
        print("  OPENAI_API_KEY       Your OpenAI API key")
        print("  EMAIL_ADDRESS        Bot's email address")
        print("  EMAIL_APP_PASSWORD   App password (Gmail: myaccount.google.com/apppasswords)")
        print()
        print("Optional:")
        print("  EMAIL_IMAP_SERVER    IMAP server (default: imap.gmail.com)")
        print("  EMAIL_SMTP_SERVER    SMTP server (default: smtp.gmail.com)")
        print()
        print("YAML config example:")
        print(YAML_EXAMPLE)
