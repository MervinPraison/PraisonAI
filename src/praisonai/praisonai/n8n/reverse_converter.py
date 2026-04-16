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
        
        # Restore workflow description from staticData if present
        static_data = n8n_workflow.get("staticData", {})
        if static_data.get("praisonai_description"):
            yaml_workflow["description"] = static_data["praisonai_description"]
        
        if agents:
            yaml_workflow["agents"] = agents
            
        if steps:
            yaml_workflow["steps"] = steps
            
        return yaml_workflow
    
    def _is_agent_node(self, node: Dict[str, Any]) -> bool:
        """Check if node represents an AI agent."""
        node_type = node.get("type", "")
        
        # Check for LangChain nodes
        if ("langchain.agent" in node_type or
            "langchain.chainLlm" in node_type or
            node_type.startswith("@n8n/n8n-nodes-langchain")):
            return True
            
        # Check for httpRequest nodes that point to PraisonAI API
        if node_type == "n8n-nodes-base.httpRequest":
            url = str(node.get("parameters", {}).get("url", ""))
            return "/api/v1/agents/" in url and url.endswith("/invoke")
            
        return False

    def _node_to_agent_id(self, node: Dict[str, Any]) -> str:
        """Derive a stable agent id from node URL/name."""
        node_name = node.get("name", f"agent_{self.agent_counter}")
        node_type = node.get("type", "")
        if node_type == "n8n-nodes-base.httpRequest":
            url = str(node.get("parameters", {}).get("url", ""))
            # Match new API pattern: /api/v1/agents/{agent_id}/invoke
            match = re.search(r"/api/v1/agents/([a-z0-9_]+)/invoke$", url)
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
            
        # Extract additional agent fields for round-trip preservation
        if options.get("goal"):
            agent_config["goal"] = options["goal"]
            
        if options.get("backstory"):
            agent_config["backstory"] = options["backstory"]
            
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
        
        # Trace execution from trigger using BFS to get complete step order
        trigger_name = trigger_nodes[0].get("name")
        steps = self._trace_execution_complete(trigger_name, connections, node_to_agent, nodes)
        
        # If no steps found through connections, create sequential steps from all agents
        if not steps:
            for node in nodes:
                if self._is_agent_node(node):
                    agent_id = node_to_agent.get(node.get("name"))
                    if agent_id:
                        steps.append({"agent": agent_id})
        
        return steps
    
    def _trace_execution_complete(self, start_node: str, connections: Dict[str, Any], node_to_agent: Dict[str, str], nodes: List[Dict[str, Any]]) -> List[Any]:
        """Complete BFS traversal of execution graph to capture all agent steps."""
        from collections import deque
        
        steps = []
        visited = set()
        queue = deque([start_node])
        
        while queue:
            current_node = queue.popleft()
            
            if current_node in visited:
                continue
                
            visited.add(current_node)
            
            # If this is an agent node, add it as a step
            if current_node in node_to_agent:
                agent_id = node_to_agent[current_node]
                # Avoid duplicate agent steps
                if not any(step.get("agent") == agent_id for step in steps if isinstance(step, dict)):
                    steps.append({"agent": agent_id})
            # Preserve control flow steps (route/if) discovered during traversal
            elif self._is_control_flow_node(current_node, nodes):
                control_step = self._convert_control_flow(current_node, nodes, connections)
                if control_step and control_step not in steps:
                    steps.append(control_step)
            
            # Add all connected nodes to queue for processing
            if current_node in connections:
                connection = connections[current_node]
                main_connections = connection.get("main", [[]])
                
                for output_connections in main_connections:
                    for conn in output_connections:
                        target_node = conn.get("node")
                        if target_node and target_node not in visited:
                            queue.append(target_node)
        
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
