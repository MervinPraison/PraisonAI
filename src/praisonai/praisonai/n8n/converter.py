"""
YAML to n8n JSON Converter

Converts PraisonAI YAML workflows to n8n JSON format for visual editing.
"""

from typing import Dict, Any, List
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)

@dataclass
class N8nNode:
    """Represents an n8n workflow node."""
    name: str
    type: str
    position: List[int]
    parameters: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "type": self.type,
            "position": self.position,
            "parameters": self.parameters
        }

class YAMLToN8nConverter:
    """Convert PraisonAI YAML workflows to n8n JSON format."""
    
    def __init__(self):
        self.node_counter = 0
        self.position_y = 300
        self.position_x_start = 250
        self.position_x_increment = 200
        
    def convert(self, yaml_workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Convert YAML workflow to n8n JSON.
        
        Args:
            yaml_workflow: Parsed YAML workflow dict
            
        Returns:
            n8n workflow JSON dict
        """
        logger.info(f"Converting workflow: {yaml_workflow.get('name', 'Untitled')}")
        
        nodes = []
        connections = {}
        
        # Add trigger node (always first)
        trigger_node = self._create_trigger_node()
        nodes.append(trigger_node)
        
        # Convert agents to nodes
        agents = yaml_workflow.get("agents", {})
        agent_nodes = {}
        
        for agent_id, agent_config in agents.items():
            node = self._agent_to_node(agent_id, agent_config)
            nodes.append(node)
            agent_nodes[agent_id] = node.name
            
        # Convert steps to connections
        steps = yaml_workflow.get("steps", [])
        connections = self._steps_to_connections(steps, agent_nodes, nodes)
        
        
        # Define fields allowed by n8n Public API
        ALLOWED_FIELDS = ["name", "nodes", "connections", "settings"]
        
        workflow_data = {
            "name": yaml_workflow.get("name", "PraisonAI Workflow"),
            "nodes": [node.to_dict() for node in nodes],
            "connections": connections,
            "settings": {
                "executionOrder": "v1"
            }
        }
        
        # Filter to only allowed fields for n8n Public API
        return {
            key: value for key, value in workflow_data.items()
            if key in ALLOWED_FIELDS
        }
    
    def _create_trigger_node(self) -> N8nNode:
        """Create manual trigger node."""
        return N8nNode(
            name="Manual Trigger",
            type="n8n-nodes-base.manualTrigger",
            position=[self.position_x_start, self.position_y],
            parameters={}
        )
    
    def _agent_to_node(self, agent_id: str, config: Dict[str, Any]) -> N8nNode:
        """Convert PraisonAI agent to n8n node."""
        self.node_counter += 1
        
        # Use httpRequest node type that points to PraisonAI API
        node_type = "n8n-nodes-base.httpRequest"
        
        # Build HTTP request parameters for PraisonAI API
        agent_url_id = re.sub(r"[^a-z0-9_]", "_", agent_id.lower().replace(" ", "_"))
        agent_url_id = re.sub(r"_+", "_", agent_url_id).strip("_")
        if not agent_url_id:
            agent_url_id = f"agent_{self.node_counter}"
        
        # Use message from webhook for first agent, result from previous for others
        query_expr = "$json.body?.message || $json.message || 'Execute task'"
        if self.node_counter > 1:
            query_expr = "$json.result || 'Continue workflow'"
        
        parameters = {
            "method": "POST",
            "url": f"http://localhost:8000/api/v1/agents/{agent_id}/invoke",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ message: {query_expr} }}) }}}}",
            "options": {
                "timeout": 300000  # 5 minute timeout
            }
        }
            
        return N8nNode(
            name=config.get("name", agent_id.replace("_", " ").title()),
            type=node_type,
            position=[
                self.position_x_start + (self.node_counter * self.position_x_increment),
                self.position_y
            ],
            parameters=parameters
        )
    
    def _convert_tools(self, tools: List[str]) -> List[Dict[str, Any]]:
        """Convert PraisonAI tools to n8n tool format."""
        converted_tools = []
        
        tool_mapping = {
            "tavily_search": {"type": "web_search", "name": "Web Search"},
            "web_search": {"type": "web_search", "name": "Web Search"},
            "file_read": {"type": "file_operations", "name": "File Read"},
            "file_write": {"type": "file_operations", "name": "File Write"},
            "python_exec": {"type": "code_execution", "name": "Python Execution"},
            "shell_exec": {"type": "shell_command", "name": "Shell Command"}
        }
        
        for tool in tools:
            if tool in tool_mapping:
                converted_tools.append(tool_mapping[tool])
            else:
                # Generic tool mapping
                converted_tools.append({
                    "type": "custom_tool",
                    "name": tool.replace("_", " ").title()
                })
                
        return converted_tools
    
    def _steps_to_connections(
        self, 
        steps: List[Dict[str, Any]], 
        agent_nodes: Dict[str, str],
        all_nodes: List[N8nNode]
    ) -> Dict[str, Any]:
        """Convert workflow steps to n8n connections."""
        connections = {}
        
        if not steps:
            # If no steps defined but we have agents, create sequential chain
            if agent_nodes:
                return self._build_sequential_connections(agent_nodes, "Manual Trigger")
            return connections
            
        # Start with trigger node
        previous_node = "Manual Trigger"
        
        for step in steps:
            if isinstance(step, str):
                # Simple agent reference
                if step in agent_nodes:
                    target_agent = agent_nodes[step]
                    connections[previous_node] = {
                        "main": [[{"node": target_agent, "type": "main", "index": 0}]]
                    }
                    previous_node = target_agent
                    
            elif isinstance(step, dict):
                if "agent" in step:
                    # Agent step with action
                    agent_id = step["agent"]
                    if agent_id in agent_nodes:
                        target_agent = agent_nodes[agent_id]
                        connections[previous_node] = {
                            "main": [[{"node": target_agent, "type": "main", "index": 0}]]
                        }
                        previous_node = target_agent
                        
                elif "route" in step:
                    # Routing step - create switch node
                    switch_node = self._create_switch_node(step["route"])
                    all_nodes.append(switch_node)
                    
                    # Connect previous to switch
                    connections[previous_node] = {
                        "main": [[{"node": switch_node.name, "type": "main", "index": 0}]]
                    }
                    
                    # Connect switch to target agents
                    switch_connections = []
                    for route_key, target_agents in step["route"].items():
                        if route_key != "default" and target_agents:
                            if isinstance(target_agents, list):
                                target_agent = target_agents[0]  # Use first agent for simplicity
                            else:
                                target_agent = target_agents
                                
                            if target_agent in agent_nodes:
                                switch_connections.append({
                                    "node": agent_nodes[target_agent], 
                                    "type": "main", 
                                    "index": len(switch_connections)
                                })
                    
                    connections[switch_node.name] = {"main": [switch_connections]}
                    previous_node = switch_node.name
                    
                elif "parallel" in step:
                    # Parallel execution - fan out to multiple agents
                    parallel_targets = []
                    for parallel_step in step["parallel"]:
                        if isinstance(parallel_step, dict) and "agent" in parallel_step:
                            agent_id = parallel_step["agent"]
                            if agent_id in agent_nodes:
                                parallel_targets.append({
                                    "node": agent_nodes[agent_id],
                                    "type": "main",
                                    "index": 0
                                })
                                
                    if parallel_targets:
                        connections[previous_node] = {"main": [parallel_targets]}
                        # For simplicity, use last parallel agent as previous
                        if parallel_targets:
                            previous_node = parallel_targets[-1]["node"]
        
        return connections
    
    def _build_sequential_connections(self, agent_nodes: Dict[str, str], trigger_name: str) -> Dict[str, Any]:
        """Build sequential connections between agents.
        
        Creates agent[i] -> agent[i+1] connections for all adjacent pairs.
        
        Args:
            agent_nodes: Dictionary mapping agent IDs to node names
            trigger_name: Name of the trigger node
            
        Returns:
            Dictionary of n8n connections
        """
        connections = {}
        agent_names = list(agent_nodes.values())
        
        if not agent_names:
            return connections
            
        # Connect trigger to first agent
        connections[trigger_name] = {
            "main": [[{"node": agent_names[0], "type": "main", "index": 0}]]
        }
        
        # Connect each agent to the next one (sequential chain)
        for i in range(len(agent_names) - 1):
            connections[agent_names[i]] = {
                "main": [[{"node": agent_names[i + 1], "type": "main", "index": 0}]]
            }
            
        return connections
    
    def _create_switch_node(self, route_config: Dict[str, Any]) -> N8nNode:
        """Convert route configuration to n8n Switch node."""
        self.node_counter += 1
        
        rules = []
        for route_key in route_config.keys():
            if route_key != "default":
                rules.append({
                    "operation": "equal",
                    "value1": f"={{$json.condition}}",
                    "value2": route_key
                })
        
        return N8nNode(
            name=f"Router {self.node_counter}",
            type="n8n-nodes-base.switch",
            position=[
                self.position_x_start + (self.node_counter * self.position_x_increment),
                self.position_y
            ],
            parameters={
                "rules": {
                    "rules": rules
                }
            }
        )
    
    def _calculate_position(self, node_index: int) -> List[int]:
        """Calculate position for node layout."""
        x = self.position_x_start + (node_index * self.position_x_increment)
        return [x, self.position_y]
