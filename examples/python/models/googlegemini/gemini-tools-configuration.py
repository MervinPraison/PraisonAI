"""
Different ways to configure Gemini internal tools in PraisonAI
"""

from praisonaiagents import Agent
from praisonaiagents.llm import LLM

# Method 1: Simple boolean flags
print("=== Method 1: Simple Boolean Flags ===")
agent1 = Agent(
    instructions="Assistant with search and code capabilities",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True,
        "enable_code_execution": True
    }
)
print("✓ Agent created with boolean flags\n")

# Method 2: Detailed configuration with thresholds
print("=== Method 2: Detailed Configuration ===")
agent2 = Agent(
    instructions="Research assistant with fine-tuned settings",
    llm={
        "model": "gemini/gemini-1.5-pro",
        "google_search_retrieval": {
            "threshold": 0.9  # High confidence threshold
        },
        "dynamic_retrieval_config": {
            "mode": "grounded",
            "dynamic_threshold": 0.7
        }
    }
)
print("✓ Agent created with detailed configuration\n")

# Method 3: Using tool_config parameter
print("=== Method 3: Tool Config Parameter ===")
agent3 = Agent(
    instructions="Advanced assistant with all tools",
    llm={
        "model": "gemini/gemini-1.5-pro-latest",
        "tool_config": {
            "google_search_retrieval": {
                "threshold": 0.8
            },
            "code_execution": {},
            "dynamic_retrieval_config": {
                "mode": "grounded",
                "dynamic_threshold": 0.6
            }
        }
    }
)
print("✓ Agent created with tool_config\n")

# Method 4: Direct LLM instance with internal tools
print("=== Method 4: Direct LLM Instance ===")
llm = LLM(
    model="gemini/gemini-1.5-flash",
    google_search_retrieval=True,
    enable_code_execution=True,
    temperature=0.7,
    max_tokens=2000
)

# Use the LLM instance with an agent
agent4 = Agent(
    instructions="Assistant using pre-configured LLM",
    llm=llm  # Pass the LLM instance directly
)
print("✓ Agent created with pre-configured LLM instance\n")

# Method 5: Combining with custom tools
print("=== Method 5: Internal + Custom Tools ===")

def calculate_compound_interest(principal: float, rate: float, time: int) -> float:
    """Calculate compound interest
    
    Args:
        principal: Initial amount
        rate: Annual interest rate (as decimal)
        time: Time period in years
    """
    return principal * (1 + rate) ** time

agent5 = Agent(
    instructions="Financial assistant with search and custom calculation tools",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True,  # For market research
        "enable_code_execution": True     # For complex calculations
    },
    tools=[calculate_compound_interest]  # Custom tool
)
print("✓ Agent created with both internal and custom tools\n")

# Method 6: Environment-specific configuration
print("=== Method 6: Environment-Specific Config ===")
import os

# You can set defaults via environment
config = {
    "model": os.getenv("GEMINI_MODEL", "gemini/gemini-1.5-flash"),
    "temperature": float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
}

# Add internal tools based on environment
if os.getenv("ENABLE_SEARCH", "true").lower() == "true":
    config["google_search_retrieval"] = True

if os.getenv("ENABLE_CODE_EXEC", "true").lower() == "true":
    config["enable_code_execution"] = True

agent6 = Agent(
    instructions="Environment-configured assistant",
    llm=config
)
print("✓ Agent created with environment-based configuration\n")

# Example usage demonstrating the tools
print("\n=== Example Usage ===")
print("Testing search capability...")
response = agent1.start("What's the current temperature in Tokyo?")
print(f"Search result preview: {response[:100]}...\n")

print("Testing code execution...")
response = agent1.start("Write and run a Python function to check if 2024 is a leap year")
print(f"Code execution result preview: {response[:100]}...\n")

print("Configuration examples complete!")