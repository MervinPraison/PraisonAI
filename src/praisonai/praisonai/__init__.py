# Disable OpenTelemetry SDK
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["EC_TELEMETRY"] = "false"
from .cli import PraisonAI
from .version import __version__

def create_agent_file(topic, agent_file="agents.yaml", framework="praisonai"):
    """
    Library-friendly function to create an agent file without CLI parsing.
    
    Args:
        topic (str): The topic for agent generation
        agent_file (str): Path to the agent file to create
        framework (str): Framework to use ('praisonai', 'crewai', 'autogen')
    
    Returns:
        str: Path to the created agent file
    """
    praison_ai = PraisonAI(agent_file=agent_file, framework=framework, init=topic)
    return praison_ai.run_agents()

def run_agents(agent_file="agents.yaml", framework="praisonai", agent_yaml=None, tools=None):
    """
    Library-friendly function to run agents without CLI parsing.
    
    Args:
        agent_file (str): Path to the agent file
        framework (str): Framework to use ('praisonai', 'crewai', 'autogen')
        agent_yaml (str): YAML content as string (alternative to agent_file)
        tools (list): List of tool class names
    
    Returns:
        str: Result of the agent execution
    """
    praison_ai = PraisonAI(
        agent_file=agent_file, 
        framework=framework, 
        agent_yaml=agent_yaml,
        tools=tools
    )
    return praison_ai.run_agents()
