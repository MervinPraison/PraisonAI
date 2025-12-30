"""
Custom Provider Registry Example (Python)

This example demonstrates how to register and use custom LLM providers
with the PraisonAI Python wrapper.

Note: The Python provider registry is for custom provider extensions.
Built-in providers (OpenAI, Anthropic, Google) are handled by LiteLLM
in praisonaiagents automatically.
"""

import sys
sys.path.insert(0, '../../src/praisonai')

from praisonai.llm import (
    LLMProviderRegistry,
    register_llm_provider,
    unregister_llm_provider,
    has_llm_provider,
    list_llm_providers,
    create_llm_provider,
    get_default_llm_registry,
    parse_model_string
)


# Example 1: Simple Custom Provider
# ---------------------------------

class SimpleCustomProvider:
    """A minimal custom provider example."""
    
    provider_id = "simple-custom"
    
    def __init__(self, model_id: str, config: dict = None):
        self.model_id = model_id
        self.config = config or {}
        self.api_endpoint = self.config.get('api_endpoint', 'https://api.example.com')
    
    def generate(self, prompt: str) -> str:
        """Generate a response (simulated)."""
        print(f"[SimpleCustomProvider] Generating with model: {self.model_id}")
        print(f"[SimpleCustomProvider] Prompt: {prompt[:50]}...")
        return f"Response from {self.provider_id}/{self.model_id}: Hello! This is a simulated response."


# Example 2: Ollama Provider
# --------------------------

class OllamaProvider:
    """Custom provider for local Ollama integration."""
    
    provider_id = "ollama"
    
    def __init__(self, model_id: str, config: dict = None):
        self.model_id = model_id
        self.config = config or {}
        self.base_url = self.config.get('base_url', 'http://localhost:11434')
    
    def generate(self, prompt: str) -> str:
        """Generate a response using Ollama API."""
        import requests
        
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_id,
                "prompt": prompt,
                "stream": False
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama API error: {response.text}")
        
        return response.json().get("response", "")
    
    def generate_stream(self, prompt: str):
        """Generate a streaming response using Ollama API."""
        import requests
        
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_id,
                "prompt": prompt,
                "stream": True
            },
            stream=True
        )
        
        for line in response.iter_lines():
            if line:
                import json
                data = json.loads(line)
                yield data.get("response", "")
                if data.get("done"):
                    break


# Example 3: Cloudflare Workers AI Provider
# -----------------------------------------

class CloudflareProvider:
    """Custom provider for Cloudflare Workers AI."""
    
    provider_id = "cloudflare"
    
    def __init__(self, model_id: str, config: dict = None):
        self.model_id = model_id
        self.config = config or {}
        self.account_id = self.config.get('account_id')
        self.api_token = self.config.get('api_token')
    
    def generate(self, prompt: str) -> str:
        """Generate a response using Cloudflare Workers AI."""
        import requests
        
        if not self.account_id or not self.api_token:
            raise ValueError("Cloudflare account_id and api_token are required")
        
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model_id}",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            },
            json={"prompt": prompt}
        )
        
        if response.status_code != 200:
            raise Exception(f"Cloudflare API error: {response.text}")
        
        return response.json().get("result", {}).get("response", "")


def main():
    print("=== Provider Registry Example (Python) ===\n")
    
    # Check initial state
    print("Initial providers:", list_llm_providers())
    print()
    
    # Register custom providers
    print("Registering custom providers...")
    register_llm_provider("simple-custom", SimpleCustomProvider)
    register_llm_provider("ollama", OllamaProvider, aliases=["local"])
    register_llm_provider("cloudflare", CloudflareProvider, aliases=["cf", "workers-ai"])
    print()
    
    # Check providers after registration
    print("Providers after registration:", list_llm_providers())
    print("Has ollama:", has_llm_provider("ollama"))
    print("Has local (alias):", has_llm_provider("local"))
    print("Has cloudflare:", has_llm_provider("cloudflare"))
    print("Has cf (alias):", has_llm_provider("cf"))
    print()
    
    # Parse model strings
    print("=== Model String Parsing ===\n")
    
    test_strings = [
        "openai/gpt-4o-mini",
        "gpt-4o-mini",
        "claude-3-5-sonnet-latest",
        "gemini-2.0-flash",
        "ollama/llama2",
        "cloudflare/workers-ai-model"
    ]
    
    for model_str in test_strings:
        parsed = parse_model_string(model_str)
        print(f"  '{model_str}' -> provider={parsed['provider_id']}, model={parsed['model_id']}")
    print()
    
    # Create and use providers
    print("=== Using Custom Providers ===\n")
    
    # Use simple custom provider
    provider = create_llm_provider("simple-custom/test-model")
    print(f"Created provider: {provider.provider_id}/{provider.model_id}")
    response = provider.generate("Hello, world!")
    print(f"Response: {response}")
    print()
    
    # Use ollama provider via alias
    provider = create_llm_provider("local/llama2", config={"base_url": "http://localhost:11434"})
    print(f"Created provider: {provider.provider_id}/{provider.model_id}")
    print()
    
    # Demonstrate error handling
    print("=== Error Handling ===\n")
    try:
        create_llm_provider("unknown-provider/model")
    except ValueError as e:
        print(f"Expected error: {e}")
    print()
    
    # Demonstrate isolated registries
    print("=== Isolated Registries ===\n")
    
    # Create isolated registry
    isolated_registry = LLMProviderRegistry()
    isolated_registry.register("isolated-provider", SimpleCustomProvider)
    
    print(f"Default registry providers: {list_llm_providers()}")
    print(f"Isolated registry providers: {isolated_registry.list()}")
    
    # Use isolated registry
    provider = create_llm_provider("isolated-provider/model", registry=isolated_registry)
    print(f"Created from isolated registry: {provider.provider_id}/{provider.model_id}")
    print()
    
    # Cleanup
    print("=== Cleanup ===\n")
    unregister_llm_provider("simple-custom")
    unregister_llm_provider("ollama")
    unregister_llm_provider("cloudflare")
    print(f"Providers after cleanup: {list_llm_providers()}")
    
    print("\n=== Example Complete ===")


if __name__ == "__main__":
    main()
