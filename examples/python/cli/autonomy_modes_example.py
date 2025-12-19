"""
Autonomy Modes Example for PraisonAI CLI.

Control AI autonomy: suggest, auto_edit, full_auto.
Docs: https://docs.praison.ai/cli/autonomy-modes
"""

from praisonai.cli.features import AutonomyModeHandler
from praisonai.cli.features.autonomy_mode import ActionRequest, ActionType

# Initialize with suggest mode (safest)
handler = AutonomyModeHandler()
manager = handler.initialize(mode="suggest")

print(f"Current mode: {handler.get_mode()}")
print("Available modes: suggest, auto_edit, full_auto")

# Create an action request
action = ActionRequest(
    action_type=ActionType.FILE_WRITE,
    description="Edit src/main.py to add logging",
    details={"file": "src/main.py"}
)

# In suggest mode, this would require approval
# For demo, we'll just show the action
print(f"\nAction: {action.description}")
print(f"Type: {action.action_type.value}")
print("Would require approval in 'suggest' mode")

# Change to auto_edit mode
handler.set_mode("auto_edit")
print(f"\nChanged to: {handler.get_mode()}")
print("File edits now auto-approved, shell commands still require approval")

# Get statistics
stats = handler.get_stats()
print(f"\nStats: {stats}")
