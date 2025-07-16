# Disable OpenTelemetry SDK
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["EC_TELEMETRY"] = "false"
from .cli import PraisonAI
from .version import __version__

# Re-export all classes from praisonaiagents to enable:
# from praisonai import Agent, Task, PraisonAIAgents
try:
    import praisonaiagents
    # Import all symbols from praisonaiagents using * import
    from praisonaiagents import *
except ImportError:
    # If praisonaiagents is not available, these imports will fail gracefully
    pass

# Define __all__ to include both PraisonAI core classes and praisonaiagents exports
__all__ = [
    # Core PraisonAI classes
    'PraisonAI',
    '__version__',
]

# Dynamically extend __all__ with praisonaiagents exports
try:
    import praisonaiagents
    __all__.extend(praisonaiagents.__all__)
except (ImportError, AttributeError):
    # If praisonaiagents is not available or doesn't have __all__, fail gracefully
    pass
