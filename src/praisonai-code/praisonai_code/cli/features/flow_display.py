"""
Flow Display Handler for CLI.

Shows a visual flow diagram of the workflow WITHOUT executing it.
Usage: praisonai agents.yaml --flow-display
"""

from typing import Any, Dict, Tuple
from .base import FlagHandler
import os
import yaml


class FlowDisplayHandler(FlagHandler):
    """
    Handler for --flow-display flag.
    
    Shows a visual flow diagram/chart of agents and tasks WITHOUT executing.
    This allows users to preview the workflow structure before running it.
    
    Example:
        praisonai agents.yaml --flow-display
    """
    
    def __init__(self, verbose: bool = False):
        super().__init__(verbose)
        self._console = None
    
    @property
    def feature_name(self) -> str:
        return "flow_display"
    
    @property
    def flag_name(self) -> str:
        return "flow-display"
    
    @property
    def flag_help(self) -> str:
        return "Show workflow flow diagram without executing"
    
    def _get_console(self):
        """Get or create Rich Console."""
        if self._console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                pass
        return self._console
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if Rich is available."""
        try:
            import importlib.util
            rich_available = importlib.util.find_spec("rich") is not None
            if not rich_available:
                return False, "rich not installed. Install with: pip install rich"
            return True, ""
        except ImportError:
            return False, "rich not installed. Install with: pip install rich"
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """Apply flow display configuration."""
        if flag_value:
            config['flow_display'] = True
        return config
    
    def display_flow_diagram(self, yaml_file: str, show_footer: bool = True) -> bool:
        """
        Display a visual flow diagram of the workflow from YAML file.
        
        Args:
            yaml_file: Path to the agents.yaml file
            show_footer: Whether to show the "run without --flow-display" footer
            
        Returns:
            True if displayed successfully, False otherwise
        """
        console = self._get_console()
        if not console:
            print("Rich library not available for flow display")
            return False
        
        # Load YAML config
        try:
            if not os.path.exists(yaml_file):
                console.print(f"[red]Error: File not found: {yaml_file}[/red]")
                return False
            
            with open(yaml_file, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            console.print(f"[red]Error loading YAML: {e}[/red]")
            return False
        
        # Detect YAML format: 'roles' (old) or 'agents'+'steps' (new workflow)
        has_roles = 'roles' in config and config['roles']
        has_agents = 'agents' in config and config['agents']
        has_steps = 'steps' in config and config['steps']
        
        if not has_roles and not has_agents:
            console.print("[red]Error: Invalid YAML format. No 'roles' or 'agents' found.[/red]")
            return False
        
        try:
            from rich.panel import Panel
            from rich.table import Table
            from rich.text import Text
            from rich import box
            
            # Determine format type
            is_workflow_format = has_agents and has_steps
            
            # Extract workflow info based on format
            if is_workflow_format:
                name = config.get('name', 'Workflow')
                description = config.get('description', '')
                framework = config.get('framework', 'praisonai')
                workflow_config = config.get('workflow', {})
                memory = workflow_config.get('memory_config', {}).get('persist', False)
                num_agents = len(config['agents'])
                num_steps = len(config['steps'])
            else:
                name = config.get('topic', 'Workflow')
                description = ''
                framework = config.get('framework', 'praisonai')
                process = config.get('process', 'sequential')
                memory = config.get('memory', False)
                num_agents = len(config['roles'])
                num_steps = sum(len(details.get('tasks', {})) for details in config['roles'].values())
            
            # Build the flow diagram
            console.print()
            
            # === HEADER ===
            header = Text()
            header.append("📊 WORKFLOW FLOW DIAGRAM\n", style="bold cyan")
            header.append("─" * 40, style="dim")
            
            header_panel = Panel(
                header,
                border_style="cyan",
                box=box.DOUBLE_EDGE,
                padding=(0, 2)
            )
            console.print(header_panel)
            
            # === WORKFLOW INFO ===
            info_table = Table(show_header=False, box=None, padding=(0, 2))
            info_table.add_column("Key", style="bold yellow")
            info_table.add_column("Value", style="white")
            
            info_table.add_row("📋 Name:", name)
            if description:
                info_table.add_row("📝 Description:", description)
            
            # Show input if present ('input' is canonical, 'topic' is alias)
            workflow_input = config.get('input', config.get('topic', ''))
            if workflow_input:
                info_table.add_row("💬 Input:", workflow_input)
            
            info_table.add_row("⚙️  Framework:", framework)
            
            if is_workflow_format:
                info_table.add_row("🔄 Format:", "WORKFLOW (steps-based)")
                planning = workflow_config.get('planning', False)
                info_table.add_row("🧠 Planning:", "✅ Enabled" if planning else "❌ Disabled")
            else:
                info_table.add_row("🔄 Process:", process.upper())
            
            info_table.add_row("💾 Memory:", "✅ Enabled" if memory else "❌ Disabled")
            info_table.add_row("👥 Agents:", str(num_agents))
            info_table.add_row("📝 Steps:", str(num_steps))
            
            console.print(Panel(info_table, title="[bold white]Workflow Configuration[/bold white]", 
                               border_style="blue", box=box.ROUNDED))
            console.print()
            
            # === FLOW DIAGRAM ===
            if is_workflow_format:
                self._display_steps_flow(console, config)
            else:
                process = config.get('process', 'sequential')
                if process == 'sequential':
                    self._display_sequential_flow(console, config)
                elif process == 'hierarchical':
                    self._display_hierarchical_flow(console, config)
                else:
                    self._display_sequential_flow(console, config)
            
            # === DETAILED AGENT INFO ===
            console.print()
            if is_workflow_format:
                self._display_workflow_agent_details(console, config)
            else:
                self._display_agent_details(console, config)
            
            # === FOOTER ===
            if show_footer:
                console.print()
                footer = Text()
                footer.append("💡 ", style="bold")
                footer.append("To execute this workflow, run without --flow-display flag", style="dim italic")
                console.print(Panel(footer, border_style="dim", box=box.ROUNDED))
            console.print()
            
            return True
            
        except ImportError as e:
            console.print(f"[red]Error: Rich components not available: {e}[/red]")
            return False
    
    def _display_sequential_flow(self, console, config: Dict):
        """Display sequential flow diagram."""
        from rich.panel import Panel
        from rich.text import Text
        from rich import box
        
        roles = list(config['roles'].items())
        
        # Box width (content area)
        BOX_WIDTH = 36
        
        def pad_line(content: str, width: int = BOX_WIDTH) -> str:
            """Pad content to fixed width."""
            padding = width - len(content)
            if padding > 0:
                return content + " " * padding
            return content[:width]
        
        flow_text = Text()
        flow_text.append("  SEQUENTIAL EXECUTION FLOW\n\n", style="bold magenta")
        
        for i, (role_key, details) in enumerate(roles):
            role_name = details.get('role', role_key)
            tasks = list(details.get('tasks', {}).keys())
            
            # Agent box
            if i == 0:
                flow_text.append("       ┌── START ──┐\n", style="green")
                flow_text.append("             │\n", style="dim")
                flow_text.append("             ▼\n", style="dim")
            
            # Agent node
            flow_text.append("       ╔════════════════════════════════════╗\n", style="cyan")
            line = f" Agent {i+1}: {role_name}"
            flow_text.append(f"       ║{pad_line(line)}║\n", style="cyan")
            
            # Tasks
            for task in tasks:
                line = f"   -> {task}"
                flow_text.append(f"       ║{pad_line(line)}║\n", style="dim white")
            
            flow_text.append("       ╚════════════════════════════════════╝\n", style="cyan")
            
            # Arrow to next
            if i < len(roles) - 1:
                flow_text.append("             │\n", style="dim")
                flow_text.append("          output\n", style="dim italic")
                flow_text.append("             ▼\n", style="dim")
            else:
                flow_text.append("             │\n", style="dim")
                flow_text.append("             ▼\n", style="dim")
                flow_text.append("       └── END ────┘\n", style="red")
        
        console.print(Panel(flow_text, border_style="magenta", box=box.DOUBLE_EDGE,
                           title="[bold white]Execution Flow[/bold white]"))
    
    def _display_hierarchical_flow(self, console, config: Dict):
        """Display hierarchical flow diagram."""
        from rich.panel import Panel
        from rich.text import Text
        from rich import box
        
        manager_llm = config.get('manager_llm', 'default')
        
        flow_text = Text()
        flow_text.append("👑 HIERARCHICAL EXECUTION FLOW\n\n", style="bold magenta")
        
        # Manager at top
        flow_text.append("         ┌──────────────────────┐\n", style="yellow")
        flow_text.append("         │  👑 MANAGER AGENT    │\n", style="bold yellow")
        flow_text.append(f"         │  LLM: {manager_llm:<14}│\n", style="dim yellow")
        flow_text.append("         └──────────┬───────────┘\n", style="yellow")
        flow_text.append("                    │\n", style="dim")
        flow_text.append("         ┌──────────┴───────────┐\n", style="dim")
        flow_text.append("         │    delegates to      │\n", style="dim italic")
        flow_text.append("         └──────────┬───────────┘\n", style="dim")
        
        roles = list(config['roles'].items())
        num_agents = len(roles)
        
        # Draw branches
        if num_agents > 0:
            branch_line = "    "
            for i in range(num_agents):
                if i == 0:
                    branch_line += "┌" + "─" * 8
                elif i == num_agents - 1:
                    branch_line += "┬" + "─" * 8 + "┐"
                else:
                    branch_line += "┬" + "─" * 8
            flow_text.append(branch_line + "\n", style="dim")
            
            # Agent boxes
            for i, (role_key, details) in enumerate(roles):
                flow_text.append("\n    ╔═══════════════╗", style="cyan")
            flow_text.append("\n")
            
            for i, (role_key, details) in enumerate(roles):
                role_name = details.get('role', role_key)[:12]
                flow_text.append(f"    ║ 🤖 {role_name:<10} ║", style="cyan")
            flow_text.append("\n")
            
            for i, (role_key, details) in enumerate(roles):
                flow_text.append("    ╚═══════════════╝", style="cyan")
            flow_text.append("\n")
        
        console.print(Panel(flow_text, border_style="magenta", box=box.DOUBLE_EDGE,
                           title="[bold white]Execution Flow[/bold white]"))
    
    def _display_agent_details(self, console, config: Dict):
        """Display detailed agent information."""
        from rich.table import Table
        from rich import box
        
        table = Table(
            title="[bold cyan]📋 Agent & Task Details[/bold cyan]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
            expand=True
        )
        
        table.add_column("#", style="dim", width=3, justify="center")
        table.add_column("Agent", style="bold yellow", min_width=15)
        table.add_column("Role", style="cyan", min_width=15)
        table.add_column("Goal", style="white", min_width=25, overflow="fold")
        table.add_column("Tasks", style="green", min_width=20)
        table.add_column("Tools", style="magenta", min_width=15)
        
        for i, (role_key, details) in enumerate(config['roles'].items(), 1):
            role_name = details.get('role', role_key)
            goal = details.get('goal', '-')
            if len(goal) > 50:
                goal = goal[:47] + "..."
            
            tasks = list(details.get('tasks', {}).keys())
            tasks_str = "\n".join(f"• {t}" for t in tasks) if tasks else "-"
            
            tools = details.get('tools', [])
            tools_str = ", ".join(t for t in tools if t) if tools else "-"
            
            table.add_row(
                str(i),
                role_name,
                role_key,
                goal,
                tasks_str,
                tools_str
            )
        
        console.print(table)
    
    def _display_steps_flow(self, console, config: Dict):
        """Display steps-based workflow flow diagram."""
        from rich.panel import Panel
        from rich.text import Text
        from rich import box
        
        steps = config.get('steps', [])
        agents = config.get('agents', {})
        
        # Box width (content area)
        BOX_WIDTH = 36
        
        def pad_line(content: str, width: int = BOX_WIDTH) -> str:
            """Pad content to fixed width, accounting for emoji width."""
            # Emojis typically take 2 character widths
            emoji_count = sum(1 for c in content if ord(c) > 0x1F300)
            actual_len = len(content) + emoji_count  # Add extra for emoji width
            padding = width - actual_len
            if padding > 0:
                return content + " " * padding
            return content[:width]
        
        flow_text = Text()
        flow_text.append("  STEPS-BASED EXECUTION FLOW\n\n", style="bold magenta")
        
        flow_text.append("       ┌── START ──┐\n", style="green")
        flow_text.append("             │\n", style="dim")
        flow_text.append("             ▼\n", style="dim")
        
        for i, step in enumerate(steps):
            # Determine step type
            agent_key = step.get('agent', '')
            step_name = step.get('name', '')
            
            # Check for special step types
            has_route = 'route' in step
            has_parallel = 'parallel' in step
            has_loop = 'loop' in step
            has_repeat = 'repeat' in step
            
            if has_route:
                # Route step
                flow_text.append("       ╔════════════════════════════════════╗\n", style="yellow")
                line = f" ROUTE: {step_name or 'routing'}"
                flow_text.append(f"       ║{pad_line(line)}║\n", style="yellow")
                
                routes = step['route']
                for route_name, route_agents in routes.items():
                    agents_str = ", ".join(route_agents) if isinstance(route_agents, list) else str(route_agents)
                    line = f"   -> {route_name}: {agents_str}"
                    flow_text.append(f"       ║{pad_line(line)}║\n", style="yellow")
                
                flow_text.append("       ╚════════════════════════════════════╝\n", style="yellow")
                
            elif has_parallel:
                # Parallel step
                flow_text.append("       ╔════════════════════════════════════╗\n", style="green")
                line = f" PARALLEL: {step_name or 'parallel'}"
                flow_text.append(f"       ║{pad_line(line)}║\n", style="green")
                
                for p_step in step['parallel']:
                    p_agent = p_step.get('agent', '?')
                    line = f"   |-- {p_agent}"
                    flow_text.append(f"       ║{pad_line(line)}║\n", style="green")
                
                flow_text.append("       ╚════════════════════════════════════╝\n", style="green")
                
            else:
                # Regular agent step
                agent_info = agents.get(agent_key, {})
                agent_name = agent_info.get('name', agent_key)
                
                flow_text.append("       ╔════════════════════════════════════╗\n", style="cyan")
                line = f" Step {i+1}: {agent_name}"
                flow_text.append(f"       ║{pad_line(line)}║\n", style="cyan")
                
                # Show modifiers
                if has_loop:
                    loop_over = step['loop'].get('over', '?')
                    line = f"   [loop over: {loop_over}]"
                    flow_text.append(f"       ║{pad_line(line)}║\n", style="dim magenta")
                
                if has_repeat:
                    until = step['repeat'].get('until', '?')
                    max_iter = step['repeat'].get('max_iterations', '?')
                    line = f"   [repeat until: {until} max:{max_iter}]"
                    flow_text.append(f"       ║{pad_line(line)}║\n", style="dim magenta")
                
                flow_text.append("       ╚════════════════════════════════════╝\n", style="cyan")
            
            # Arrow to next
            if i < len(steps) - 1:
                flow_text.append("             │\n", style="dim")
                flow_text.append("             ▼\n", style="dim")
        
        flow_text.append("             │\n", style="dim")
        flow_text.append("             ▼\n", style="dim")
        flow_text.append("       └── END ────┘\n", style="red")
        
        console.print(Panel(flow_text, border_style="magenta", box=box.DOUBLE_EDGE,
                           title="[bold white]Execution Flow[/bold white]"))
    
    def _display_workflow_agent_details(self, console, config: Dict):
        """Display detailed agent information for workflow format."""
        from rich.table import Table
        from rich import box
        
        table = Table(
            title="[bold cyan]📋 Agent Details[/bold cyan]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            padding=(0, 1),
            expand=True
        )
        
        table.add_column("#", style="dim", width=3, justify="center")
        table.add_column("Agent Key", style="bold yellow", min_width=15)
        table.add_column("Name", style="cyan", min_width=15)
        table.add_column("Role", style="white", min_width=20)
        table.add_column("Goal", style="green", min_width=25, overflow="fold")
        
        for i, (agent_key, details) in enumerate(config['agents'].items(), 1):
            name = details.get('name', agent_key)
            role = details.get('role', '-')
            goal = details.get('goal', '-')
            if len(goal) > 40:
                goal = goal[:37] + "..."
            
            table.add_row(
                str(i),
                agent_key,
                name,
                role,
                goal
            )
        
        console.print(table)
    
    def display_workflow_start(self, workflow_name: str, agents: list) -> None:
        """
        Display workflow start message.
        
        Args:
            workflow_name: Name of the workflow being started
            agents: List of agent names in the workflow
        """
        console = self._get_console()
        if console:
            try:
                from rich.panel import Panel
                from rich import box
                
                agents_str = ", ".join(agents) if agents else "No agents"
                content = f"🚀 Starting: {workflow_name}\n👥 Agents: {agents_str}"
                console.print(Panel(content, title="[bold cyan]Workflow Started[/bold cyan]", 
                                   border_style="cyan", box=box.ROUNDED))
            except ImportError:
                print(f"Starting workflow: {workflow_name} with agents: {agents}")
    
    def display_workflow_end(self, success: bool = True) -> None:
        """
        Display workflow end message.
        
        Args:
            success: Whether the workflow completed successfully
        """
        console = self._get_console()
        if console:
            try:
                from rich.panel import Panel
                from rich import box
                
                if success:
                    content = "✅ Workflow completed successfully"
                    style = "green"
                else:
                    content = "❌ Workflow failed"
                    style = "red"
                
                console.print(Panel(content, title=f"[bold {style}]Workflow Ended[/bold {style}]", 
                                   border_style=style, box=box.ROUNDED))
            except ImportError:
                status = "successfully" if success else "with errors"
                print(f"Workflow ended {status}")
    
    def execute(self, yaml_file: str = None, **kwargs) -> bool:
        """
        Execute flow display - shows diagram without running workflow.
        
        Args:
            yaml_file: Path to the YAML file
            
        Returns:
            True if displayed successfully
        """
        if yaml_file:
            return self.display_flow_diagram(yaml_file)
        return False
