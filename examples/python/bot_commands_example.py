"""
Bot Commands Example — Built-in /status, /new, /help commands.

Every PraisonAI bot comes with built-in chat commands:
  /status — Show agent info + uptime
  /new    — Reset conversation session
  /help   — List available commands

Usage:
    1. Set environment variables:
        export OPENAI_API_KEY=your_key
        export TELEGRAM_BOT_TOKEN=your_token

    2. Run:
        python bot_commands_example.py

    3. Open your Telegram bot and type:
        /status
        /help
        /new
"""

import asyncio
from praisonai.bots import TelegramBot
from praisonaiagents import Agent

# Create an agent
agent = Agent(
    name="assistant",
    instructions="You are a helpful assistant. Answer questions clearly and concisely.",
    llm="gpt-4o-mini",
)

# Create Telegram bot — commands are built-in automatically
bot = TelegramBot(
    token="YOUR_TELEGRAM_BOT_TOKEN",  # Replace or use os.environ
    agent=agent,
)

if __name__ == "__main__":
    print("Starting Telegram bot with built-in commands...")
    print("Available commands: /status, /new, /help")
    asyncio.run(bot.start())
