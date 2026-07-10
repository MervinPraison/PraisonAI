"""Workflow CLI commands (C8.4)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import yaml
from dotenv import load_dotenv
from rich import print

from praisonai.cli.legacy.framework_run import fw_workflow_module as _fw_workflow_module

def handle_workflow_command(self, action: str, action_args: list, variables: dict = None, args=None):
    """
    Handle workflow subcommand actions.
    
    Args:
        action: The workflow action (list, run, create, show)
        action_args: Additional arguments for the action
        variables: Workflow variables for substitution
        args: Parsed command line arguments
    """
    try:
        from praisonaiagents import Agent as PraisonAgent
        from praisonaiagents.memory import WorkflowManager
        from rich import print
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        manager = WorkflowManager(workspace_path=os.getcwd())
        
        if action == 'list':
            workflows = manager.list_workflows()
            if workflows:
                table = Table(title="Available Workflows")
                table.add_column("Name", style="cyan")
                table.add_column("Description", style="white")
                table.add_column("Steps", style="green")
                
                for workflow in workflows:
                    table.add_row(
                        workflow.name,
                        workflow.description[:50] + "..." if len(workflow.description) > 50 else workflow.description,
                        str(len(workflow.steps))
                    )
                
                console.print(table)
            else:
                print("[yellow]No workflows found. Create files in .praison/workflows/[/yellow]")
                
        elif action == 'run':
            if not action_args:
                print("[red]ERROR: Workflow name required. Usage: praisonai workflow run <name>[/red]")
                return
            workflow_name = action_args[0]
            
            # Check if it's a YAML file
            if workflow_name.endswith(('.yaml', '.yml')) and os.path.exists(workflow_name):
                # Use new YAML workflow parser
                self._run_yaml_workflow(workflow_name, action_args, variables, args)
                return
            
            # Use global flags (--llm, --tools, --planning, --memory, --save, --verbose)
            workflow_llm = getattr(args, 'llm', None) if args else None
            workflow_tools_str = getattr(args, 'tools', None) if args else None
            workflow_planning = getattr(args, 'planning', False) if args else False
            workflow_verbose = getattr(args, 'verbose', False) if args else False
            workflow_memory = getattr(args, 'memory', False) if args else False
            workflow_save = getattr(args, 'save', False) if args else False
            
            # Load tools if specified
            workflow_tools = None
            if workflow_tools_str:
                workflow_tools = self._load_tools(workflow_tools_str)
                if workflow_tools:
                    print(f"[cyan]Loaded {len(workflow_tools)} tool(s) for workflow[/cyan]")
            
            # Initialize memory if enabled
            memory = None
            if workflow_memory:
                try:
                    from praisonaiagents.memory import Memory
                    memory = Memory()
                    print("[cyan]Memory enabled for workflow[/cyan]")
                except ImportError:
                    print("[yellow]Warning: Memory not available[/yellow]")
            
            # Create default agent for steps without agent_config
            default_agent = PraisonAgent(
                name="WorkflowExecutor",
                role="Task Executor",
                goal="Execute workflow steps",
                llm=workflow_llm,
                tools=workflow_tools,
                verbose=1 if workflow_verbose else 0
            )
            
            print(f"[bold cyan]Running workflow: {workflow_name}[/bold cyan]")
            if workflow_planning:
                print("[cyan]Planning mode enabled[/cyan]")
            
            result = manager.execute(
                workflow_name,
                default_agent=default_agent,
                default_llm=workflow_llm,
                variables=variables or {},
                memory=memory,
                planning=workflow_planning,
                verbose=1 if workflow_verbose else 0,
                on_step=lambda step, i: print(f"[cyan]  → Step {i+1}: {step.name}[/cyan]"),
                on_result=lambda step, output: print(f"[green]  ✓ Completed: {step.name}[/green]")
            )
            
            if result.get("success"):
                print("[green]✅ Workflow completed successfully![/green]")
                for step_result in result.get("results", []):
                    status = "✅" if step_result.get("status") == "success" else "❌"
                    print(f"  {status} {step_result.get('step', 'Unknown step')}")
                
                # Show final output
                final_results = result.get("results", [])
                if final_results:
                    last_output = final_results[-1].get("output", "")
                    if last_output:
                        print("\n[bold]Final Output:[/bold]")
                        print(last_output[:2000] + "..." if len(last_output) > 2000 else last_output)
                
                # Save output if requested
                if workflow_save and final_results:
                    from datetime import datetime
                    output_dir = os.path.join(os.getcwd(), "output", "workflows")
                    os.makedirs(output_dir, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    safe_name = workflow_name.replace(" ", "_").lower()
                    output_file = os.path.join(output_dir, f"{timestamp}_{safe_name}.md")
                    
                    with open(output_file, "w") as f:
                        f.write(f"# Workflow: {workflow_name}\n\n")
                        f.write(f"**Executed:** {timestamp}\n\n")
                        for step_result in final_results:
                            f.write(f"## {step_result.get('step', 'Unknown')}\n\n")
                            f.write(f"**Status:** {step_result.get('status', 'unknown')}\n\n")
                            if step_result.get("output"):
                                f.write(f"{step_result['output']}\n\n")
                    
                    print(f"\n[green]✅ Output saved to: {output_file}[/green]")
            else:
                print(f"[red]❌ Workflow failed: {result.get('error', 'Unknown error')}[/red]")
                
        elif action == 'show':
            if not action_args:
                print("[red]ERROR: Workflow name required. Usage: praisonai workflow show <name>[/red]")
                return
            workflow_name = action_args[0]
            workflow = manager.get_workflow(workflow_name)
            if workflow:
                print(f"[bold cyan]Workflow: {workflow.name}[/bold cyan]")
                print(f"[bold]Description:[/bold] {workflow.description}")
                print(f"\n[bold]Steps ({len(workflow.steps)}):[/bold]")
                for i, step in enumerate(workflow.steps, 1):
                    print(f"  {i}. {step.name}: {step.action[:80]}...")
                if workflow.variables:
                    print(f"\n[bold]Variables:[/bold] {workflow.variables}")
            else:
                print(f"[red]Workflow not found: {workflow_name}[/red]")
                
        elif action == 'create':
            if not action_args:
                print("[red]ERROR: Workflow name required. Usage: praisonai workflow create <name>[/red]")
                return
            workflow_name = action_args[0]
            
            # Create a simple template workflow
            manager.create_workflow(
                name=workflow_name,
                description=f"Workflow created via CLI: {workflow_name}",
                steps=[
                    {"name": "Step 1", "action": "First step - edit this in .praison/workflows/"},
                    {"name": "Step 2", "action": "Second step - edit this in .praison/workflows/"}
                ]
            )
            print(f"[green]✅ Workflow created: {workflow_name}[/green]")
            print(f"[cyan]Edit the workflow in .praison/workflows/{workflow_name}.md[/cyan]")
            
        elif action == 'validate':
            # Validate a YAML workflow file
            if not action_args:
                print("[red]ERROR: YAML file required. Usage: praisonai workflow validate <file.yaml>[/red]")
                return
            yaml_file = action_args[0]
            if not yaml_file.endswith(('.yaml', '.yml')):
                print("[red]ERROR: File must be a YAML file (.yaml or .yml)[/red]")
                return
            self._validate_yaml_workflow(yaml_file)
            
        elif action == 'template':
            # Create from template
            template_name = action_args[0] if action_args else None
            output_file = None
            for i, arg in enumerate(action_args):
                if arg == '--output' and i + 1 < len(action_args):
                    output_file = action_args[i + 1]
            self._create_workflow_from_template(template_name, output_file)
        
        elif action == 'auto':
            # Auto-generate workflow from topic
            self._auto_generate_workflow(action_args)
            
        elif action == 'help' or action == '--help':
            print("[bold]Workflow Commands:[/bold]")
            print("  praisonai workflow list                  - List available workflows")
            print("  praisonai workflow run <name>            - Execute a workflow")
            print("  praisonai workflow run <file.yaml>       - Execute a YAML workflow")
            print("  praisonai workflow show <name>           - Show workflow details")
            print("  praisonai workflow create <name>         - Create a new workflow")
            print("  praisonai workflow validate <file.yaml>  - Validate a YAML workflow")
            print("  praisonai workflow template <name>       - Create from template")
            print('  praisonai workflow auto "topic"          - Auto-generate workflow')
            print("\n[bold]Templates:[/bold]")
            print("  simple, routing, parallel, loop, evaluator-optimizer")
            print("\n[bold]Options (uses global flags):[/bold]")
            print("  --workflow-var key=value                 - Set workflow variable (can be repeated)")
            print("  --var key=value                          - Set variable for YAML workflows")
            print("  --llm <model>                            - LLM model (e.g., openai/gpt-4o-mini)")
            print("  --tools <tools>                          - Tools (comma-separated, e.g., tavily)")
            print("  --planning                               - Enable planning mode")
            print("  --memory                                 - Enable memory")
            print("  --verbose                                - Enable verbose output")
            print("  --save                                   - Save output to file")
            print("\n[bold]Examples:[/bold]")
            print("  praisonai workflow run 'Research Blog' --tools tavily --save")
            print("  praisonai workflow run research.yaml --var topic='AI trends'")
            print("  praisonai workflow template routing --output my_workflow.yaml")
        else:
            print(f"[red]Unknown workflow action: {action}[/red]")
            print("Use 'praisonai workflow help' for available commands")
            
    except ImportError as e:
        print(f"[red]ERROR: Failed to import workflow module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except Exception as e:
        print(f"[red]ERROR: Workflow command failed: {e}[/red]")

def _run_yaml_workflow(self, yaml_file: str, action_args: list, variables: dict = None, args=None):
    """
    Run a YAML workflow file using the new YAMLWorkflowParser.
    
    Args:
        yaml_file: Path to the YAML workflow file
        action_args: Additional arguments
        variables: Workflow variables
        args: Parsed command line arguments
    """
    # Initialize trace variables for cleanup
    trace_writer = None
    trace_emitter = None
    trace_emitter_token = None
    
    try:
        from praisonaiagents.workflows import WorkflowManager
        from rich import print
        from rich.table import Table
        from rich.console import Console
        import uuid
        
        console = Console()
        manager = WorkflowManager()
        
        # Parse --var arguments from action_args
        parsed_vars = variables or {}
        i = 0
        while i < len(action_args):
            if action_args[i] == "--var" and i + 1 < len(action_args):
                var_str = action_args[i + 1]
                if "=" in var_str:
                    key, value = var_str.split("=", 1)
                    parsed_vars[key.strip()] = value.strip()
                i += 2
            else:
                i += 1
        
        # Get verbose flag
        verbose = '--verbose' in action_args or '-v' in action_args or (getattr(args, 'verbose', False) if args else False)
        
        # Get save flag for replay trace
        save_replay = '--save' in action_args or '-s' in action_args or (getattr(args, 'save', False) if args else False)
        
        # Initialize replay trace writer if --save flag is set
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        if save_replay:
            try:
                from praisonai_code._wrapper_bridge import import_wrapper_module
                _mod = import_wrapper_module('praisonai.replay')
                ContextTraceWriter = getattr(_mod, 'ContextTraceWriter')
                from praisonaiagents.trace.context_events import ContextTraceEmitter, set_context_emitter
                from pathlib import Path
                
                trace_writer = ContextTraceWriter(session_id=run_id)
                trace_emitter = ContextTraceEmitter(sink=trace_writer, session_id=run_id)
                # Set as global emitter so agents can access it
                trace_emitter_token = set_context_emitter(trace_emitter)
                trace_emitter.session_start({"workflow": yaml_file, "run_id": run_id})
                print(f"[cyan]📝 Replay trace enabled: {run_id}[/cyan]")
            except ImportError as e:
                import logging
                logging.debug(f"Replay module not available: {e}")
            except Exception as e:
                import logging
                logging.warning(f"Failed to initialize trace writer: {e}")
        
        print(f"[bold cyan]Running YAML workflow: {yaml_file}[/bold cyan]")
        if parsed_vars:
            print(f"[cyan]Variables: {parsed_vars}[/cyan]")
        
        # Auto-load tools.py from recipe directory if present
        import importlib.util
        from pathlib import Path
        
        yaml_path = Path(yaml_file).resolve()
        tools_file = yaml_path.parent / "tools.py"
        tool_registry = {}
        
        if tools_file.exists():
            try:
                from praisonai_code._safe_loader import load_user_module
                tools_module = load_user_module(str(tools_file), name="recipe_tools", allow_outside_cwd=True)
                if tools_module is not None:
                    import inspect
                    # Build registry from public functions only
                    for name, obj in vars(tools_module).items():
                        if inspect.isfunction(obj) and not name.startswith('_') and inspect.getmodule(obj) is tools_module:
                            tool_registry[name] = obj
                else:
                    logging.getLogger(__name__).warning("Recipe tools loading disabled. Set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable.")
                
                if tool_registry:
                    print(f"[cyan]Loaded {len(tool_registry)} tools from tools.py: {', '.join(tool_registry.keys())}[/cyan]")
            except Exception as e:
                print(f"[yellow]Warning: Failed to load tools.py: {e}[/yellow]")
        
        # Load and execute the YAML workflow with tool registry
        workflow = manager.load_yaml(yaml_file, tool_registry=tool_registry)

        validate_workflow_framework = _fw_workflow_module().validate_workflow_framework
        validate_workflow_framework(
            getattr(workflow, "framework", "praisonai"),
            source=f"workflow file {yaml_file}",
        )
        
        # Show workflow info
        table = Table(title=f"Workflow: {workflow.name}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Steps", str(len(workflow.steps)))
        table.add_row("Planning", str(workflow.planning))
        table.add_row("Reasoning", str(workflow.reasoning))
        console.print(table)
        
        # Merge variables
        if parsed_vars:
            workflow.variables.update(parsed_vars)
        
        # Set verbose
        if verbose:
            workflow.verbose = True
        
        # Set context management from CLI args
        context_auto_compact = getattr(args, 'context_auto_compact', None) if args else None
        context_strategy = getattr(args, 'context_strategy', None) if args else None
        context_threshold = getattr(args, 'context_threshold', None) if args else None
        
        if context_auto_compact is True or context_strategy or context_threshold:
            # Enable context management with CLI-specified options
            try:
                from praisonaiagents.context import ManagerConfig
                config_kwargs = {"auto_compact": True}
                if context_strategy:
                    from praisonaiagents.context import OptimizerStrategy
                    strategy_map = {
                        "truncate": OptimizerStrategy.TRUNCATE,
                        "sliding_window": OptimizerStrategy.SLIDING_WINDOW,
                        "prune_tools": OptimizerStrategy.PRUNE_TOOLS,
                        "summarize": OptimizerStrategy.SUMMARIZE,
                        "smart": OptimizerStrategy.SMART,
                    }
                    config_kwargs["strategy"] = strategy_map.get(context_strategy, OptimizerStrategy.SMART)
                if context_threshold:
                    config_kwargs["compact_threshold"] = context_threshold
                workflow.context = ManagerConfig(**config_kwargs)
                print(f"[cyan]Context management enabled (strategy={context_strategy or 'smart'}, threshold={context_threshold or 0.8})[/cyan]")
            except ImportError:
                print("[yellow]Warning: Context management not available[/yellow]")
        
        # Determine workflow input: CLI --var input takes precedence, then the
        # YAML top-level `input:` field (stored on workflow.default_input).
        default_input = getattr(workflow, "default_input", "") or ""
        start_input = parsed_vars.get("input", default_input) if parsed_vars else default_input

        # Seed the runtime `{{input}}` variable when it is not overridden via --var
        if start_input and (not parsed_vars or "input" not in parsed_vars):
            workflow.variables.setdefault("input", start_input)

        if start_input:
            preview = start_input[:80] + ("..." if len(start_input) > 80 else "")
            print(f"[cyan]Workflow input: {preview}[/cyan]")
        else:
            print("[yellow]Warning: no workflow input — {{input}} will be empty unless --var input=... is set[/yellow]")

        # Execute
        print("\n[bold]Executing workflow...[/bold]\n")
        result = workflow.start(start_input)
        
        if result.get("status") == "completed":
            print("\n[green]✅ Workflow completed successfully![/green]")
            
            # Show output
            if result.get("output"):
                print("\n[bold]Output:[/bold]")
                output = result["output"]
                if len(output) > 2000:
                    print(output[:2000] + "...")
                else:
                    print(output)
        else:
            print(f"\n[red]❌ Workflow failed: {result.get('error', 'Unknown error')}[/red]")
        
        # Close trace writer on completion
        if trace_emitter:
            trace_emitter.session_end()
            print(f"[cyan]📝 Replay trace saved: {run_id}[/cyan]")
        if trace_writer:
            trace_writer.close()
        # Reset global emitter
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
            
    except FileNotFoundError:
        # Cleanup trace on error
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        print(f"[red]ERROR: YAML file not found: {yaml_file}[/red]")
    except Exception as e:
        # Cleanup trace on error
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        print(f"[red]ERROR: YAML workflow failed: {e}[/red]")
        import traceback
        traceback.print_exc()

def _validate_yaml_workflow(self, yaml_file: str):
    """
    Validate a YAML workflow file.
    
    Args:
        yaml_file: Path to the YAML workflow file
    """
    try:
        from praisonaiagents.workflows import YAMLWorkflowParser
        from rich import print
        from rich.table import Table
        from rich.console import Console
        import yaml
        
        console = Console()
        
        if not os.path.exists(yaml_file):
            print(f"[red]ERROR: File not found: {yaml_file}[/red]")
            return
        
        print(f"[cyan]Validating: {yaml_file}[/cyan]")
        
        # Load raw YAML to check for non-canonical names
        with open(yaml_file, 'r') as f:
            raw_data = yaml.safe_load(f)
        
        # Check for non-canonical names and suggest canonical ones
        suggestions = self._get_canonical_suggestions(raw_data)
        
        parser = YAMLWorkflowParser()
        workflow = parser.parse_file(yaml_file)

        validate_workflow_framework = _fw_workflow_module().validate_workflow_framework
        validate_workflow_framework(
            getattr(workflow, "framework", "praisonai"),
            source=f"workflow file {yaml_file}",
        )
        
        # Show validation results
        table = Table(title="Workflow Validation")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Name", workflow.name)
        table.add_row("Description", getattr(workflow, 'description', 'N/A'))
        table.add_row("Steps", str(len(workflow.steps)))
        table.add_row("Variables", str(len(workflow.variables)))
        table.add_row("Planning", str(workflow.planning))
        table.add_row("Reasoning", str(workflow.reasoning))
        
        console.print(table)
        print("[green]✓ Workflow is valid![/green]")
        
        # Show suggestions for canonical names
        if suggestions:
            print()
            print("[yellow]💡 Suggestions for canonical field names:[/yellow]")
            for suggestion in suggestions:
                print(f"   [dim]•[/dim] {suggestion}")
            print()
            print("[dim]Note: Both old and new names work, but canonical names are recommended.[/dim]")
        
    except Exception as e:
        print(f"[red]✗ Validation failed: {e}[/red]")

def _get_canonical_suggestions(self, data: dict) -> list:
    """
    Check for non-canonical field names and return suggestions.
    
    Canonical names (A-I-G-S mnemonic):
    - Agents (not roles)
    - Instructions (not backstory)
    - Goal (same)
    - Steps (not tasks)
    
    Also:
    - name (not topic)
    - action (not description)
    
    Args:
        data: Raw YAML data
        
    Returns:
        List of suggestion strings
    """
    suggestions = []
    
    if not data:
        return suggestions
    
    # Check top-level keys
    if 'roles' in data:
        suggestions.append("Use 'agents' instead of 'roles'")
    
    if 'topic' in data and 'name' not in data:
        suggestions.append("Use 'name' instead of 'topic'")
    
    # Check agent fields
    agents_data = data.get('agents', data.get('roles', {}))
    for agent_id, agent_config in agents_data.items():
        if isinstance(agent_config, dict):
            if 'backstory' in agent_config:
                suggestions.append(f"Agent '{agent_id}': Use 'instructions' instead of 'backstory'")
            
            # Check nested tasks
            if 'tasks' in agent_config:
                suggestions.append(f"Agent '{agent_id}': Use 'steps' at top level instead of nested 'tasks'")
    
    # Check step fields
    steps_data = data.get('steps', [])
    for i, step in enumerate(steps_data):
        if isinstance(step, dict):
            if 'description' in step and 'action' not in step:
                step_name = step.get('name', f'step {i+1}')
                suggestions.append(f"Step '{step_name}': Use 'action' instead of 'description'")
            
            # Check parallel steps
            if 'parallel' in step:
                for j, parallel_step in enumerate(step['parallel']):
                    if isinstance(parallel_step, dict):
                        if 'description' in parallel_step and 'action' not in parallel_step:
                            suggestions.append(f"Parallel step {j+1}: Use 'action' instead of 'description'")
    
    return suggestions

def _create_workflow_from_template(self, template_name: str = None, output_file: str = None):
    """
    Create a workflow from a template.
    
    Uses templates from WorkflowHandler to avoid duplication.
    
    Args:
        template_name: Name of the template
        output_file: Output file path
    """
    from rich import print
    
    # Use templates from WorkflowHandler to avoid duplication
    try:
        from ..features.workflow import WorkflowHandler
        templates = WorkflowHandler.TEMPLATES
    except ImportError:
        print("[red]ERROR: WorkflowHandler not available.[/red]")
        return
    
    if not template_name:
        print("[red]ERROR: Template name required.[/red]")
        print(f"[cyan]Available templates: {', '.join(templates.keys())}[/cyan]")
        return
    
    if template_name not in templates:
        print(f"[red]ERROR: Unknown template: {template_name}[/red]")
        print(f"[cyan]Available templates: {', '.join(templates.keys())}[/cyan]")
        return
    
    # Default output file
    if not output_file:
        output_file = f"{template_name}_workflow.yaml"
    
    # Check if file exists
    if os.path.exists(output_file):
        print(f"[red]ERROR: File already exists: {output_file}[/red]")
        return
    
    # Write template
    with open(output_file, 'w') as f:
        f.write(templates[template_name])
    
    print(f"[green]✓ Created workflow: {output_file}[/green]")
    print(f"[cyan]Run with: praisonai workflow run {output_file}[/cyan]")

def _auto_generate_workflow(self, action_args: list):
    """
    Auto-generate a workflow from a topic description.
    
    Args:
        action_args: ["topic description", --pattern, <pattern>, --output, <file.yaml>]
    """
    from rich import print
    
    # Parse arguments
    topic = None
    pattern = "sequential"
    output_file = None
    
    i = 0
    while i < len(action_args):
        if action_args[i] == "--pattern" and i + 1 < len(action_args):
            pattern = action_args[i + 1]
            i += 2
        elif action_args[i] == "--output" and i + 1 < len(action_args):
            output_file = action_args[i + 1]
            i += 2
        elif not action_args[i].startswith("--") and topic is None:
            topic = action_args[i]
            i += 1
        else:
            i += 1
    
    if not topic:
        print('[red]Usage: praisonai workflow auto "topic" --pattern <pattern>[/red]')
        print("[cyan]Patterns: sequential, routing, parallel[/cyan]")
        return
    
    # Validate pattern
    valid_patterns = ["sequential", "routing", "parallel", "loop", "orchestrator-workers", "evaluator-optimizer"]
    if pattern not in valid_patterns:
        print(f"[red]Unknown pattern: {pattern}[/red]")
        print(f"[cyan]Valid patterns: {', '.join(valid_patterns)}[/cyan]")
        return
    
    # Default output file
    if not output_file:
        safe_name = "".join(c if c.isalnum() else "_" for c in topic[:30]).lower()
        output_file = f"{safe_name}_workflow.yaml"
    
    # Check if file exists
    if os.path.exists(output_file):
        print(f"[red]ERROR: File already exists: {output_file}[/red]")
        return
    
    print(f"[cyan]Generating {pattern} workflow for: {topic}[/cyan]")
    
    try:
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module('praisonai.auto')
        WorkflowAutoGenerator = getattr(_mod, 'WorkflowAutoGenerator')
        
        generator = WorkflowAutoGenerator(
            topic=topic,
            workflow_file=output_file
        )
        
        result_path = generator.generate(pattern=pattern)
        
        print(f"[green]✓ Created workflow: {result_path}[/green]")
        print(f"[cyan]Run with: praisonai workflow run {output_file}[/cyan]")
        
    except ImportError:
        print("[red]Auto-generation requires litellm: pip install litellm[/red]")
    except Exception as e:
        print(f"[red]Generation failed: {e}[/red]")
