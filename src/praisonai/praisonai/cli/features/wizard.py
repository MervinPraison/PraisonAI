"""
Onboarding Wizard for PraisonAI.

Provides an interactive setup wizard for new users.
"""

from __future__ import annotations

import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class OnboardingWizard:
    """Interactive onboarding wizard for PraisonAI setup."""
    
    def __init__(self):
        self.config: Dict[str, Any] = {}
    
    def run(self, output_dir: str = ".") -> bool:
        """Run the onboarding wizard.
        
        Args:
            output_dir: Directory to create configuration files
            
        Returns:
            True if setup completed successfully
        """
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.prompt import Prompt, Confirm
        except ImportError:
            print("Error: Rich library required for wizard")
            return False
        
        console = Console()
        
        console.print(Panel.fit(
            "[bold blue]Welcome to PraisonAI![/bold blue]\n\n"
            "This wizard will help you set up your first agent project.",
            title="Onboarding Wizard",
        ))
        console.print()
        
        project_name = Prompt.ask(
            "Project name",
            default="my-agent-project",
        )
        self.config["project_name"] = project_name
        
        console.print("\n[bold]Select your LLM provider:[/bold]")
        console.print("  1. OpenAI (GPT-4, GPT-3.5)")
        console.print("  2. Anthropic (Claude)")
        console.print("  3. Google (Gemini)")
        console.print("  4. Ollama (Local)")
        console.print("  5. Other (LiteLLM)")
        
        provider_choice = Prompt.ask(
            "Provider",
            choices=["1", "2", "3", "4", "5"],
            default="1",
        )
        
        provider_map = {
            "1": "openai",
            "2": "anthropic",
            "3": "google",
            "4": "ollama",
            "5": "litellm",
        }
        self.config["provider"] = provider_map[provider_choice]
        
        if self.config["provider"] != "ollama":
            api_key = Prompt.ask(
                f"API Key for {self.config['provider']}",
                password=True,
            )
            self.config["api_key"] = api_key
        
        model_defaults = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-sonnet-20240229",
            "google": "gemini-1.5-flash",
            "ollama": "llama3.2",
            "litellm": "gpt-4o-mini",
        }
        
        model = Prompt.ask(
            "Model",
            default=model_defaults.get(self.config["provider"], "gpt-4o-mini"),
        )
        self.config["model"] = model
        
        console.print("\n[bold]Agent Configuration:[/bold]")
        
        agent_name = Prompt.ask(
            "Agent name",
            default="assistant",
        )
        self.config["agent_name"] = agent_name
        
        agent_role = Prompt.ask(
            "Agent role/description",
            default="A helpful AI assistant",
        )
        self.config["agent_role"] = agent_role
        
        use_tools = Confirm.ask(
            "Enable tools (web search, file operations)?",
            default=True,
        )
        self.config["use_tools"] = use_tools
        
        use_memory = Confirm.ask(
            "Enable memory (conversation history)?",
            default=True,
        )
        self.config["use_memory"] = use_memory
        
        console.print("\n[bold]Creating project files...[/bold]")
        
        project_dir = os.path.join(output_dir, project_name)
        os.makedirs(project_dir, exist_ok=True)
        
        self._create_env_file(project_dir)
        self._create_agent_yaml(project_dir)
        self._create_main_py(project_dir)
        self._create_readme(project_dir)
        
        console.print(f"\n[green]✓[/green] Project created at: {project_dir}")
        console.print("\n[bold]Next steps:[/bold]")
        console.print(f"  1. cd {project_name}")
        console.print("  2. pip install praisonaiagents")
        console.print("  3. python main.py")
        
        return True
    
    def _create_env_file(self, project_dir: str) -> None:
        """Create .env file."""
        env_content = []
        
        if self.config.get("api_key"):
            provider = self.config["provider"]
            key_names = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "google": "GOOGLE_API_KEY",
                "litellm": "OPENAI_API_KEY",
            }
            key_name = key_names.get(provider, "API_KEY")
            env_content.append(f"{key_name}={self.config['api_key']}")
        
        env_path = os.path.join(project_dir, ".env")
        with open(env_path, "w") as f:
            f.write("\n".join(env_content))
        
        gitignore_path = os.path.join(project_dir, ".gitignore")
        with open(gitignore_path, "w") as f:
            f.write(".env\n__pycache__/\n*.pyc\n")
    
    def _create_agent_yaml(self, project_dir: str) -> None:
        """Create agents.yaml file."""
        tools = []
        if self.config.get("use_tools"):
            tools = ["search_web"]
        
        yaml_content = f"""# PraisonAI Agent Configuration
# Generated by praisonai init

framework: praisonai
topic: {self.config['agent_role']}

agents:
  - name: {self.config['agent_name']}
    role: {self.config['agent_role']}
    goal: Help users with their tasks
    backstory: You are a helpful AI assistant.
    llm: {self.config['model']}
    tools: {tools}
    memory: {str(self.config.get('use_memory', True)).lower()}

steps:
  - name: main
    agent: {self.config['agent_name']}
    action: Respond to user input
    expected_output: A helpful response
"""
        
        yaml_path = os.path.join(project_dir, "agents.yaml")
        with open(yaml_path, "w") as f:
            f.write(yaml_content)
    
    def _create_main_py(self, project_dir: str) -> None:
        """Create main.py file."""
        main_content = f'''"""
{self.config['project_name']} - PraisonAI Agent

Generated by praisonai init
"""

from praisonaiagents import Agent

def main():
    agent = Agent(
        name="{self.config['agent_name']}",
        instructions="{self.config['agent_role']}",
        llm="{self.config['model']}",
        memory={self.config.get('use_memory', True)},
    )
    
    print("Agent ready! Type 'quit' to exit.")
    print()
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            break
        
        response = agent.chat(user_input)
        print(f"Agent: {{response}}")
        print()

if __name__ == "__main__":
    main()
'''
        
        main_path = os.path.join(project_dir, "main.py")
        with open(main_path, "w") as f:
            f.write(main_content)
    
    def _create_readme(self, project_dir: str) -> None:
        """Create README.md file."""
        readme_content = f"""# {self.config['project_name']}

A PraisonAI agent project.

## Setup

1. Install dependencies:
   ```bash
   pip install praisonaiagents
   ```

2. Set up your API key in `.env`

3. Run the agent:
   ```bash
   python main.py
   ```

## Configuration

Edit `agents.yaml` to customize your agent's behavior.

## Documentation

- [PraisonAI Documentation](https://docs.praison.ai)
- [Agent Configuration](https://docs.praison.ai/agents)
- [Tools Reference](https://docs.praison.ai/tools)
"""
        
        readme_path = os.path.join(project_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write(readme_content)


def handle_init_command(args) -> None:
    """Handle init CLI command."""
    wizard = OnboardingWizard()
    
    output_dir = getattr(args, "output", ".")
    wizard.run(output_dir=output_dir)


def add_init_parser(subparsers) -> None:
    """Add init subparser to CLI."""
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new PraisonAI project",
    )
    init_parser.add_argument(
        "--output", "-o",
        default=".",
        help="Output directory (default: current directory)",
    )
    init_parser.set_defaults(func=handle_init_command)
