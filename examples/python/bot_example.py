"""
Messaging Bot Example - Deploy Agents to Telegram, Discord, Slack

This example demonstrates how to configure bots for different
messaging platforms.
"""

import os
from praisonaiagents import Agent, BotConfig

# Telegram Bot Configuration
telegram_config = BotConfig(
    token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    command_prefix="/",
    mention_required=True,
    typing_indicator=True,
    max_message_length=4096,
    metadata={"platform": "telegram"}
)

# Discord Bot Configuration
discord_config = BotConfig(
    token=os.environ.get("DISCORD_BOT_TOKEN", ""),
    command_prefix="!",
    mention_required=True,
    typing_indicator=True,
    metadata={
        "platform": "discord",
        "guild_ids": []  # Add your guild IDs here
    }
)

# Slack Bot Configuration
slack_config = BotConfig(
    token=os.environ.get("SLACK_BOT_TOKEN", ""),
    command_prefix="/",
    mention_required=True,
    typing_indicator=True,
    metadata={
        "platform": "slack",
        "app_token": os.environ.get("SLACK_APP_TOKEN", "")
    }
)

# Create the agent that will handle messages
assistant = Agent(
    name="assistant",
    instructions="""You are a helpful assistant that responds to messages 
    from users on messaging platforms. Be friendly and concise.""",
    llm="gpt-4o-mini"
)

if __name__ == "__main__":
    print("Bot Configurations:")
    print()
    
    print("Telegram Config:")
    print(f"  Token configured: {bool(telegram_config.token)}")
    print(f"  Command prefix: {telegram_config.command_prefix}")
    print(f"  Mention required: {telegram_config.mention_required}")
    print()
    
    print("Discord Config:")
    print(f"  Token configured: {bool(discord_config.token)}")
    print(f"  Command prefix: {discord_config.command_prefix}")
    print()
    
    print("Slack Config:")
    print(f"  Token configured: {bool(slack_config.token)}")
    print(f"  Command prefix: {slack_config.command_prefix}")
    print()
    
    print("To start a bot, use the CLI:")
    print("  praisonai bot telegram --token $TELEGRAM_BOT_TOKEN")
    print("  praisonai bot discord --token $DISCORD_BOT_TOKEN")
    print("  praisonai bot slack --token $SLACK_BOT_TOKEN")
