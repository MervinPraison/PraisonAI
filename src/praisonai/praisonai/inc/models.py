# praisonai/inc/models.py
import os
import logging
from urllib.parse import urlparse
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO').upper(), format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
LOCAL_SERVER_API_KEY_PLACEHOLDER = "not-needed"

# Conditionally import modules based on availability
try:
    from langchain_openai import ChatOpenAI  # pip install langchain-openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from langchain_google_genai import ChatGoogleGenerativeAI  # pip install langchain-google-genai
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False

try:
    from langchain_anthropic import ChatAnthropic  # pip install langchain-anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from langchain_cohere import ChatCohere  # pip install langchain-cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False

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
        self.model =  model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
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
        Returns an instance of the langchain Chat client with the configured parameters.

        Returns:
            Chat: An instance of the langchain Chat client.
        """
        if self.model.startswith("google/"):
            if GOOGLE_GENAI_AVAILABLE:
                return ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=self.api_key
                )
            else:
                raise ImportError(
                    "Required Langchain Integration 'langchain-google-genai' not found. "
                    "Please install with 'pip install langchain-google-genai'"
                )
        elif self.model.startswith("cohere/"):
            if COHERE_AVAILABLE:
                return ChatCohere(
                    model=self.model_name,
                    cohere_api_key=self.api_key,
                )
            else:
                raise ImportError(
                    "Required Langchain Integration 'langchain-cohere' not found. "
                    "Please install with 'pip install langchain-cohere'"
                )
        elif self.model.startswith("anthropic/"):
            if ANTHROPIC_AVAILABLE:
                return ChatAnthropic(
                    model=self.model_name,
                    anthropic_api_key=self.api_key,
                )
            else:
                raise ImportError(
                    "Required Langchain Integration 'langchain-anthropic' not found. "
                    "Please install with 'pip install langchain-anthropic'"
                )
        elif OPENAI_AVAILABLE:
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
            )
        else:
            raise ImportError(
                "Required Langchain Integration 'langchain-openai' not found. "
                "Please install with 'pip install langchain-openai'"
            )
