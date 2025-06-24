import logging
import warnings

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

__all__ = ["LLM", "LLMContextLengthExceededException"]
