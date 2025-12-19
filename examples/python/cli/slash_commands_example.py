"""
Slash Commands Example for PraisonAI CLI.

Demonstrates interactive slash commands like /help, /cost, /model.
Docs: https://docs.praison.ai/cli/slash-commands
"""

from praisonai.cli.features import SlashCommandHandler
from praisonai.cli.features.slash_commands import SlashCommand, CommandKind

# Create handler
handler = SlashCommandHandler()

# Execute commands
print("=== /help ===")
result = handler.execute("/help")
print(result.get("message", ""))

print("\n=== /cost ===")
result = handler.execute("/cost")
print(result.get("message", ""))

print("\n=== /model ===")
result = handler.execute("/model")
print(result.get("message", ""))

# Check if input is a command
print("\n=== Command Detection ===")
print(f"/help is command: {handler.is_command('/help')}")
print(f"hello is command: {handler.is_command('hello')}")

# Get completions for auto-complete
print("\n=== Completions for '/he' ===")
completions = handler.get_completions("/he")
print(completions)

# Register custom command
def my_custom_handler(args, context):
    return {"type": "custom", "message": f"Custom command with args: {args}"}

custom_cmd = SlashCommand(
    name="mycommand",
    description="My custom command",
    handler=my_custom_handler,
    kind=CommandKind.ACTION,
    aliases=["mc"]
)

handler.register(custom_cmd)
result = handler.execute("/mycommand arg1 arg2")
print(f"\n=== Custom Command ===\n{result.get('message', '')}")
