import logging
import warnings
import os

# Disable litellm telemetry before any imports
os.environ["LITELLM_TELEMETRY"] = "False"

# Suppress all relevant logs at module level
logging.getLogger("litellm").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("pydantic").setLevel(logging.ERROR)

# Suppress pydantic warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Configure logging to suppress all INFO messages
logging.basicConfig(level=logging.WARNING)

# Import after suppressing warnings
from .llm import LLM, LLMContextLengthExceededException

# Ensure telemetry is disabled after import as well
try:
    import litellm
    litellm.telemetry = False
except ImportError:
    pass

__all__ = ["LLM", "LLMContextLengthExceededException"]
