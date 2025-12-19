"""
Interactive TUI Example for PraisonAI CLI.

Rich terminal interface with completions and history.
Docs: https://docs.praison.ai/cli/interactive-tui
"""

from praisonai.cli.features import InteractiveTUIHandler
from praisonai.cli.features.interactive_tui import InteractiveConfig

# Custom configuration
config = InteractiveConfig(
    prompt="ai> ",
    multiline=True,
    enable_completions=True,
    show_status_bar=True
)

# Define callbacks
def on_input(text):
    """Handle regular input."""
    return f"You said: {text}"

def on_command(cmd):
    """Handle slash commands."""
    if cmd == "/exit":
        return {"type": "exit"}
    return {"type": "command", "message": f"Executed: {cmd}"}

# Initialize
handler = InteractiveTUIHandler()
session = handler.initialize(
    config=config,
    on_input=on_input,
    on_command=on_command
)

# Add commands for completion
session.add_commands(["help", "exit", "cost", "model", "plan"])

# Add symbols from codebase
session.add_symbols(["MyClass", "my_function"])

print("Interactive TUI initialized!")
print("Commands available: /help, /exit, /cost, /model, /plan")
print("Run handler.run() to start interactive session")

# Uncomment to run interactive session:
# handler.run()
