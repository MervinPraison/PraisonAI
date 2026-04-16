"""
n8n JSON to YAML Converter

Converts n8n JSON workflows back to PraisonAI YAML format.
"""

from typing import Dict, Any, List, Optional
import logging
import re

logger = logging.getLogger(__name__)

class N8nToYAMLConverter:
    """Convert n8n JSON workflows back to PraisonAI YAML format."""
    
    def __init__(self):
        self.agent_counter = 0
        
    def convert(self, n8n_workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Convert n8n JSON to PraisonAI YAML format.
        
        Args:
            n8n_workflow: n8n workflow JSON dict
            
        Returns:
            PraisonAI YAML workflow dict
        """
        logger.info(f"Converting n8n workflow: {n8n_workflow.get('name', 'Untitled')}")
        
        agents = {}
        steps = []
        
        nodes = n8n_workflow.get("nodes", [])
        connections = n8n_workflow.get("connections", {})
        
        # Extract agents from nodes
        for node in nodes:
            if self._is_agent_node(node):
                agent_id, agent_config = self._node_to_agent(node)
                agents[agent_id] = agent_config
        
        # Extract workflow steps from connections
        steps = self._connections_to_steps(nodes, connections)
        
        yaml_workflow = {
            "name": n8n_workflow.get("name", "Converted Workflow")
        }
        
        if agents:
            yaml_workflow["agents"] = agents
            
        if steps:
            yaml_workflow["steps"] = steps
            
        return yaml_workflow
    
    def _is_agent_node(self, node: Dict[str, Any]) -> bool:
        """Check if node represents an AI agent."""
        node_type = node.get("type", "")
        return (
            "langchain.agent" in node_type or
            "langchain.chainLlm" in node_type or
            node_type.startswith("@n8n/n8n-nodes-langchain") or
            node_type == "n8n-nodes-base.httpRequest"
        )

    def _node_to_agent_id(self, node: Dict[str, Any]) -> str:
        """Derive a stable agent id from node URL/name."""
        node_name = node.get("name", f"agent_{self.agent_counter}")
        node_type = node.get("type", "")
        if node_type == "n8n-nodes-base.httpRequest":
            url = str(node.get("parameters", {}).get("url", ""))
            match = re.search(r"/agents/([a-zA-Z0-9_-]+)$", url)
            if match:
                return match.group(1).lower()
        return node_name.lower().replace(" ", "_").replace("-", "_")
    
    def _node_to_agent(self, node: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """Convert n8n node to PraisonAI agent configuration."""
        node_name = node.get("name", f"agent_{self.agent_counter}")
        self.agent_counter += 1
        
        # Create agent ID from node name
        agent_id = self._node_to_agent_id(node)
        
        # Extract agent configuration from node parameters
        parameters = node.get("parameters", {})
        options = parameters.get("options", {})
        
        agent_config = {
            "name": node_name
        }
        
        # Extract system message/instructions
        if options.get("systemMessage"):
            agent_config["instructions"] = options["systemMessage"]
            
        # Extract role if present
        if options.get("role"):
            agent_config["role"] = options["role"]
            
        # Extract model/LLM configuration
        if options.get("model"):
            agent_config["llm"] = options["model"]
            
        # Extract tools
        tools = self._extract_tools(parameters)
        if tools:
            agent_config["tools"] = tools
            
        return agent_id, agent_config
    
    def _extract_tools(self, parameters: Dict[str, Any]) -> List[str]:
        """Extract tools from node parameters."""
        tools = []
        
        # Check for tools array in parameters
        if "tools" in parameters:
            tool_configs = parameters["tools"]
            if isinstance(tool_configs, list):
                for tool_config in tool_configs:
                    tool_name = self._map_n8n_tool_to_praisonai(tool_config)
                    if tool_name:
                        tools.append(tool_name)
        
        return tools
    
    def _map_n8n_tool_to_praisonai(self, tool_config: Dict[str, Any]) -> Optional[str]:
        """Map n8n tool configuration to PraisonAI tool name."""
        tool_type = tool_config.get("type", "")
        tool_name = tool_config.get("name", "")
        
        # Map common tool types
        tool_mapping = {
            "web_search": "tavily_search",
            "file_operations": "file_read",
            "code_execution": "python_exec",
            "shell_command": "shell_exec"
        }
        
        if tool_type in tool_mapping:
            return tool_mapping[tool_type]
        
        # Fallback to generic tool name
        if tool_name:
            return tool_name.lower().replace(" ", "_")
            
        return None
    
    def _connections_to_steps(self, nodes: List[Dict[str, Any]], connections: Dict[str, Any]) -> List[Any]:
        """Convert n8n connections to PraisonAI workflow steps."""
        steps = []
        
        # Create node name to agent mapping
        node_to_agent = {}
        for node in nodes:
            if self._is_agent_node(node):
                node_name = node.get("name")
                agent_id = self._node_to_agent_id(node)
                node_to_agent[node_name] = agent_id
        
        # Find trigger node and trace execution path
        trigger_nodes = [
            node for node in nodes 
            if node.get("type", "").endswith(".manualTrigger")
        ]
        
        if not trigger_nodes:
            # If no trigger, create simple sequential steps from agents
            for node in nodes:
                if self._is_agent_node(node):
                    agent_id = node_to_agent.get(node.get("name"))
                    if agent_id:
                        steps.append({"agent": agent_id})
            return steps
        
        # Trace execution from trigger
        trigger_name = trigger_nodes[0].get("name")
        visited = set()
        
        def trace_execution(current_node: str) -> List[Any]:
            """Recursively trace execution path."""
            if current_node in visited:
                return []
                
            visited.add(current_node)
            current_steps = []
            
            if current_node in connections:
                connection = connections[current_node]
                main_connections = connection.get("main", [[]])
                
                for output_connections in main_connections:
                    for conn in output_connections:
                        target_node = conn.get("node")
                        
                        if not target_node:
                            continue
                            
                        # Check if target is an agent
                        if target_node in node_to_agent:
                            agent_id = node_to_agent[target_node]
                            current_steps.append({"agent": agent_id})
                            
                        # Check if target is a control flow node
                        elif self._is_control_flow_node(target_node, nodes):
                            control_step = self._convert_control_flow(target_node, nodes, connections)
                            if control_step:
                                current_steps.append(control_step)
                        
                        # Continue tracing
                        current_steps.extend(trace_execution(target_node))
            
            return current_steps
        
        steps = trace_execution(trigger_name)
        return steps
    
    def _is_control_flow_node(self, node_name: str, nodes: List[Dict[str, Any]]) -> bool:
        """Check if node represents control flow (routing, parallel, etc.)."""
        for node in nodes:
            if node.get("name") == node_name:
                node_type = node.get("type", "")
                return (
                    "switch" in node_type or
                    "if" in node_type or
                    "merge" in node_type
                )
        return False
    
    def _convert_control_flow(
        self, 
        node_name: str, 
        nodes: List[Dict[str, Any]], 
        connections: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert control flow node to PraisonAI step."""
        for node in nodes:
            if node.get("name") == node_name:
                node_type = node.get("type", "")
                
                if "switch" in node_type:
                    return self._convert_switch_to_route(node, connections)
                elif "if" in node_type:
                    return self._convert_if_to_route(node, connections)
        
        return None
    
    def _convert_switch_to_route(
        self, 
        switch_node: Dict[str, Any], 
        connections: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert switch node to route step."""
        route_config = {}
        
        # Extract rules from switch node parameters
        parameters = switch_node.get("parameters", {})
        rules = parameters.get("rules", {}).get("rules", [])
        
        # Map switch outputs to routes
        switch_name = switch_node.get("name")
        if switch_name in connections:
            connection = connections[switch_name]
            main_connections = connection.get("main", [[]])
            
            for i, output_connections in enumerate(main_connections):
                if i < len(rules):
                    rule = rules[i]
                    route_key = rule.get("value2", f"condition_{i}")
                else:
                    route_key = "default"
                
                target_agents = []
                for conn in output_connections:
                    target_node = conn.get("node")
                    if target_node:
                        # Convert node name to agent ID
                        agent_id = target_node.lower().replace(" ", "_").replace("-", "_")
                        target_agents.append(agent_id)
                
                if target_agents:
                    route_config[route_key] = target_agents
        
        return {"route": route_config}
    
    def _convert_if_to_route(
        self, 
        if_node: Dict[str, Any], 
        connections: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert if node to simple route step."""
        route_config = {
            "true": [],
            "false": []
        }
        
        # Extract connections from if node
        if_name = if_node.get("name")
        if if_name in connections:
            connection = connections[if_name]
            main_connections = connection.get("main", [[], []])  # [true_path, false_path]
            
            for i, output_connections in enumerate(main_connections):
                route_key = "true" if i == 0 else "false"
                
                for conn in output_connections:
                    target_node = conn.get("node")
                    if target_node:
                        agent_id = target_node.lower().replace(" ", "_").replace("-", "_")
                        route_config[route_key].append(agent_id)
        
        return {"route": route_config}
