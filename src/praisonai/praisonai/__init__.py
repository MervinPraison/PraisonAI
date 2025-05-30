# Disable OpenTelemetry SDK
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["EC_TELEMETRY"] = "false"

# Initialize directory management for clean organization
try:
    from .inc.directory_manager import initialize_directories
    # Initialize on import if not in Docker environment
    if not os.environ.get("DOCKER_CONTAINER"):
        initialize_directories(migrate=True)
except ImportError:
    # Directory manager is optional for backwards compatibility
    pass

from .cli import PraisonAI
from .version import __version__