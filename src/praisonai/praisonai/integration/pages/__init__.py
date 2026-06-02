"""Optional L3 dashboard pages for PraisonAI integration."""

# Import pages to register them with aiui
try:
    from . import workflow_runs, bot_health
except ImportError:
    # Pages are optional and may not be available if aiui is not installed
    pass