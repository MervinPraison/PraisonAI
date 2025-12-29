"""
Lite Agent Handler for CLI.

Provides access to the lightweight praisonaiagents.lite subpackage.
Usage: praisonai lite [run|info]
"""

import os
from typing import Any, Dict, Tuple
from .base import FlagHandler


class LiteHandler(FlagHandler):
    """
    Handler for lite agent commands.
    
    The lite subpackage provides a minimal agent framework without heavy
    dependencies like litellm. Users can bring their own LLM client.
    
    Commands:
        praisonai lite run "prompt"     - Run a lite agent with custom LLM
        praisonai lite info             - Show lite package info
        praisonai lite example          - Show example usage
    """
    
    @property
    def feature_name(self) -> str:
        return "lite"
    
    @property
    def flag_name(self) -> str:
        return "lite"
    
    @property
    def flag_help(self) -> str:
        return "Use lightweight agent without heavy dependencies"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if lite package is available."""
        import importlib.util
        if importlib.util.find_spec("praisonaiagents.lite") is not None:
            return True, ""
        return False, "Lite package requires praisonaiagents>=0.5.0"
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get information about the lite package.
        
        Returns:
            Dict with package info
        """
        import importlib.util
        if importlib.util.find_spec("praisonaiagents.lite") is None:
            return {
                "available": False,
                "error": "praisonaiagents.lite not found"
            }
        
        return {
            "available": True,
            "classes": ["LiteAgent", "LiteTask", "LiteToolResult"],
            "decorators": ["@tool"],
            "helpers": ["create_openai_llm_fn", "create_anthropic_llm_fn"],
            "features": [
                "BYO-LLM (Bring Your Own LLM)",
                "Thread-safe chat history",
                "Tool execution",
                "No litellm dependency",
                "Minimal memory footprint"
            ]
        }
    
    def show_example(self) -> str:
        """
        Show example usage of lite package.
        
        Returns:
            Example code string
        """
        example = '''
# Example: Using praisonaiagents.lite with custom LLM

from praisonaiagents.lite import LiteAgent, tool

# Define a custom LLM function
def my_llm(messages):
    """Your custom LLM implementation."""
    # Example: Call OpenAI directly
    import openai
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    return response.choices[0].message.content

# Or use the built-in OpenAI adapter
from praisonaiagents.lite import create_openai_llm_fn
llm_fn = create_openai_llm_fn(model="gpt-4o-mini")

# Create a lite agent
agent = LiteAgent(
    name="MyAgent",
    llm_fn=llm_fn,
    instructions="You are a helpful assistant."
)

# Chat with the agent
response = agent.chat("Hello!")
print(response)

# Define and use tools
@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

agent_with_tools = LiteAgent(
    name="MathAgent",
    llm_fn=llm_fn,
    tools=[add_numbers]
)

# Execute tool directly
result = agent_with_tools.execute_tool("add_numbers", a=5, b=3)
print(f"Result: {result.output}")  # Output: 8
'''
        return example
    
    def run_lite_agent(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        provider: str = "openai"
    ) -> str:
        """
        Run a lite agent with the given prompt.
        
        Args:
            prompt: The prompt to send to the agent
            model: Model name to use
            provider: LLM provider (openai, anthropic)
            
        Returns:
            Agent response
        """
        try:
            from praisonaiagents.lite import LiteAgent, create_openai_llm_fn, create_anthropic_llm_fn
            
            # Create LLM function based on provider
            if provider == "openai":
                if not os.environ.get("OPENAI_API_KEY"):
                    return "Error: OPENAI_API_KEY not set"
                llm_fn = create_openai_llm_fn(model=model)
            elif provider == "anthropic":
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    return "Error: ANTHROPIC_API_KEY not set"
                llm_fn = create_anthropic_llm_fn(model=model)
            else:
                return f"Error: Unknown provider '{provider}'. Use 'openai' or 'anthropic'."
            
            # Create and run agent
            agent = LiteAgent(
                name="LiteCLIAgent",
                llm_fn=llm_fn,
                instructions="You are a helpful assistant. Keep responses concise."
            )
            
            return agent.chat(prompt)
            
        except ImportError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
    
    def handle(self, subcommand: str = "info", **kwargs) -> Any:
        """
        Handle lite subcommands.
        
        Args:
            subcommand: One of run, info, example
            **kwargs: Additional options (prompt, model, provider)
            
        Returns:
            Results
        """
        if subcommand == "info":
            info = self.get_info()
            if info.get("available"):
                print("praisonaiagents.lite - Lightweight Agent Package")
                print("=" * 50)
                print("\nClasses:", ", ".join(info["classes"]))
                print("Decorators:", ", ".join(info["decorators"]))
                print("Helpers:", ", ".join(info["helpers"]))
                print("\nFeatures:")
                for feature in info["features"]:
                    print(f"  • {feature}")
            else:
                print(f"Lite package not available: {info.get('error')}")
            return info
            
        elif subcommand == "example":
            example = self.show_example()
            print(example)
            return example
            
        elif subcommand == "run":
            prompt = kwargs.get("prompt", "Hello!")
            model = kwargs.get("model", "gpt-4o-mini")
            provider = kwargs.get("provider", "openai")
            
            response = self.run_lite_agent(prompt, model, provider)
            print(response)
            return response
            
        else:
            print(f"Unknown subcommand: {subcommand}")
            print("Available: info, example, run")
            return None


def run_lite_command(args) -> int:
    """
    Run lite command from CLI args.
    
    Args:
        args: Parsed CLI arguments
        
    Returns:
        Exit code (0 for success)
    """
    handler = LiteHandler()
    subcommand = getattr(args, 'lite_command', 'info')
    
    kwargs = {}
    if hasattr(args, 'prompt'):
        kwargs['prompt'] = args.prompt
    if hasattr(args, 'model'):
        kwargs['model'] = args.model
    if hasattr(args, 'provider'):
        kwargs['provider'] = args.provider
    
    result = handler.handle(subcommand, **kwargs)
    return 0 if result else 1
