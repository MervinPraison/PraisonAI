"""
YAML loader for agent scheduler configuration.

Loads agent and schedule configuration from agents.yaml files.
"""

import yaml
import logging
from typing import Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


def load_agent_yaml_with_schedule(yaml_path: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Load agents.yaml file and extract agent and schedule configuration.
    
    Args:
        yaml_path: Path to agents.yaml file
        
    Returns:
        Tuple of (agent_config, schedule_config)
        
    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ValueError: If YAML is invalid or missing required fields
        
    Example YAML structure:
        framework: praisonai
        
        agents:
          - name: "AI News Monitor"
            role: "News Analyst"
            goal: "Monitor AI news"
            instructions: "Search and summarize"
            tools:
              - search_tool
            verbose: true
        
        task: "Search for latest AI news"
        
        schedule:
          interval: "hourly"
          max_retries: 3
          run_immediately: true
    """
    yaml_path = Path(yaml_path)
    
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")
    
    try:
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML file: {e}")
    
    if not config:
        raise ValueError("Empty YAML file")
    
    # Extract agent configuration
    agent_config = {}
    
    # Get agents list (can be single agent or multiple)
    agents = config.get('agents', [])
    if not agents:
        raise ValueError("No agents defined in YAML file")
    
    # Use first agent for scheduling (can be extended for multi-agent later)
    if isinstance(agents, list):
        agent_config = agents[0]
    else:
        agent_config = agents
    
    # Get task
    task = config.get('task', '')
    if not task:
        # Try to get from agent's tasks
        if 'tasks' in agent_config and agent_config['tasks']:
            first_task = list(agent_config['tasks'].values())[0]
            task = first_task.get('description', '')
    
    agent_config['task'] = task
    
    # Get framework (default to praisonai)
    agent_config['framework'] = config.get('framework', 'praisonai')
    
    # Extract schedule configuration (optional)
    schedule_section = config.get('schedule', {})
    
    # Set defaults for schedule if not provided
    schedule_config = {
        'interval': schedule_section.get('interval', 'hourly'),
        'max_retries': schedule_section.get('max_retries', 3),
        'run_immediately': schedule_section.get('run_immediately', False),
        'timeout': schedule_section.get('timeout'),  # Optional timeout in seconds
        'max_cost': schedule_section.get('max_cost', 1.00)  # Default $1.00 budget limit for safety
    }
    
    logger.info(f"Loaded agent '{agent_config.get('name', 'Unknown')}' with schedule interval '{schedule_config['interval']}'")
    
    return agent_config, schedule_config


def create_agent_from_config(agent_config: Dict[str, Any]) -> Any:
    """
    Create a PraisonAI Agent instance from configuration.
    
    Args:
        agent_config: Agent configuration dictionary
        
    Returns:
        Agent instance
        
    Raises:
        ImportError: If praisonaiagents is not installed
    """
    try:
        from praisonaiagents import Agent
    except ImportError:
        raise ImportError("praisonaiagents package is required. Install with: pip install praisonaiagents")
    
    # Extract agent parameters
    name = agent_config.get('name', 'Scheduled Agent')
    role = agent_config.get('role', '')
    goal = agent_config.get('goal', '')
    instructions = agent_config.get('instructions', agent_config.get('backstory', ''))
    verbose = agent_config.get('verbose', False)
    
    # Handle tools
    tools = []
    tool_names = agent_config.get('tools', [])
    
    if tool_names:
        # Try to import tools
        for tool_name in tool_names:
            try:
                # Try common tool imports
                if tool_name == 'search_tool' or tool_name == 'InternetSearchTool':
                    try:
                        from tools import search_tool
                        tools.append(search_tool)
                    except ImportError:
                        logger.warning(f"Could not import {tool_name}, skipping")
                # Add more tool imports as needed
            except Exception as e:
                logger.warning(f"Error loading tool {tool_name}: {e}")
    
    # Create agent
    agent = Agent(
        name=name,
        role=role,
        goal=goal,
        instructions=instructions,
        tools=tools,
        verbose=verbose
    )
    
    return agent


def validate_schedule_config(schedule_config: Dict[str, Any]) -> None:
    """
    Validate schedule configuration.
    
    Args:
        schedule_config: Schedule configuration dictionary
        
    Raises:
        ValueError: If configuration is invalid
    """
    required_fields = ['interval']
    for field in required_fields:
        if field not in schedule_config:
            raise ValueError(f"Missing required schedule field: {field}")
    
    # Validate interval format
    interval = schedule_config['interval']
    valid_intervals = ['hourly', 'daily']
    
    if interval not in valid_intervals:
        # Check if it's a custom format (*/Nm, */Nh, */Ns, or plain number)
        if not (interval.startswith('*/') or interval.isdigit()):
            raise ValueError(
                f"Invalid interval format: {interval}. "
                f"Use 'hourly', 'daily', '*/30m', '*/6h', or seconds as number"
            )
    
    # Validate max_retries
    max_retries = schedule_config.get('max_retries', 3)
    if not isinstance(max_retries, int) or max_retries < 0:
        raise ValueError(f"max_retries must be a non-negative integer, got: {max_retries}")
