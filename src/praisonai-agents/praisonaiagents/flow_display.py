"""
Flow Display for PraisonAI Agents

Visual display with agents in center and tools on sides.
"""

from typing import Dict, List, Set, Tuple
from collections import defaultdict
import threading

# Lazy imports for rich components
_rich_cache = {}

def _get_rich_components():
    """Lazy import all rich components."""
    if not _rich_cache:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        from rich.align import Align
        from rich.columns import Columns
        from rich.table import Table
        from rich import box
        _rich_cache['Console'] = Console
        _rich_cache['Panel'] = Panel
        _rich_cache['Text'] = Text
        _rich_cache['Align'] = Align
        _rich_cache['Columns'] = Columns
        _rich_cache['Table'] = Table
        _rich_cache['box'] = box
    return _rich_cache

class FlowDisplay:
    """Displays agent workflow with agents centered and tools on sides."""
    
    def __init__(self):
        rich = _get_rich_components()
        self.console = rich['Console']()
        self.agents = []  # List of agents in order
        self.agent_tools = defaultdict(list)  # agent -> [tools]
        self.tracking = False
        self.lock = threading.Lock()
        
    def start(self):
        """Start tracking workflow."""
        self.tracking = True
        self.agents.clear()
        self.agent_tools.clear()
        
        # Register callbacks
        try:
            from praisonaiagents.main import register_display_callback
            
            def on_interaction(**kwargs):
                if self.tracking:
                    agent = kwargs.get('agent_name', 'Unknown')
                    self._add_agent(agent)
                    
            def on_tool_call(message, **kwargs):
                if self.tracking and "called function" in message:
                    parts = message.split("'")
                    if len(parts) > 1:
                        tool_name = parts[1]
                        agent = kwargs.get('agent_name', 'Unknown')
                        self._add_tool(agent, tool_name)
                        
            register_display_callback('interaction', on_interaction)
            register_display_callback('tool_call', on_tool_call)
            
        except ImportError:
            pass
            
    def stop(self):
        """Stop tracking and display the flow."""
        self.tracking = False
        self.display()
        
    def _add_agent(self, name: str):
        """Add an agent if not already present."""
        with self.lock:
            if name not in self.agents:
                self.agents.append(name)
                
    def _add_tool(self, agent_name: str, tool_name: str):
        """Add a tool to an agent."""
        with self.lock:
            if agent_name not in self.agents:
                self.agents.append(agent_name)
            if tool_name not in self.agent_tools[agent_name]:
                self.agent_tools[agent_name].append(tool_name)
                
    def display(self):
        """Display the flow chart with agents in center and tools on sides."""
        if not self.agents:
            return
            
        self.console.print("\n[bold cyan]🔄 Agent Workflow Flow[/bold cyan]\n")
        
        # Display start
        self._display_centered_node("── start ──", "grey35")
        self._display_arrow_down()
        
        # Display each agent with their tools
        for i, agent in enumerate(self.agents):
            self._display_agent_with_tools(agent)
            
            # Add arrow to next agent or end
            if i < len(self.agents) - 1:
                self._display_arrow_down()
        
        # Display end
        self._display_arrow_down()
        self._display_centered_node("── end ──", "grey35")
        
    def _display_agent_with_tools(self, agent: str):
        """Display agent with tools on the sides."""
        rich = _get_rich_components()
        Table = rich['Table']
        Panel = rich['Panel']
        Text = rich['Text']
        Align = rich['Align']
        box = rich['box']
        
        tools = self.agent_tools.get(agent, [])
        
        if not tools:
            # No tools - just agent
            self._display_centered_node(agent, "purple")
        else:
            # Split tools between left and right
            left_tools = tools[::2]  # Even indices
            right_tools = tools[1::2]  # Odd indices
            
            # Create the layout
            table = Table(show_header=False, show_edge=False, box=None, padding=0)
            table.add_column(justify="center", min_width=20)  # Left tools
            table.add_column(justify="center", min_width=5)   # Space
            table.add_column(justify="center", min_width=20)  # Agent
            table.add_column(justify="center", min_width=5)   # Space
            table.add_column(justify="center", min_width=20)  # Right tools
            
            # Create panels
            left_panel = self._create_tools_panel(left_tools) if left_tools else ""
            agent_panel = Panel(
                Text(agent, style="white on purple", justify="center"),
                style="white on purple",
                box=box.ROUNDED,
                padding=(0, 2)
            )
            right_panel = self._create_tools_panel(right_tools) if right_tools else ""
            
            # Add row
            table.add_row(left_panel, "", agent_panel, "", right_panel)
            
            # Display centered
            self.console.print(Align.center(table))
            
            # Show arrows
            if left_tools or right_tools:
                arrow_parts = []
                if left_tools:
                    arrow_parts.append("←→")
                else:
                    arrow_parts.append("  ")
                    
                arrow_parts.append("        ")  # Center space
                
                if right_tools:
                    arrow_parts.append("←→")
                else:
                    arrow_parts.append("  ")
                    
                self.console.print(Align.center(Text("".join(arrow_parts))))
                
    def _create_tools_panel(self, tools: List[str]):
        """Create a panel for tools."""
        rich = _get_rich_components()
        Panel = rich['Panel']
        Text = rich['Text']
        box = rich['box']
        
        if not tools:
            return ""
            
        if len(tools) == 1:
            return Panel(
                Text(tools[0], style="black on yellow", justify="center"),
                style="black on yellow",
                box=box.ROUNDED,
                padding=(0, 1)
            )
        else:
            # Multiple tools
            content = "\n".join(tools)
            return Panel(
                Text(content, style="black on yellow", justify="center"),
                style="black on yellow",
                box=box.ROUNDED,
                padding=(0, 1)
            )
            
    def _display_centered_node(self, label: str, color: str):
        """Display a centered node."""
        rich = _get_rich_components()
        Panel = rich['Panel']
        Text = rich['Text']
        Align = rich['Align']
        box = rich['box']
        
        panel = Panel(
            Text(label, style=f"white on {color}", justify="center"),
            style=f"white on {color}",
            box=box.ROUNDED,
            padding=(0, 2)
        )
        self.console.print(Align.center(panel))
        
    def _display_arrow_down(self):
        """Display a downward arrow."""
        rich = _get_rich_components()
        Align = rich['Align']
        
        self.console.print()
        self.console.print(Align.center("↓"))
        self.console.print()


# Simple function to create and use
def track_workflow():
    """Create a flow display tracker."""
    return FlowDisplay()