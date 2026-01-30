"""
Multi-Agent CLI Feature Handler

Provides CLI commands for defining and running multiple agents:
- praisonai agents run --agent "name:role:tools" --agent "..." --task "..."

Example:
    praisonai agents run \
        --agent "researcher:Research Analyst:internet_search" \
        --agent "writer:Content Writer:write_file" \
        --task "Research AI trends and write a report"
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any


def parse_agent_definition(definition: str) -> Dict[str, Any]:
    """Parse an agent definition string.
    
    Format: name:role:tools:goal (tools and goal are optional)
    
    Args:
        definition: Agent definition string
        
    Returns:
        Dictionary with name, role, tools, and optionally goal
    """
    parts = definition.split(':')
    
    result = {
        'name': parts[0].strip() if len(parts) > 0 else 'agent',
        'role': parts[1].strip() if len(parts) > 1 else 'Assistant',
        'tools': [],
        'goal': None
    }
    
    # Parse tools (comma-separated)
    if len(parts) > 2 and parts[2].strip():
        result['tools'] = [t.strip() for t in parts[2].split(',') if t.strip()]
    
    # Parse goal if provided
    if len(parts) > 3:
        result['goal'] = parts[3].strip()
    
    return result


class MultiAgentHandler:
    """Handler for multi-agent CLI commands."""
    
    def __init__(self, verbose: bool = True):
        """Initialize the multi-agent handler.
        
        Args:
            verbose: Whether to print verbose output
        """
        self.verbose = verbose
    
    def create_agents_from_definitions(
        self,
        definitions: List[str],
        llm: Optional[str] = None,
        instructions: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Create agent configurations from definition strings.
        
        Args:
            definitions: List of agent definition strings
            llm: LLM model to use for all agents
            instructions: Additional instructions for all agents
            
        Returns:
            List of agent configuration dictionaries
        """
        agents = []
        
        for definition in definitions:
            agent_config = parse_agent_definition(definition)
            
            if llm:
                agent_config['llm'] = llm
            
            if instructions:
                agent_config['instructions'] = instructions
            
            agents.append(agent_config)
        
        return agents
    
    def prepare_execution_config(
        self,
        agent_definitions: List[str],
        task: str,
        process: str = "sequential",
        llm: Optional[str] = None,
        instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prepare configuration for agent execution.
        
        Args:
            agent_definitions: List of agent definition strings
            task: Task description
            process: Execution process (sequential, parallel)
            llm: LLM model to use
            instructions: Additional instructions
            
        Returns:
            Execution configuration dictionary
        """
        agents = self.create_agents_from_definitions(
            agent_definitions, llm, instructions
        )
        
        return {
            'agents': agents,
            'task': task,
            'process': process,
            'llm': llm
        }
    
    def _load_tools(self, tool_names: List[str]) -> List:
        """Load tool functions by name.
        
        Args:
            tool_names: List of tool names to load
            
        Returns:
            List of tool functions
        """
        tools = []
        
        try:
            from praisonaiagents.tools import (
                internet_search, read_file, write_file, list_files,
                execute_command, read_csv, write_csv, analyze_csv
            )
            
            tool_map = {
                'internet_search': internet_search,
                'read_file': read_file,
                'write_file': write_file,
                'list_files': list_files,
                'execute_command': execute_command,
                'read_csv': read_csv,
                'write_csv': write_csv,
                'analyze_csv': analyze_csv,
            }
            
            for name in tool_names:
                if name in tool_map:
                    tools.append(tool_map[name])
                else:
                    if self.verbose:
                        print(f"⚠ Tool '{name}' not found, skipping")
        except ImportError as e:
            if self.verbose:
                print(f"⚠ Could not load tools: {e}")
        
        return tools
    
    def _execute_agents(
        self,
        agents_config: List[Dict[str, Any]],
        task: str,
        process: str = "sequential",
        llm: Optional[str] = None
    ) -> str:
        """Execute agents with the given configuration.
        
        Args:
            agents_config: List of agent configurations
            task: Task to execute
            process: Execution process
            llm: LLM model to use
            
        Returns:
            Execution result
        """
        try:
            from praisonaiagents import Agent, Task, Agents
            
            # Create Agent objects
            agents = []
            tasks = []
            
            for i, config in enumerate(agents_config):
                # Load tools for this agent
                tools = self._load_tools(config.get('tools', []))
                
                agent = Agent(
                    name=config['name'],
                    role=config['role'],
                    goal=config.get('goal') or f"Complete tasks as {config['role']}",
                    backstory=f"You are a skilled {config['role']}.",
                    instructions=config.get('instructions', ''),
                    tools=tools if tools else None,
                    llm=config.get('llm') or llm or os.environ.get('OPENAI_MODEL_NAME', 'gpt-4o-mini'),
                    verbose=self.verbose
                )
                agents.append(agent)
                
                # Create task for this agent
                agent_task = Task(
                    name=f"task_{config['name']}",
                    description=task if i == 0 else f"Continue the work: {task}",
                    expected_output="Completed task output",
                    agent=agent
                )
                tasks.append(agent_task)
            
            # Run agents
            if self.verbose:
                print(f"\n🚀 Running {len(agents)} agents ({process} mode)...")
                for agent in agents:
                    print(f"  - {agent.name}: {agent.role}")
                print()
            
            praison_agents = AgentManager(
                agents=agents,
                tasks=tasks,
                process=process,
                verbose=self.verbose
            )
            
            result = praison_agents.start()
            return result
            
        except Exception as e:
            if self.verbose:
                print(f"❌ Execution failed: {e}")
            raise
    
    def run(
        self,
        agent_definitions: List[str],
        task: str,
        process: str = "sequential",
        llm: Optional[str] = None,
        instructions: Optional[str] = None
    ) -> str:
        """Run multiple agents with the given task.
        
        Args:
            agent_definitions: List of agent definition strings
            task: Task to execute
            process: Execution process (sequential, parallel)
            llm: LLM model to use
            instructions: Additional instructions
            
        Returns:
            Execution result
        """
        config = self.prepare_execution_config(
            agent_definitions, task, process, llm, instructions
        )
        
        return self._execute_agents(
            config['agents'],
            config['task'],
            config['process'],
            config['llm']
        )


def handle_agents_command(args) -> int:
    """Handle agents subcommand from CLI.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    handler = MultiAgentHandler(verbose=True)
    
    try:
        if args.agents_command == "run":
            if not hasattr(args, 'agent') or not args.agent:
                print("Error: At least one --agent is required")
                return 1
            
            if not hasattr(args, 'task') or not args.task:
                print("Error: --task is required")
                return 1
            
            result = handler.run(
                agent_definitions=args.agent,
                task=args.task,
                process=getattr(args, 'process', 'sequential'),
                llm=getattr(args, 'llm', None),
                instructions=getattr(args, 'instructions', None)
            )
            
            print("\n" + "="*50)
            print("RESULT:")
            print("="*50)
            print(result)
            
        elif args.agents_command == "list":
            # List available tools
            print("\nAvailable tools for agents:")
            print("-" * 30)
            tools = [
                ("internet_search", "Search the web"),
                ("read_file", "Read file contents"),
                ("write_file", "Write to a file"),
                ("list_files", "List directory contents"),
                ("execute_command", "Execute shell commands"),
                ("read_csv", "Read CSV files"),
                ("write_csv", "Write CSV files"),
                ("analyze_csv", "Analyze CSV data"),
            ]
            for name, desc in tools:
                print(f"  {name}: {desc}")
            
        else:
            print(f"Unknown agents command: {args.agents_command}")
            return 1
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


def add_agents_parser(subparsers) -> None:
    """Add agents subcommand to argument parser.
    
    Args:
        subparsers: Subparsers object from argparse
    """
    # run command
    run_parser = subparsers.add_parser(
        'run',
        help='Run multiple agents with a task'
    )
    run_parser.add_argument(
        '--agent', '-a',
        action='append',
        required=True,
        help='Agent definition (format: name:role:tools). Can be used multiple times.'
    )
    run_parser.add_argument(
        '--task', '-t',
        required=True,
        help='Task for the agents to complete'
    )
    run_parser.add_argument(
        '--process', '-p',
        choices=['sequential', 'parallel'],
        default='sequential',
        help='Execution process (default: sequential)'
    )
    run_parser.add_argument(
        '--llm', '-m',
        help='LLM model to use for all agents'
    )
    run_parser.add_argument(
        '--instructions', '-i',
        help='Additional instructions for all agents'
    )
    run_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    # list command - list available tools
    list_parser = subparsers.add_parser(
        'list',
        help='List available tools for agents'
    )
