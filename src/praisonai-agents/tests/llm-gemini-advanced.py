from praisonaiagents import Agent

# Detailed LLM configuration
llm_config = {
    "model": "gemini/gemini-1.5-flash-latest",  # Model name without provider prefix
    
    # Core settings
    "temperature": 0.7,                # Controls randomness (like temperature)
    "timeout": 30,                 # Timeout in seconds
    "top_p": 0.9,                    # Nucleus sampling parameter
    "max_tokens": 1000,               # Max tokens in response
    
    # Advanced parameters
    "presence_penalty": 0.1,         # Penalize repetition of topics (-2.0 to 2.0)
    "frequency_penalty": 0.1,        # Penalize token repetition (-2.0 to 2.0)
    
    # API settings (optional)
    "api_key": None,                 # Your API key (or use environment variable)
    "base_url": None,                # Custom API endpoint if needed
    
    # Response formatting
    "response_format": {             # Force specific response format
        "type": "text"               # Options: "text", "json_object"
    },
    
    # Additional controls
    "seed": 42,                      # For reproducible responses
    "stop_phrases": ["##", "END"],   # Custom stop sequences
}

agent = Agent(
    instructions="You are a helpful Assistant specialized in scientific explanations. "
                "Provide clear, accurate, and engaging responses.",
    llm=llm_config,                  # Pass the detailed configuration
    verbose=True,                    # Enable detailed output
    markdown=True,                   # Format responses in markdown
    self_reflect=True,              # Enable self-reflection
    max_reflect=3,                  # Maximum reflection iterations
    min_reflect=1                   # Minimum reflection iterations
)

# Test the agent
response = agent.start("Why is the sky blue? Please explain in simple terms.")

print(response)