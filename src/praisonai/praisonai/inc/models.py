# praisonai/inc/models.py
# PERFORMANCE OPTIMIZED: Removed all LangChain imports
# Uses direct OpenAI SDK for fast startup (~600ms vs ~3200ms with langchain_openai)
import os
import logging
from urllib.parse import urlparse
import importlib.util

logger = logging.getLogger(__name__)
_loglevel = os.environ.get('LOGLEVEL', 'INFO').strip().upper() or 'INFO'
logging.basicConfig(level=_loglevel, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
LOCAL_SERVER_API_KEY_PLACEHOLDER = "not-needed"

# Use find_spec for fast availability checks (no actual import)
# This avoids the ~3200ms langchain_openai import at module load
OPENAI_AVAILABLE = importlib.util.find_spec("openai") is not None
GOOGLE_GENAI_AVAILABLE = importlib.util.find_spec("google.generativeai") is not None
ANTHROPIC_AVAILABLE = importlib.util.find_spec("anthropic") is not None
COHERE_AVAILABLE = importlib.util.find_spec("cohere") is not None

# Lazy import helpers for provider SDKs
def _get_openai_client():
    """Lazy import OpenAI client."""
    from openai import OpenAI
    return OpenAI

def _get_google_genai():
    """Lazy import Google Generative AI."""
    import google.generativeai as genai
    return genai

def _get_anthropic_client():
    """Lazy import Anthropic client."""
    from anthropic import Anthropic
    return Anthropic

def _get_cohere_client():
    """Lazy import Cohere client."""
    import cohere
    return cohere

class PraisonAIModel:
    def __init__(self, model=None, api_key_var=None, base_url=None, api_key=None):
        """
        Initializes the PraisonAIModel with the provided parameters or environment variables.

        Args:
            model (str, optional): The name of the OpenAI model. Defaults to None.
            api_key_var (str, optional): The environment variable name for the API key. Defaults to None.
            base_url (str, optional): The base URL for the OpenAI API. Defaults to None.
            api_key (str, optional): The explicit API key to use. Takes precedence over environment variables. Defaults to None.
        """
        self.model =  model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        if self.model.startswith("openai/"):
            self.api_key_var = "OPENAI_API_KEY"
            self.base_url = base_url or "https://api.openai.com/v1"
            self.model_name = self.model.replace("openai/", "")
        elif self.model.startswith("groq/"):
            self.api_key_var = "GROQ_API_KEY"
            self.base_url = base_url or "https://api.groq.com/openai/v1"
            self.model_name = self.model.replace("groq/", "")
        elif self.model.startswith("cohere/"):
            self.api_key_var = "COHERE_API_KEY"
            self.base_url = ""
            self.model_name = self.model.replace("cohere/", "")
        elif self.model.startswith("ollama/"):
            self.api_key_var = "OLLAMA_API_KEY"
            self.base_url = base_url or "http://localhost:11434/v1"
            self.model_name = self.model.replace("ollama/", "")
        elif self.model.startswith("anthropic/"):
            self.api_key_var = "ANTHROPIC_API_KEY"
            self.base_url = ""
            self.model_name = self.model.replace("anthropic/", "")
        elif self.model.startswith("google/"):
            self.api_key_var = "GOOGLE_API_KEY"
            self.base_url = ""
            self.model_name = self.model.replace("google/", "")
        elif self.model.startswith("openrouter/"):
            self.api_key_var = "OPENROUTER_API_KEY"
            self.base_url = base_url or "https://openrouter.ai/api/v1"
            self.model_name = self.model.replace("openrouter/", "")
        else: 
            self.api_key_var = api_key_var or "OPENAI_API_KEY" 
            self.base_url = base_url or os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            self.model_name = self.model
        logger.debug(f"Initialized PraisonAIModel with model {self.model_name}, api_key_var {self.api_key_var}, and base_url {self.base_url}")

        # Get API key from environment
        self.api_key = api_key or os.environ.get(self.api_key_var)
        
        # For local servers, allow placeholder API key if base_url is set to non-OpenAI endpoint
        if not self.api_key and self.base_url:
            parsed_url = urlparse(self.base_url)
            is_local = (parsed_url.hostname in ["localhost", "127.0.0.1"] or 
                       "api.openai.com" not in self.base_url)
            if is_local:
                self.api_key = LOCAL_SERVER_API_KEY_PLACEHOLDER
        
        if not self.api_key:
            raise ValueError(
                f"{self.api_key_var} environment variable is required for the default OpenAI service. "
                f"For local servers, set {self.api_key_var}='{LOCAL_SERVER_API_KEY_PLACEHOLDER}' and OPENAI_API_BASE to your local endpoint."
            )


    def get_model(self):
        """
        Returns an instance of the native SDK client with the configured parameters.
        
        PERFORMANCE: Uses direct SDK clients instead of LangChain wrappers.
        This saves ~2600ms on import (OpenAI SDK ~600ms vs langchain_openai ~3200ms).

        Returns:
            Client: An instance of the native SDK client (OpenAI, Anthropic, etc.)
        """
        if self.model.startswith("google/"):
            if GOOGLE_GENAI_AVAILABLE:
                genai = _get_google_genai()
                genai.configure(api_key=self.api_key)
                return genai.GenerativeModel(self.model_name)
            else:
                raise ImportError(
                    "Required package 'google-generativeai' not found. "
                    "Please install with 'pip install google-generativeai'"
                )
        elif self.model.startswith("cohere/"):
            if COHERE_AVAILABLE:
                cohere = _get_cohere_client()
                return cohere.Client(api_key=self.api_key)
            else:
                raise ImportError(
                    "Required package 'cohere' not found. "
                    "Please install with 'pip install cohere'"
                )
        elif self.model.startswith("anthropic/"):
            if ANTHROPIC_AVAILABLE:
                Anthropic = _get_anthropic_client()
                return Anthropic(api_key=self.api_key)
            else:
                raise ImportError(
                    "Required package 'anthropic' not found. "
                    "Please install with 'pip install anthropic'"
                )
        elif OPENAI_AVAILABLE:
            OpenAI = _get_openai_client()
            return OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            raise ImportError(
                "Required package 'openai' not found. "
                "Please install with 'pip install openai'"
            )
