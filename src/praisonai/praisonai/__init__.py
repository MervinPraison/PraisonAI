# Disable OpenTelemetry SDK
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["EC_TELEMETRY"] = "false"

# Directory management is available for explicit initialization
try:
    from .inc.directory_manager import initialize_directories
    # Note: Directory initialization should be called explicitly via CLI or setup
    # to avoid unexpected file operations on package import
except ImportError:
    # Directory manager is optional for backwards compatibility
    pass

from .cli import PraisonAI
from .version import __version__