"""
Example: Using AI LLM Gateways with PraisonAI

This example demonstrates how to use AI gateways like OpenRouter, LiteLLM Proxy,
and custom gateways with PraisonAI agents for unified access to 100+ LLM providers.
"""

import os
from praisonaiagents import Agent

# Example 1: Using OpenRouter Gateway
# OpenRouter provides access to models from multiple providers
def example_openrouter():
    """Example using OpenRouter gateway."""
    
    # Set your OpenRouter API key (or use environment variable OPENROUTER_API_KEY)
    os.environ["OPENROUTER_API_KEY"] = "your-openrouter-api-key"
    
    # Create an agent using OpenRouter gateway
    agent = Agent(
        name="Research Assistant",
        role="AI Researcher",
        goal="Help with research tasks",
        llm="openrouter/anthropic/claude-3.5-sonnet",  # Use any OpenRouter model
        instructions="You are a helpful research assistant."
    )
    
    # The agent will automatically use OpenRouter's endpoint
    response = agent.chat("What are the benefits of AI gateways?")
    print(response)


# Example 2: Using LiteLLM Proxy (Self-hosted or Cloud)
def example_litellm_proxy():
    """Example using LiteLLM Proxy gateway."""
    
    # Configure LiteLLM Proxy endpoint
    # For self-hosted: default is http://localhost:4000
    # For cloud: use your cloud endpoint
    os.environ["LITELLM_PROXY_BASE_URL"] = "http://localhost:4000"
    os.environ["LITELLM_PROXY_API_KEY"] = "your-proxy-key"
    
    # Create an agent using LiteLLM Proxy
    agent = Agent(
        name="Code Assistant",
        role="Python Developer",
        goal="Help with Python programming",
        llm="litellm-proxy/gpt-4",  # Use any model configured in your proxy
        instructions="You are an expert Python developer."
    )
    
    response = agent.chat("Write a function to calculate fibonacci numbers")
    print(response)


# Example 3: Using Custom Gateway
def example_custom_gateway():
    """Example using a custom OpenAI-compatible gateway."""
    from praisonai.llm import create_llm_provider
    
    # Create a custom gateway provider
    custom_provider = create_llm_provider({
        "name": "custom-gateway",
        "model_id": "my-custom-model",
        "config": {
            "base_url": "https://api.mygateway.com/v1",
            "api_key": "your-custom-gateway-key",
            "extra_headers": {
                "X-Custom-Header": "custom-value"
            }
        }
    })
    
    # Use with an agent
    agent = Agent(
        name="Custom Assistant",
        role="General Assistant",
        goal="Help with various tasks",
        llm=custom_provider,  # Pass the provider instance directly
        instructions="You are a helpful assistant."
    )
    
    response = agent.chat("Hello! How can you help me?")
    print(response)


# Example 4: Advanced Configuration with Multiple Agents
def example_multi_agent_gateway():
    """Example using different gateways for different agents."""
    
    # Research agent using OpenRouter for access to Claude
    research_agent = Agent(
        name="Researcher",
        role="Research Specialist",
        llm="openrouter/anthropic/claude-3.5-sonnet",
        instructions="You excel at research and analysis."
    )
    
    # Code agent using LiteLLM Proxy for GPT-4
    code_agent = Agent(
        name="Coder",
        role="Software Engineer",
        llm="litellm-proxy/gpt-4",
        instructions="You are an expert programmer."
    )
    
    # Creative agent using OpenRouter for Llama
    creative_agent = Agent(
        name="Creative",
        role="Creative Writer",
        llm="openrouter/meta-llama/llama-3.1-70b-instruct",
        instructions="You are a creative writer."
    )
    
    # Agents can work together with different LLM backends
    agents = [research_agent, code_agent, creative_agent]
    
    for agent in agents:
        print(f"\n{agent.name} response:")
        response = agent.chat("What's your specialty?")
        print(response)


# Example 5: Gateway with Fallback Configuration
def example_gateway_with_fallback():
    """Example using gateways with fallback options."""
    from praisonai.llm import register_llm_provider
    
    # Custom provider with fallback logic
    class FallbackGatewayProvider:
        def __init__(self, model_id, config=None):
            self.model_id = model_id
            self.config = config or {}
            self.provider_id = "fallback"
            
            # Primary and fallback endpoints
            self.endpoints = [
                {"base_url": "https://primary.api.com/v1", "api_key": "key1"},
                {"base_url": "https://fallback.api.com/v1", "api_key": "key2"},
            ]
        
        def generate(self, prompt, **kwargs):
            import litellm
            
            for endpoint in self.endpoints:
                try:
                    return litellm.completion(
                        model=self.model_id,
                        messages=[{"role": "user", "content": prompt}],
                        base_url=endpoint["base_url"],
                        api_key=endpoint["api_key"],
                        **kwargs
                    )
                except Exception as e:
                    print(f"Failed with {endpoint['base_url']}: {e}")
                    continue
            
            raise Exception("All endpoints failed")
    
    # Register the custom fallback provider
    register_llm_provider("fallback", FallbackGatewayProvider)
    
    # Use with an agent
    agent = Agent(
        name="Reliable Assistant",
        role="Assistant with Fallback",
        llm="fallback/gpt-3.5-turbo",
        instructions="You are a reliable assistant with automatic fallback."
    )
    
    response = agent.chat("Test message")
    print(response)


if __name__ == "__main__":
    print("LLM Gateway Examples for PraisonAI\n")
    print("=" * 50)
    
    # Uncomment to run examples (requires API keys)
    # example_openrouter()
    # example_litellm_proxy()
    # example_custom_gateway()
    # example_multi_agent_gateway()
    # example_gateway_with_fallback()
    
    print("\nTo run these examples:")
    print("1. Set up your API keys for the gateway you want to use")
    print("2. Uncomment the example function calls above")
    print("3. Run: python llm_gateway_example.py")