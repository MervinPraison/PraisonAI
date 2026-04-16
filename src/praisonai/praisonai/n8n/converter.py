"""
YAML to n8n JSON Converter

Converts PraisonAI YAML workflows to n8n JSON format for visual editing.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

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
        
        # If no steps defined, create simple chain from trigger to first agent
        if not steps and agent_nodes:
            first_agent = list(agent_nodes.values())[0]
            connections[trigger_node.name] = {
                "main": [[{"node": first_agent, "type": "main", "index": 0}]]
            }
        
        return {
            "name": yaml_workflow.get("name", "PraisonAI Workflow"),
            "nodes": [node.to_dict() for node in nodes],
            "connections": connections,
            "settings": {
                "executionOrder": "v1"
            },
            "staticData": {},
            "tags": ["praisonai", "agents"],
            "triggerCount": 1,
            "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "versionId": "1.0.0"
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
        has_tools = bool(config.get("tools"))
        
        # Determine node type based on agent capabilities
        if has_tools:
            node_type = "@n8n/n8n-nodes-langchain.agent"
        else:
            node_type = "@n8n/n8n-nodes-langchain.chainLlm"
        
        # Prepare parameters
        parameters = {
            "options": {}
        }
        
        if config.get("instructions"):
            parameters["options"]["systemMessage"] = config["instructions"]
            
        if config.get("role"):
            parameters["options"]["role"] = config["role"]
            
        if config.get("llm"):
            parameters["options"]["model"] = config["llm"]
            
        # Add tool configuration if present
        if has_tools:
            parameters["tools"] = self._convert_tools(config.get("tools", []))
            
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
                            
                elif "loop" in step:
                    # Loop step - create splitInBatches node for loop iteration
                    loop_node = self._create_split_in_batches_node(step["loop"])
                    all_nodes.append(loop_node)
                    
                    # Connect previous to split node
                    connections[previous_node] = {
                        "main": [[{"node": loop_node.name, "type": "main", "index": 0}]]
                    }
                    
                    # Connect split node to loop body agents
                    loop_targets = []
                    loop_config = step["loop"]
                    if "steps" in loop_config:
                        for loop_step in loop_config["steps"]:
                            if isinstance(loop_step, str) and loop_step in agent_nodes:
                                loop_targets.append({
                                    "node": agent_nodes[loop_step],
                                    "type": "main",
                                    "index": 0
                                })
                            elif isinstance(loop_step, dict) and "agent" in loop_step:
                                agent_id = loop_step["agent"]
                                if agent_id in agent_nodes:
                                    loop_targets.append({
                                        "node": agent_nodes[agent_id],
                                        "type": "main", 
                                        "index": 0
                                    })
                    
                    if loop_targets:
                        connections[loop_node.name] = {"main": [loop_targets]}
                        # Use the last loop target as previous node
                        previous_node = loop_targets[-1]["node"]
                    else:
                        previous_node = loop_node.name
        
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
    
    def _create_split_in_batches_node(self, loop_config: Dict[str, Any]) -> N8nNode:
        """Convert loop configuration to n8n SplitInBatches node."""
        self.node_counter += 1
        
        # Extract loop configuration
        batch_size = loop_config.get("batch_size", 1)
        input_field = loop_config.get("items", "items")
        
        return N8nNode(
            name=f"Loop {self.node_counter}",
            type="n8n-nodes-base.splitInBatches",
            position=[
                self.position_x_start + (self.node_counter * self.position_x_increment),
                self.position_y
            ],
            parameters={
                "batchSize": batch_size,
                "options": {}
            }
        )
    
    def _calculate_position(self, node_index: int) -> List[int]:
        """Calculate position for node layout."""
        x = self.position_x_start + (node_index * self.position_x_increment)
        return [x, self.position_y]