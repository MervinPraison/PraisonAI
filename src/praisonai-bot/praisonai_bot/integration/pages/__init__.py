"""Optional L3 dashboard pages for PraisonAI bot integration."""

# Import pages to register them with aiui
try:
    from . import bot_health
except ImportError:
    # Pages are optional and may not be available if aiui is not installed
    pass
