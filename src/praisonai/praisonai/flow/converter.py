"""YAML ↔ Langflow JSON Converter.

Converts PraisonAI YAML workflows to/from Langflow JSON format for seamless
visual workflow editing and execution.

Architecture:
- YAML → Langflow: Uses YAMLWorkflowParser + node mapping
- Langflow → YAML: Extracts from Langflow JSON + canonical mapping
- Auto-layout: Grid positioning algorithm for visual clarity
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    requests = None


class YAMLToLangflowConverter:
    """Converts PraisonAI YAML workflows to Langflow JSON format."""
    
    def __init__(self):
        """Initialize converter with node positioning state."""
        self.node_positions: Dict[str, Tuple[int, int]] = {}
        self.current_x = 100
        self.current_y = 200
        self.node_spacing_x = 300
        self.node_spacing_y = 150
        self.max_nodes_per_row = 3
        
    def convert(self, yaml_path: str) -> Dict[str, Any]:
        """
        Convert YAML workflow file to Langflow JSON format.
        
        Args:
            yaml_path: Path to YAML workflow file
            
        Returns:
            Langflow JSON flow definition
        """
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        # Parse YAML workflow
        parser = YAMLWorkflowParser()
        workflow = parser.parse_file(yaml_path)
        
        # Extract metadata from parsed YAML for direct access
        yaml_path = Path(yaml_path)
        with open(yaml_path, 'r') as f:
            import yaml
            raw_yaml = yaml.safe_load(f)
        
        # Convert workflow to Langflow nodes
        nodes, edges = self._convert_workflow_to_nodes(workflow, raw_yaml)
        
        # Generate flow metadata
        flow_name = workflow.name or yaml_path.stem
        flow_description = getattr(workflow, 'description', f'Converted from {yaml_path.name}')
        
        # Build Langflow JSON structure
        langflow_json = {
            "data": {
                "nodes": nodes,
                "edges": edges
            },
            "description": flow_description,
            "name": flow_name,
            "last_tested_version": "1.1.0",
            "endpoint_name": flow_name.lower().replace(' ', '_'),
        }
        
        return langflow_json
    
    def _convert_workflow_to_nodes(self, workflow, raw_yaml: Dict) -> Tuple[List[Dict], List[Dict]]:
        """
        Convert workflow and raw YAML to Langflow nodes and edges.
        
        Args:
            workflow: Parsed Workflow object
            raw_yaml: Raw YAML data for agent definitions
            
        Returns:
            Tuple of (nodes, edges) lists
        """
        nodes = []
        edges = []
        
        # Get agents from raw YAML (handles both 'agents' and 'roles' formats)
        agents_data = raw_yaml.get('agents', {})
        if not agents_data and 'roles' in raw_yaml:
            # Convert roles to agents format
            agents_data = self._convert_roles_to_agents(raw_yaml['roles'])
        
        # Create agent nodes
        agent_nodes = []
        for agent_id, agent_config in agents_data.items():
            node = self._create_agent_node(agent_id, agent_config)
            nodes.append(node)
            agent_nodes.append(node)
        
        # Create orchestrator node based on process type
        process = raw_yaml.get('process', 'sequential')
        orchestrator = self._create_orchestrator_node(process, raw_yaml, agent_nodes)
        nodes.append(orchestrator)
        
        # Create input/output nodes
        input_node = self._create_input_node(raw_yaml)
        output_node = self._create_output_node()
        nodes.extend([input_node, output_node])
        
        # Create edges
        edges.extend(self._create_edges(agent_nodes, orchestrator, input_node, output_node))
        
        return nodes, edges
    
    def _create_agent_node(self, agent_id: str, agent_config: Dict) -> Dict:
        """Create a PraisonAI Agent node for Langflow."""
        node_id = f"PraisonAIAgent-{agent_id}"
        x, y = self._get_next_position()
        
        # Map agent config to Langflow component inputs
        template = {
            "agent_name": {"value": agent_config.get('name', agent_id)},
            "role": {"value": agent_config.get('role', '')},
            "goal": {"value": agent_config.get('goal', '')},
            "backstory": {"value": agent_config.get('backstory', '')},
            "instructions": {"value": agent_config.get('instructions', '')},
            "llm": {"value": agent_config.get('llm', 'openai/gpt-4o-mini')},
            "tools": {"value": agent_config.get('tools', [])},
            "memory": {"value": agent_config.get('memory', False)},
            "allow_delegation": {"value": agent_config.get('allow_delegation', False)},
            "allow_code_execution": {"value": agent_config.get('allow_code_execution', False)},
            "verbose": {"value": agent_config.get('verbose', False)},
            "self_reflect": {"value": agent_config.get('self_reflect', False)},
            "max_iter": {"value": agent_config.get('max_iter', 20)},
        }
        
        # Add optional fields if present
        if 'planning' in agent_config:
            template["planning"] = {"value": agent_config['planning']}
        if 'reasoning' in agent_config:
            template["reasoning"] = {"value": agent_config['reasoning']}
        if 'guardrails' in agent_config:
            template["guardrails"] = {"value": agent_config['guardrails']}
        
        return {
            "id": node_id,
            "type": "genericNode",
            "position": {"x": x, "y": y},
            "data": {
                "type": "PraisonAIAgent",
                "node": {
                    "template": template,
                    "display_name": f"Agent: {agent_config.get('name', agent_id)}",
                    "description": f"PraisonAI agent: {agent_config.get('role', agent_id)}",
                }
            }
        }
    
    def _create_orchestrator_node(self, process: str, raw_yaml: Dict, agent_nodes: List[Dict]) -> Dict:
        """Create a PraisonAI Agents (orchestrator) node."""
        node_id = "PraisonAIAgents-orchestrator"
        x, y = self._get_next_position()
        
        # Map workflow config to orchestrator inputs
        template = {
            "team_name": {"value": raw_yaml.get('name', 'AgentTeam')},
            "process": {"value": process},
            "memory": {"value": raw_yaml.get('memory', False)},
            "verbose": {"value": raw_yaml.get('verbose', False)},
            "planning": {"value": raw_yaml.get('planning', False)},
            "guardrails": {"value": raw_yaml.get('guardrails', False)},
        }
        
        # Add manager LLM for hierarchical process
        if process == 'hierarchical':
            manager_llm = raw_yaml.get('manager_llm', 'openai/gpt-4o')
            template["manager_llm"] = {"value": manager_llm}
        
        # Add variables if present
        if 'variables' in raw_yaml:
            template["global_variables"] = {"value": raw_yaml['variables']}
        
        return {
            "id": node_id,
            "type": "genericNode",
            "position": {"x": x, "y": y},
            "data": {
                "type": "PraisonAIAgents",
                "node": {
                    "template": template,
                    "display_name": f"Agent Team ({process})",
                    "description": f"Multi-agent orchestrator using {process} process",
                }
            }
        }
    
    def _create_input_node(self, raw_yaml: Dict) -> Dict:
        """Create a ChatInput node."""
        node_id = "ChatInput-input"
        x, y = 100, 100  # Fixed position at top-left
        
        # Get default input from YAML
        default_input = raw_yaml.get('input', raw_yaml.get('topic', ''))
        
        return {
            "id": node_id,
            "type": "genericNode",
            "position": {"x": x, "y": y},
            "data": {
                "type": "ChatInput",
                "node": {
                    "template": {
                        "input_value": {"value": default_input},
                        "sender": {"value": "User"},
                        "sender_name": {"value": "User"},
                        "session_id": {"value": ""},
                    },
                    "display_name": "Chat Input",
                    "description": "Input for chat messages",
                }
            }
        }
    
    def _create_output_node(self) -> Dict:
        """Create a ChatOutput node."""
        node_id = "ChatOutput-output" 
        x, y = self._get_next_position()
        
        return {
            "id": node_id,
            "type": "genericNode", 
            "position": {"x": x, "y": y},
            "data": {
                "type": "ChatOutput",
                "node": {
                    "template": {
                        "input_value": {"value": ""},
                        "sender": {"value": "AI"},
                        "sender_name": {"value": "AI"},
                        "session_id": {"value": ""},
                    },
                    "display_name": "Chat Output",
                    "description": "Output for chat messages",
                }
            }
        }
    
    def _create_edges(self, agent_nodes: List[Dict], orchestrator: Dict, 
                     input_node: Dict, output_node: Dict) -> List[Dict]:
        """Create edges connecting nodes in the flow."""
        edges = []
        
        # Connect input to orchestrator
        edges.append({
            "id": f"edge-{input_node['id']}-{orchestrator['id']}",
            "source": input_node['id'],
            "target": orchestrator['id'],
            "sourceHandle": "message",
            "targetHandle": "input_value",
        })
        
        # Connect each agent to orchestrator
        for agent_node in agent_nodes:
            edges.append({
                "id": f"edge-{agent_node['id']}-{orchestrator['id']}",
                "source": agent_node['id'],
                "target": orchestrator['id'], 
                "sourceHandle": "agent",
                "targetHandle": "agents",
            })
        
        # Connect orchestrator to output
        edges.append({
            "id": f"edge-{orchestrator['id']}-{output_node['id']}",
            "source": orchestrator['id'],
            "target": output_node['id'],
            "sourceHandle": "response",
            "targetHandle": "input_value",
        })
        
        return edges
    
    def _get_next_position(self) -> Tuple[int, int]:
        """Get next position for node placement using grid layout."""
        x = self.current_x
        y = self.current_y
        
        # Store position
        position_key = f"{self.current_x},{self.current_y}"
        self.node_positions[position_key] = (x, y)
        
        # Calculate next position
        self.current_x += self.node_spacing_x
        
        # Wrap to next row if needed
        if len(self.node_positions) % self.max_nodes_per_row == 0:
            self.current_x = 100
            self.current_y += self.node_spacing_y
        
        return x, y
    
    def _convert_roles_to_agents(self, roles: Dict[str, Dict]) -> Dict[str, Dict]:
        """Convert legacy roles format to agents format."""
        agents = {}
        for role_id, role_config in roles.items():
            agent = {
                'name': role_config.get('role', role_id),
                'role': role_config.get('role', role_id),
                'goal': role_config.get('goal', ''),
                'instructions': role_config.get('backstory', ''),
            }
            
            # Copy optional fields
            if 'llm' in role_config:
                llm_config = role_config['llm']
                if isinstance(llm_config, dict):
                    agent['llm'] = llm_config.get('model', 'openai/gpt-4o-mini')
                else:
                    agent['llm'] = llm_config
            
            if 'tools' in role_config:
                agent['tools'] = [t for t in role_config['tools'] if t]
            
            # Copy other fields
            for field in ['planning', 'reasoning', 'verbose', 'max_iter', 
                         'allow_delegation', 'allow_code_execution']:
                if field in role_config:
                    agent[field] = role_config[field]
            
            agents[role_id] = agent
        
        return agents


class LangflowToYAMLConverter:
    """Converts Langflow JSON flows back to PraisonAI YAML format."""
    
    def convert(self, langflow_json: Dict[str, Any]) -> str:
        """
        Convert Langflow JSON back to YAML format.
        
        Args:
            langflow_json: Langflow JSON flow definition
            
        Returns:
            YAML string
        """
        import yaml
        
        data = langflow_json.get("data", {})
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        
        # Extract flow metadata
        flow_name = langflow_json.get("name", "Converted Flow")
        flow_description = langflow_json.get("description", "")
        
        # Find PraisonAI nodes
        agent_nodes = []
        orchestrator_node = None
        
        for node in nodes:
            node_data = node.get("data", {})
            node_type = node_data.get("type", "")
            
            if node_type == "PraisonAIAgent":
                agent_nodes.append(node)
            elif node_type == "PraisonAIAgents":
                orchestrator_node = node
        
        # Build YAML structure
        yaml_data = {
            "name": flow_name,
        }
        
        if flow_description:
            yaml_data["description"] = flow_description
        
        # Extract framework and process from orchestrator
        if orchestrator_node:
            template = orchestrator_node.get("data", {}).get("node", {}).get("template", {})
            process = template.get("process", {}).get("value", "sequential")
            yaml_data["framework"] = "praisonai"
            yaml_data["process"] = process
            
            # Extract manager LLM if hierarchical
            if process == "hierarchical" and "manager_llm" in template:
                yaml_data["manager_llm"] = template["manager_llm"].get("value")
            
            # Extract variables
            if "global_variables" in template:
                variables = template["global_variables"].get("value")
                if variables:
                    yaml_data["variables"] = variables
        
        # Convert agents
        agents = {}
        for agent_node in agent_nodes:
            template = agent_node.get("data", {}).get("node", {}).get("template", {})
            agent_id = self._extract_agent_id_from_node(agent_node)
            
            agent_config = {}
            
            # Extract agent fields
            field_mapping = {
                "agent_name": "name",
                "role": "role", 
                "goal": "goal",
                "backstory": "backstory",
                "instructions": "instructions",
                "llm": "llm",
                "tools": "tools",
                "memory": "memory",
                "allow_delegation": "allow_delegation",
                "allow_code_execution": "allow_code_execution",
                "verbose": "verbose",
                "self_reflect": "self_reflect",
                "max_iter": "max_iter",
            }
            
            for langflow_field, yaml_field in field_mapping.items():
                if langflow_field in template:
                    value = template[langflow_field].get("value")
                    if value is not None and value != "" and value != []:
                        # Skip default values to keep YAML clean
                        if self._is_non_default_value(yaml_field, value):
                            agent_config[yaml_field] = value
            
            agents[agent_id] = agent_config
        
        if agents:
            yaml_data["agents"] = agents
        
        # Convert to YAML string
        return yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)
    
    def _extract_agent_id_from_node(self, node: Dict) -> str:
        """Extract agent ID from Langflow node."""
        node_id = node.get("id", "")
        if node_id.startswith("PraisonAIAgent-"):
            return node_id.replace("PraisonAIAgent-", "")
        
        # Fallback: use agent name
        template = node.get("data", {}).get("node", {}).get("template", {})
        agent_name = template.get("agent_name", {}).get("value", "agent")
        return agent_name.lower().replace(" ", "_")
    
    def _is_non_default_value(self, field: str, value: Any) -> bool:
        """Check if value is different from default to avoid cluttering YAML."""
        defaults = {
            "llm": "openai/gpt-4o-mini",
            "memory": False,
            "allow_delegation": False,
            "allow_code_execution": False,
            "verbose": False,
            "self_reflect": False,
            "max_iter": 20,
            "tools": [],
        }
        
        if field in defaults:
            return value != defaults[field]
        return bool(value)  # Include non-empty values for other fields


class LangflowAPIClient:
    """Client for Langflow REST API operations."""
    
    def __init__(self, base_url: str = "http://localhost:7860"):
        """Initialize client with Langflow server URL."""
        self.base_url = base_url.rstrip("/")
        
        if not requests:
            raise ImportError("requests is required for Langflow API operations. Install with: pip install requests")
    
    def upload_flow(self, flow_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload a flow to Langflow.
        
        Args:
            flow_json: Langflow JSON flow definition
            
        Returns:
            API response with flow ID
        """
        url = f"{self.base_url}/api/v1/flows/upload/"
        
        try:
            response = requests.post(url, json=flow_json, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to upload flow to Langflow: {e}")
    
    def download_flow(self, flow_id: str) -> Dict[str, Any]:
        """
        Download a flow from Langflow.
        
        Args:
            flow_id: UUID of the flow to download
            
        Returns:
            Langflow JSON flow definition
        """
        url = f"{self.base_url}/api/v1/flows/{flow_id}"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to download flow from Langflow: {e}")
    
    def list_flows(self) -> List[Dict[str, Any]]:
        """
        List all flows in Langflow.
        
        Returns:
            List of flow metadata
        """
        url = f"{self.base_url}/api/v1/flows/"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json().get("flows", [])
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to list flows from Langflow: {e}")
    
    def health_check(self) -> bool:
        """
        Check if Langflow server is running.
        
        Returns:
            True if server is healthy
        """
        url = f"{self.base_url}/api/v1/health"
        
        try:
            response = requests.get(url, timeout=10)
            return response.status_code == 200
        except requests.RequestException:
            return False


def yaml_to_langflow_json(yaml_path: str) -> Dict[str, Any]:
    """
    Convert YAML workflow file to Langflow JSON.
    
    Args:
        yaml_path: Path to YAML workflow file
        
    Returns:
        Langflow JSON flow definition
    """
    converter = YAMLToLangflowConverter()
    return converter.convert(yaml_path)


def langflow_json_to_yaml(langflow_json: Dict[str, Any]) -> str:
    """
    Convert Langflow JSON back to YAML.
    
    Args:
        langflow_json: Langflow JSON flow definition
        
    Returns:
        YAML string
    """
    converter = LangflowToYAMLConverter()
    return converter.convert(langflow_json)


def export_yaml_to_langflow(yaml_path: str, langflow_url: str = "http://localhost:7860") -> str:
    """
    Convert YAML to Langflow JSON and upload to running Langflow instance.
    
    Args:
        yaml_path: Path to YAML workflow file
        langflow_url: URL of running Langflow server
        
    Returns:
        Flow ID of uploaded flow
    """
    # Convert YAML to Langflow JSON
    flow_json = yaml_to_langflow_json(yaml_path)
    
    # Upload to Langflow
    client = LangflowAPIClient(langflow_url)
    response = client.upload_flow(flow_json)
    
    return response.get("id", response.get("flow_id", ""))


def import_langflow_to_yaml(flow_id: str, output_path: Optional[str] = None, 
                           langflow_url: str = "http://localhost:7860") -> str:
    """
    Download flow from Langflow and convert to YAML.
    
    Args:
        flow_id: UUID of the flow to download
        output_path: Optional path to save YAML (if None, returns string)
        langflow_url: URL of running Langflow server
        
    Returns:
        YAML string (or path if saved to file)
    """
    # Download from Langflow
    client = LangflowAPIClient(langflow_url)
    flow_json = client.download_flow(flow_id)
    
    # Convert to YAML
    yaml_content = langflow_json_to_yaml(flow_json)
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(yaml_content)
        return output_path
    
    return yaml_content