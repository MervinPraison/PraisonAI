"""
Single Agent CLI Feature Handler

Provides CLI commands for running a single agent:
- praisonai agent run --name "assistant" --task "Hello world" --tool-search auto

Example:
    praisonai agent run \
        --name "assistant" \
        --instructions "You are a helpful assistant" \
        --task "Help me with something" \
        --tool-search auto
"""

import os
from typing import Optional, List, Dict, Any, Union


def parse_tool_search_param(value: str) -> Union[bool, str, Dict[str, Any]]:
    """Parse tool_search parameter from CLI.
    
    Args:
        value: String value from CLI parameter
        
    Returns:
        Parsed value for tool_search parameter
    """
    if value.lower() in ('false', 'off', 'disabled'):
        return False
    elif value.lower() in ('true', 'on', 'enabled'):
        return True
    elif value.lower() in ('auto',):
        return "auto"
    else:
        # Try to parse as JSON for advanced config
        try:
            import json
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            # Treat as mode string
            return value


class SingleAgentHandler:
    """Handler for single agent CLI commands."""
    
    def __init__(self, verbose: bool = True):
        """Initialize the single agent handler.
        
        Args:
            verbose: Whether to print verbose output
        """
        self.verbose = verbose
    
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
    
    def run(
        self,
        name: str = "assistant",
        instructions: Optional[str] = None,
        task: str = "Hello",
        llm: Optional[str] = None,
        tools: Optional[List[str]] = None,
        tool_search: Optional[str] = None,
        memory: bool = False,
        verbose: bool = False
    ) -> str:
        """Run a single agent with the given parameters.
        
        Args:
            name: Agent name
            instructions: Agent instructions
            task: Task to execute
            llm: LLM model to use
            tools: List of tool names
            tool_search: Tool search configuration
            memory: Whether to enable memory
            verbose: Whether to enable verbose output
            
        Returns:
            Agent execution result
        """
        try:
            from praisonaiagents import Agent
            
            # Parse tool_search parameter
            tool_search_config = None
            if tool_search:
                tool_search_config = parse_tool_search_param(tool_search)
            
            # Load tools if specified
            agent_tools = None
            if tools:
                agent_tools = self._load_tools(tools)
            
            # Create and run agent
            agent = Agent(
                name=name,
                instructions=instructions or f"You are a helpful agent named {name}.",
                llm=llm or os.environ.get('OPENAI_MODEL_NAME', 'gpt-4o-mini'),
                tools=agent_tools,
                tool_search=tool_search_config,
                memory=memory,
                verbose=verbose
            )
            
            if self.verbose:
                print(f"\n🚀 Running agent '{name}'...")
                print(f"Task: {task}")
                if tool_search_config:
                    print(f"Tool Search: {tool_search_config}")
                print()
            
            result = agent.start(task)
            return str(result)
            
        except Exception as e:
            if self.verbose:
                print(f"❌ Execution failed: {e}")
            raise


def handle_agent_command(args) -> int:
    """Handle agent subcommand from CLI.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    handler = SingleAgentHandler(verbose=True)
    
    try:
        if args.agent_command == "run":
            result = handler.run(
                name=getattr(args, 'name', 'assistant'),
                instructions=getattr(args, 'instructions', None),
                task=getattr(args, 'task', 'Hello'),
                llm=getattr(args, 'llm', None),
                tools=getattr(args, 'tools', None),
                tool_search=getattr(args, 'tool_search', None),
                memory=getattr(args, 'memory', False),
                verbose=getattr(args, 'verbose', False)
            )
            
            print("\n" + "="*50)
            print("RESULT:")
            print("="*50)
            print(result)
            
        else:
            print(f"Unknown agent command: {args.agent_command}")
            return 1
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


def add_agent_parser(subparsers) -> None:
    """Add agent subcommand to argument parser.
    
    Args:
        subparsers: Subparsers object from argparse
    """
    # run command
    run_parser = subparsers.add_parser(
        'run',
        help='Run a single agent with specified parameters'
    )
    run_parser.add_argument(
        '--name', '-n',
        default='assistant',
        help='Agent name (default: assistant)'
    )
    run_parser.add_argument(
        '--instructions', '-i',
        help='Agent instructions'
    )
    run_parser.add_argument(
        '--task', '-t',
        default='Hello',
        help='Task for the agent to complete (default: Hello)'
    )
    run_parser.add_argument(
        '--llm', '-m',
        help='LLM model to use'
    )
    run_parser.add_argument(
        '--tools',
        action='append',
        help='Tool names to load (can be used multiple times)'
    )
    run_parser.add_argument(
        '--tool-search',
        help='Tool search configuration (false/true/auto or JSON config)'
    )
    run_parser.add_argument(
        '--memory',
        action='store_true',
        help='Enable agent memory'
    )
    run_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )