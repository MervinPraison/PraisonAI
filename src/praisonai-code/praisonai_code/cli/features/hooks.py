"""
Hooks CLI Feature for PraisonAI.

Provides CLI commands for managing and testing hooks.

Commands:
- praisonai hooks list                    # List registered hooks
- praisonai hooks test <event> <target>   # Test hooks for an event
- praisonai hooks validate <config>       # Validate hooks configuration
- praisonai hooks run <command>           # Run a command hook manually
"""

import os
import json
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class HooksConfig:
    """Configuration for hooks loaded from file."""
    hooks: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    
    @classmethod
    def from_file(cls, path: str) -> "HooksConfig":
        """Load hooks configuration from a JSON/YAML file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Hooks config file not found: {path}")
        
        with open(path, 'r') as f:
            if path.endswith('.yaml') or path.endswith('.yml'):
                try:
                    import yaml
                    data = yaml.safe_load(f)
                except ImportError:
                    raise ImportError("PyYAML required for YAML config files")
            else:
                data = json.load(f)
        
        return cls(
            hooks=data.get('hooks', []),
            enabled=data.get('enabled', True)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'hooks': self.hooks,
            'enabled': self.enabled
        }


class HooksHandler:
    """
    Handler for hooks CLI commands.
    
    Provides functionality to:
    - List registered hooks
    - Test hooks with sample events
    - Validate hook configurations
    - Run command hooks manually
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._registry = None
        self._runner = None
    
    @property
    def feature_name(self) -> str:
        return "hooks"
    
    def _get_registry(self):
        """Lazy load the hook registry."""
        if self._registry is None:
            from praisonaiagents.hooks import HookRegistry
            self._registry = HookRegistry()
        return self._registry
    
    def _get_runner(self):
        """Lazy load the hook runner."""
        if self._runner is None:
            from praisonaiagents.hooks import HookRunner
            self._runner = HookRunner(self._get_registry())
        return self._runner
    
    def list_hooks(self, format: str = "table") -> Dict[str, Any]:
        """
        List all registered hooks.
        
        Args:
            format: Output format (table, json)
            
        Returns:
            Dictionary of hooks by event
        """
        registry = self._get_registry()
        hooks = registry.list_hooks()
        
        if format == "json":
            print(json.dumps(hooks, indent=2))
        else:
            self._print_hooks_table(hooks)
        
        return hooks
    
    def _print_hooks_table(self, hooks: Dict[str, List[Dict]]):
        """Print hooks in table format."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            if not hooks:
                console.print("[yellow]No hooks registered[/yellow]")
                return
            
            table = Table(title="Registered Hooks")
            table.add_column("Event", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Type", style="blue")
            table.add_column("Matcher", style="magenta")
            table.add_column("Enabled", style="yellow")
            
            for event, event_hooks in hooks.items():
                for hook in event_hooks:
                    table.add_row(
                        event,
                        hook.get('name', 'unknown'),
                        hook.get('type', 'unknown'),
                        hook.get('matcher') or '*',
                        '✓' if hook.get('enabled', True) else '✗'
                    )
            
            console.print(table)
        except ImportError:
            # Fallback to simple print
            print("Registered Hooks:")
            for event, event_hooks in hooks.items():
                print(f"\n  {event}:")
                for hook in event_hooks:
                    print(f"    - {hook.get('name', 'unknown')} ({hook.get('type', 'unknown')})")
    
    def test_hook(
        self,
        event: str,
        target: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Test hooks for a specific event.
        
        Args:
            event: Event name (before_tool, after_tool, etc.)
            target: Optional target to filter hooks (e.g., tool name)
            input_data: Optional custom input data
            
        Returns:
            List of hook execution results
        """
        from praisonaiagents.hooks import HookEvent
        from praisonaiagents.hooks.events import BeforeToolInput, BeforeAgentInput
        
        # Map string to HookEvent
        event_map = {
            'before_tool': HookEvent.BEFORE_TOOL,
            'after_tool': HookEvent.AFTER_TOOL,
            'before_agent': HookEvent.BEFORE_AGENT,
            'after_agent': HookEvent.AFTER_AGENT,
            'session_start': HookEvent.SESSION_START,
            'session_end': HookEvent.SESSION_END,
        }
        
        hook_event = event_map.get(event.lower())
        if hook_event is None:
            print(f"[red]Unknown event: {event}[/red]")
            print(f"Available events: {', '.join(event_map.keys())}")
            return []
        
        # Create sample input based on event type
        from datetime import datetime
        timestamp = datetime.now().isoformat()
        
        if hook_event in (HookEvent.BEFORE_TOOL, HookEvent.AFTER_TOOL):
            sample_input = BeforeToolInput(
                session_id="cli-test",
                cwd=os.getcwd(),
                event_name=event,
                timestamp=timestamp,
                tool_name=target or "test_tool",
                tool_input=input_data or {"test": "data"}
            )
        else:
            sample_input = BeforeAgentInput(
                session_id="cli-test",
                cwd=os.getcwd(),
                event_name=event,
                timestamp=timestamp,
                prompt=target or "Test prompt"
            )
        
        runner = self._get_runner()
        results = asyncio.run(runner.execute(hook_event, sample_input, target))
        
        # Print results
        self._print_test_results(results)
        
        return [r.to_dict() for r in results]
    
    def _print_test_results(self, results):
        """Print test results."""
        try:
            from rich.console import Console
            from rich.panel import Panel
            
            console = Console()
            
            if not results:
                console.print("[yellow]No hooks executed[/yellow]")
                return
            
            console.print(f"\n[bold]Hook Execution Results ({len(results)} hooks)[/bold]\n")
            
            for result in results:
                status = "[green]✓ PASSED[/green]" if result.success else "[red]✗ FAILED[/red]"
                decision = result.output.decision if result.output else "N/A"
                
                content = f"""
Hook: {result.hook_name}
Status: {status}
Decision: {decision}
Duration: {result.duration_ms:.2f}ms
"""
                if result.error:
                    content += f"Error: {result.error}\n"
                if result.output and result.output.reason:
                    content += f"Reason: {result.output.reason}\n"
                
                panel_style = "green" if result.success else "red"
                console.print(Panel(content.strip(), title=result.hook_name, border_style=panel_style))
        except ImportError:
            print(f"\nHook Execution Results ({len(results)} hooks):")
            for result in results:
                status = "PASSED" if result.success else "FAILED"
                print(f"  - {result.hook_name}: {status}")
    
    def validate_config(self, config_path: str) -> bool:
        """
        Validate a hooks configuration file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            True if valid, False otherwise
        """
        try:
            config = HooksConfig.from_file(config_path)
            
            errors = []
            warnings = []
            
            for i, hook in enumerate(config.hooks):
                # Check required fields
                if 'event' not in hook:
                    errors.append(f"Hook {i}: missing 'event' field")
                
                if 'command' not in hook and 'function' not in hook:
                    errors.append(f"Hook {i}: must have 'command' or 'function'")
                
                # Check event name
                valid_events = ['before_tool', 'after_tool', 'before_agent', 
                               'after_agent', 'session_start', 'session_end']
                if hook.get('event') and hook['event'] not in valid_events:
                    warnings.append(f"Hook {i}: unknown event '{hook['event']}'")
                
                # Check timeout
                if 'timeout' in hook:
                    try:
                        timeout = float(hook['timeout'])
                        if timeout <= 0:
                            warnings.append(f"Hook {i}: timeout should be positive")
                    except (ValueError, TypeError):
                        errors.append(f"Hook {i}: invalid timeout value")
            
            # Print results
            try:
                from rich.console import Console
                console = Console()
                
                if errors:
                    console.print("[red]Validation FAILED[/red]")
                    for error in errors:
                        console.print(f"  [red]✗[/red] {error}")
                else:
                    console.print("[green]Validation PASSED[/green]")
                
                if warnings:
                    console.print("\n[yellow]Warnings:[/yellow]")
                    for warning in warnings:
                        console.print(f"  [yellow]![/yellow] {warning}")
                
                console.print(f"\n[dim]Found {len(config.hooks)} hooks in config[/dim]")
            except ImportError:
                if errors:
                    print("Validation FAILED")
                    for error in errors:
                        print(f"  - {error}")
                else:
                    print("Validation PASSED")
                
                if warnings:
                    print("\nWarnings:")
                    for warning in warnings:
                        print(f"  - {warning}")
            
            return len(errors) == 0
            
        except FileNotFoundError as e:
            print(f"[red]Error: {e}[/red]")
            return False
        except json.JSONDecodeError as e:
            print(f"[red]Invalid JSON: {e}[/red]")
            return False
        except Exception as e:
            print(f"[red]Error validating config: {e}[/red]")
            return False
    
    def run_command_hook(
        self,
        command: str,
        event: str = "before_tool",
        input_json: Optional[str] = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Run a command hook manually.
        
        Args:
            command: Shell command to execute
            event: Event type for the hook
            input_json: Optional JSON input to pass to the command
            timeout: Timeout in seconds
            
        Returns:
            Execution result
        """
        from praisonaiagents.hooks import HookEvent, HookRegistry, HookRunner
        from praisonaiagents.hooks.events import BeforeToolInput
        from datetime import datetime
        
        registry = HookRegistry()
        registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command=command,
            name="cli_test_hook",
            timeout=timeout
        )
        
        runner = HookRunner(registry)
        
        # Create input
        if input_json:
            try:
                custom_input = json.loads(input_json)
            except json.JSONDecodeError:
                custom_input = {}
        else:
            custom_input = {}
        
        sample_input = BeforeToolInput(
            session_id="cli-manual",
            cwd=os.getcwd(),
            event_name=event,
            timestamp=datetime.now().isoformat(),
            tool_name=custom_input.get('tool_name', 'manual_test'),
            tool_input=custom_input.get('tool_input', {})
        )
        
        results = asyncio.run(runner.execute(HookEvent.BEFORE_TOOL, sample_input))
        
        if results:
            result = results[0]
            self._print_command_result(result)
            return result.to_dict()
        
        return {}
    
    def _print_command_result(self, result):
        """Print command hook result."""
        try:
            from rich.console import Console
            from rich.syntax import Syntax
            
            console = Console()
            
            console.print(f"\n[bold]Command Hook Result[/bold]")
            console.print(f"Exit Code: {result.exit_code}")
            console.print(f"Success: {'[green]Yes[/green]' if result.success else '[red]No[/red]'}")
            console.print(f"Duration: {result.duration_ms:.2f}ms")
            
            if result.stdout:
                console.print("\n[bold]STDOUT:[/bold]")
                console.print(result.stdout)
            
            if result.stderr:
                console.print("\n[bold]STDERR:[/bold]")
                console.print(f"[red]{result.stderr}[/red]")
            
            if result.output:
                console.print(f"\n[bold]Decision:[/bold] {result.output.decision}")
                if result.output.reason:
                    console.print(f"[bold]Reason:[/bold] {result.output.reason}")
        except ImportError:
            print(f"\nCommand Hook Result")
            print(f"Exit Code: {result.exit_code}")
            print(f"Success: {result.success}")
            if result.stdout:
                print(f"STDOUT: {result.stdout}")
            if result.stderr:
                print(f"STDERR: {result.stderr}")
    
    def register_from_config(self, config_path: str) -> int:
        """
        Register hooks from a configuration file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            Number of hooks registered
        """
        from praisonaiagents.hooks import HookEvent
        
        config = HooksConfig.from_file(config_path)
        registry = self._get_registry()
        
        event_map = {
            'before_tool': HookEvent.BEFORE_TOOL,
            'after_tool': HookEvent.AFTER_TOOL,
            'before_agent': HookEvent.BEFORE_AGENT,
            'after_agent': HookEvent.AFTER_AGENT,
            'session_start': HookEvent.SESSION_START,
            'session_end': HookEvent.SESSION_END,
        }
        
        count = 0
        for hook in config.hooks:
            event = event_map.get(hook.get('event', '').lower())
            if event is None:
                continue
            
            if 'command' in hook:
                registry.register_command(
                    event=event,
                    command=hook['command'],
                    name=hook.get('name'),
                    matcher=hook.get('matcher'),
                    timeout=hook.get('timeout', 60.0),
                    env=hook.get('env', {})
                )
                count += 1
        
        print(f"[green]Registered {count} hooks from {config_path}[/green]")
        return count


def handle_hooks_command(args: List[str], verbose: bool = False):
    """
    Handle hooks CLI commands.
    
    Usage:
        praisonai hooks list [--format json|table]
        praisonai hooks test <event> [target] [--input '{"key": "value"}']
        praisonai hooks validate <config_path>
        praisonai hooks run <command> [--event <event>] [--input <json>] [--timeout <seconds>]
        praisonai hooks load <config_path>
    """
    handler = HooksHandler(verbose=verbose)
    
    if not args:
        print("Usage: praisonai hooks <command> [options]")
        print("\nCommands:")
        print("  list                    List registered hooks")
        print("  test <event> [target]   Test hooks for an event")
        print("  validate <config>       Validate hooks configuration")
        print("  run <command>           Run a command hook manually")
        print("  load <config>           Load hooks from configuration file")
        return
    
    command = args[0]
    
    if command == "list":
        format_type = "table"
        if "--format" in args:
            idx = args.index("--format")
            if idx + 1 < len(args):
                format_type = args[idx + 1]
        handler.list_hooks(format=format_type)
    
    elif command == "test":
        if len(args) < 2:
            print("Usage: praisonai hooks test <event> [target] [--input <json>]")
            return
        
        event = args[1]
        target = args[2] if len(args) > 2 and not args[2].startswith("--") else None
        
        input_data = None
        if "--input" in args:
            idx = args.index("--input")
            if idx + 1 < len(args):
                try:
                    input_data = json.loads(args[idx + 1])
                except json.JSONDecodeError:
                    print("[red]Invalid JSON input[/red]")
                    return
        
        handler.test_hook(event, target, input_data)
    
    elif command == "validate":
        if len(args) < 2:
            print("Usage: praisonai hooks validate <config_path>")
            return
        handler.validate_config(args[1])
    
    elif command == "run":
        if len(args) < 2:
            print("Usage: praisonai hooks run <command> [--event <event>] [--input <json>] [--timeout <seconds>]")
            return
        
        cmd = args[1]
        event = "before_tool"
        input_json = None
        timeout = 60.0
        
        if "--event" in args:
            idx = args.index("--event")
            if idx + 1 < len(args):
                event = args[idx + 1]
        
        if "--input" in args:
            idx = args.index("--input")
            if idx + 1 < len(args):
                input_json = args[idx + 1]
        
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                try:
                    timeout = float(args[idx + 1])
                except ValueError:
                    print("[red]Invalid timeout value[/red]")
                    return
        
        handler.run_command_hook(cmd, event, input_json, timeout)
    
    elif command == "load":
        if len(args) < 2:
            print("Usage: praisonai hooks load <config_path>")
            return
        handler.register_from_config(args[1])
    
    elif command == "help" or command == "--help":
        print("Hooks CLI Commands:")
        print("\n  praisonai hooks list [--format json|table]")
        print("    List all registered hooks")
        print("\n  praisonai hooks test <event> [target] [--input <json>]")
        print("    Test hooks for a specific event")
        print("    Events: before_tool, after_tool, before_agent, after_agent, session_start, session_end")
        print("\n  praisonai hooks validate <config_path>")
        print("    Validate a hooks configuration file (JSON or YAML)")
        print("\n  praisonai hooks run <command> [--event <event>] [--input <json>] [--timeout <seconds>]")
        print("    Run a command hook manually for testing")
        print("\n  praisonai hooks load <config_path>")
        print("    Load and register hooks from a configuration file")
    
    else:
        print(f"[red]Unknown command: {command}[/red]")
        print("Use 'praisonai hooks help' for available commands")
