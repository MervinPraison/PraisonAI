"""
n8n Integration Handler for PraisonAI CLI.

Converts PraisonAI agents.yaml workflows to n8n workflow JSON format
and opens them in the n8n UI.

Usage:
    praisonai agents.yaml --n8n
    praisonai agents.yaml --n8n --n8n-url http://localhost:5678
"""

import json
import yaml
import webbrowser
import hashlib
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from .base import FlagHandler


class N8nHandler(FlagHandler):
    """
    Handler for n8n workflow export and visualization.
    
    Converts PraisonAI YAML workflows to n8n-compatible JSON format
    and opens them in the n8n UI for visual editing.
    """
    
    def __init__(self, verbose: bool = False, n8n_url: str = "http://localhost:5678",
                 use_execute_command: bool = True):
        """
        Initialize the n8n handler.
        
        Args:
            verbose: Enable verbose output
            n8n_url: Base URL of the n8n instance
            use_execute_command: Use Execute Command nodes (runs praisonai directly)
                                 instead of HTTP Request nodes
        """
        super().__init__(verbose=verbose)
        self.n8n_url = n8n_url
        self.praisonai_api_url = "http://localhost:8000"
        self.use_execute_command = use_execute_command
    
    @property
    def feature_name(self) -> str:
        return "n8n"
    
    @property
    def flag_name(self) -> str:
        return "n8n"
    
    @property
    def flag_help(self) -> str:
        return "Export workflow to n8n and open in browser"
    
    def execute(self, yaml_path: str, n8n_url: Optional[str] = None, 
                open_browser: bool = True, **kwargs) -> Dict[str, Any]:
        """
        Execute the n8n export workflow.
        
        Args:
            yaml_path: Path to the agents.yaml file
            n8n_url: Optional custom n8n URL
            open_browser: Whether to open the workflow in browser
            
        Returns:
            Dictionary with workflow JSON and URL
        """
        if n8n_url:
            self.n8n_url = n8n_url
        
        # Convert YAML to n8n workflow JSON
        workflow_json = self.convert_yaml_to_n8n(yaml_path)
        
        # Save workflow JSON to file
        output_path = self._save_workflow_json(workflow_json, yaml_path)
        
        self.print_status("✅ Workflow converted successfully!", "success")
        self.print_status(f"📄 JSON saved to: {output_path}", "info")
        
        # Try to create workflow via n8n API
        api_key = os.environ.get('N8N_API_KEY')
        workflow_id = None
        
        if api_key and REQUESTS_AVAILABLE:
            workflow_id = self._create_workflow_via_api(workflow_json, api_key)
        
        if workflow_id:
            # Successfully created via API - open directly
            url = f"{self.n8n_url}/workflow/{workflow_id}"
            self.print_status("🚀 Workflow created in n8n!", "success")
            
            if open_browser:
                self.open_in_browser(url)
                self.print_status(f"🌐 Opening: {url}", "info")
        else:
            # Fallback to manual import instructions
            url = self.generate_n8n_url(workflow_json, self.n8n_url)
            
            if not api_key:
                self.print_status("", "info")
                self.print_status("💡 Tip: Set N8N_API_KEY env var for auto-import", "info")
                self.print_status("   Generate API key in n8n: Settings → API", "info")
            
            self.print_status("", "info")
            self.print_status("📋 To import into n8n:", "info")
            self.print_status("   1. Open n8n in your browser", "info")
            self.print_status("   2. Click the three dots menu (⋮) in the top right", "info")
            self.print_status("   3. Select 'Import from File'", "info")
            self.print_status(f"   4. Choose: {output_path}", "info")
            
            if open_browser:
                self.open_in_browser(url)
                self.print_status(f"🌐 Opening n8n: {url}", "info")
        
        return {
            "workflow": workflow_json,
            "url": url,
            "output_path": output_path,
            "workflow_id": workflow_id
        }
    
    def _create_workflow_via_api(self, workflow_json: Dict[str, Any], 
                                  api_key: str) -> Optional[str]:
        """
        Create workflow in n8n via REST API.
        
        Args:
            workflow_json: The n8n workflow JSON
            api_key: n8n API key
            
        Returns:
            Workflow ID if successful, None otherwise
        """
        if not REQUESTS_AVAILABLE:
            return None
        
        try:
            # Only include fields allowed by n8n API schema
            # See: n8n/packages/cli/src/public-api/v1/handlers/workflows/spec/schemas/workflow.yml
            workflow_data = {
                "name": workflow_json.get("name", "PraisonAI Workflow"),
                "nodes": workflow_json.get("nodes", []),
                "connections": workflow_json.get("connections", {}),
                "settings": workflow_json.get("settings", {"executionOrder": "v1"}),
            }
            
            # Optional fields
            if "staticData" in workflow_json:
                workflow_data["staticData"] = workflow_json["staticData"]
            
            response = requests.post(
                f"{self.n8n_url}/api/v1/workflows",
                headers={
                    "X-N8N-API-KEY": api_key,
                    "Content-Type": "application/json"
                },
                json=workflow_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('id')
            else:
                self.log(f"API error: {response.status_code} - {response.text}", "warning")
                return None
                
        except Exception as e:
            self.log(f"Failed to create workflow via API: {e}", "warning")
            return None
    
    def convert_yaml_to_n8n(self, yaml_path: str) -> Dict[str, Any]:
        """
        Convert a PraisonAI YAML workflow to n8n JSON format.
        
        Args:
            yaml_path: Path to the agents.yaml file
            
        Returns:
            n8n workflow JSON as dictionary
        """
        # Load YAML file
        with open(yaml_path, 'r') as f:
            yaml_content = yaml.safe_load(f)
        
        # Extract workflow metadata
        workflow_name = yaml_content.get('name', 'PraisonAI Workflow')
        description = yaml_content.get('description', '')
        
        # Get agents and steps
        agents = yaml_content.get('agents', yaml_content.get('roles', {}))
        steps = yaml_content.get('steps', [])
        
        # If no steps defined, create steps from agents
        if not steps and agents:
            steps = self._create_steps_from_agents(agents)
        
        # Build n8n nodes and connections
        nodes = []
        connections = {}
        
        # Add manual trigger node
        trigger_node = self._create_trigger_node()
        nodes.append(trigger_node)
        
        # Track previous node for connections
        prev_node_name = trigger_node["name"]
        
        # Process each step
        x_position = 450  # Start position after trigger
        
        for i, step in enumerate(steps):
            if isinstance(step, dict):
                if 'parallel' in step:
                    # Handle parallel steps
                    parallel_nodes, parallel_connections = self._create_parallel_nodes(
                        step['parallel'], x_position, agents
                    )
                    nodes.extend(parallel_nodes)
                    connections.update(parallel_connections)
                    
                    # Connect previous node to first parallel node
                    if prev_node_name not in connections:
                        connections[prev_node_name] = {"main": [[]]}
                    for pnode in parallel_nodes:
                        connections[prev_node_name]["main"][0].append({
                            "node": pnode["name"],
                            "type": "main",
                            "index": 0
                        })
                    
                    x_position += 200 * len(parallel_nodes)
                    prev_node_name = parallel_nodes[-1]["name"] if parallel_nodes else prev_node_name
                    
                elif 'route' in step:
                    # Handle route/decision steps
                    route_node = self._create_route_node(step, x_position, i)
                    nodes.append(route_node)
                    
                    # Connect previous node
                    if prev_node_name not in connections:
                        connections[prev_node_name] = {"main": [[]]}
                    connections[prev_node_name]["main"][0].append({
                        "node": route_node["name"],
                        "type": "main",
                        "index": 0
                    })
                    
                    prev_node_name = route_node["name"]
                    x_position += 200
                    
                else:
                    # Regular agent step
                    agent_id = step.get('agent', '')
                    action = step.get('action', step.get('description', ''))
                    agent_config = agents.get(agent_id, {})
                    
                    agent_node = self._create_agent_node(
                        agent_id=agent_id,
                        agent_config=agent_config,
                        action=action,
                        position=[x_position, 300],
                        index=i
                    )
                    nodes.append(agent_node)
                    
                    # Connect to previous node
                    if prev_node_name not in connections:
                        connections[prev_node_name] = {"main": [[]]}
                    connections[prev_node_name]["main"][0].append({
                        "node": agent_node["name"],
                        "type": "main",
                        "index": 0
                    })
                    
                    prev_node_name = agent_node["name"]
                    x_position += 200
        
        # Build the complete workflow
        # Generate a unique ID based on workflow name
        workflow_id = hashlib.md5(workflow_name.encode()).hexdigest()[:8]
        
        workflow = {
            "id": workflow_id,
            "name": workflow_name,
            "nodes": nodes,
            "connections": connections,
            "active": False,
            "settings": {
                "executionOrder": "v1"
            },
            "versionId": "1",
            "pinData": {},
            "meta": {
                "instanceId": "praisonai-export",
                "templateCredsSetupCompleted": True
            },
            "tags": []
        }
        
        if description:
            workflow["meta"]["description"] = description
        
        return workflow
    
    def _create_steps_from_agents(self, agents: Dict[str, Any]) -> List[Dict]:
        """Create steps from agents when no steps are defined."""
        steps = []
        for agent_id, agent_config in agents.items():
            if isinstance(agent_config, dict):
                # Check for tasks nested in agent
                tasks = agent_config.get('tasks', {})
                if tasks:
                    for task_id, task_config in tasks.items():
                        steps.append({
                            'agent': agent_id,
                            'action': task_config.get('description', task_config.get('action', f'Execute {task_id}'))
                        })
                else:
                    # Create a default step for the agent
                    steps.append({
                        'agent': agent_id,
                        'action': agent_config.get('instructions', agent_config.get('goal', f'Execute {agent_id}'))
                    })
        return steps
    
    def _create_trigger_node(self) -> Dict[str, Any]:
        """Create a manual trigger node."""
        return {
            "id": "trigger",
            "name": "Manual Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [250, 300],
            "parameters": {}
        }
    
    def _create_agent_node(self, agent_id: str, agent_config: Dict,
                            action: str, position: List[int], 
                            index: int) -> Dict[str, Any]:
        """Create a node for an agent - either Execute Command or HTTP Request."""
        if self.use_execute_command:
            return self._create_execute_command_node(
                agent_id, agent_config, action, position, index
            )
        else:
            return self._create_http_request_node(
                agent_id, agent_config, action, position, index
            )
    
    def _create_execute_command_node(self, agent_id: str, agent_config: Dict,
                                      action: str, position: List[int],
                                      index: int) -> Dict[str, Any]:
        """Create an Execute Command node that runs praisonai directly."""
        agent_name = agent_config.get('name', agent_id.title())
        
        # Escape quotes in the action for shell command
        escaped_action = action.replace('"', '\\"').replace("'", "\\'")
        
        # Build the praisonai command
        # Uses the input from previous node if available
        command = f'praisonai "{escaped_action}"'
        
        return {
            "id": f"agent_{index}",
            "name": agent_name,
            "type": "n8n-nodes-base.executeCommand",
            "typeVersion": 1,
            "position": position,
            "parameters": {
                "command": command,
                "executeOnce": True
            }
        }
    
    def _create_http_request_node(self, agent_id: str, agent_config: Dict,
                                   action: str, position: List[int], 
                                   index: int) -> Dict[str, Any]:
        """Create an HTTP Request node for an agent."""
        agent_name = agent_config.get('name', agent_id.title())
        
        # Build the request body
        request_body = {
            "query": action,
            "agent": agent_id
        }
        
        return {
            "id": f"agent_{index}",
            "name": agent_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": position,
            "parameters": {
                "method": "POST",
                "url": f"{self.praisonai_api_url}/agents",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": json.dumps(request_body),
                "options": {
                    "timeout": 300000  # 5 minute timeout for LLM calls
                }
            }
        }
    
    def _create_parallel_nodes(self, parallel_steps: List[Dict], 
                                x_position: int,
                                agents: Dict[str, Any]) -> tuple:
        """Create nodes for parallel execution."""
        nodes = []
        connections = {}
        
        for i, step in enumerate(parallel_steps):
            agent_id = step.get('agent', '')
            action = step.get('action', step.get('description', ''))
            agent_config = agents.get(agent_id, {})
            
            node = self._create_agent_node(
                agent_id=agent_id,
                agent_config=agent_config,
                action=action,
                position=[x_position + (i * 200), 300 + (i * 100)],
                index=100 + i  # Offset index for parallel nodes
            )
            nodes.append(node)
        
        return nodes, connections
    
    def _create_route_node(self, step: Dict, x_position: int, 
                           index: int) -> Dict[str, Any]:
        """Create an IF node for routing decisions."""
        route_config = step.get('route', {})
        conditions = list(route_config.keys())
        
        return {
            "id": f"route_{index}",
            "name": f"Route Decision {index}",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [x_position, 300],
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": f"condition_{i}",
                            "leftValue": "={{ $json.result }}",
                            "rightValue": condition,
                            "operator": {
                                "type": "string",
                                "operation": "contains"
                            }
                        }
                        for i, condition in enumerate(conditions) if condition != 'default'
                    ]
                }
            }
        }
    
    def generate_n8n_url(self, workflow_json: Dict[str, Any], 
                         base_url: str) -> str:
        """
        Generate a URL to open n8n workflow editor.
        
        Note: n8n doesn't support URL hash-based import. Users need to:
        1. Open n8n
        2. Use "Import from File" to load the saved JSON
        
        Args:
            workflow_json: The n8n workflow JSON (unused, kept for API compatibility)
            base_url: Base URL of the n8n instance
            
        Returns:
            URL to open n8n workflow editor
        """
        # n8n doesn't support URL-based workflow import via hash
        # Return the new workflow URL - user will need to import manually
        return f"{base_url}/workflow/new"
    
    def open_in_browser(self, url: str) -> None:
        """
        Open a URL in the default web browser.
        
        Args:
            url: URL to open
        """
        try:
            webbrowser.open(url)
        except Exception as e:
            self.print_status(f"Could not open browser: {e}", "warning")
            self.print_status(f"Please open this URL manually: {url}", "info")
    
    def _save_workflow_json(self, workflow_json: Dict[str, Any], 
                            yaml_path: str) -> str:
        """
        Save the workflow JSON to a file.
        
        Args:
            workflow_json: The n8n workflow JSON
            yaml_path: Original YAML file path
            
        Returns:
            Path to the saved JSON file
        """
        # Create output path based on input YAML
        yaml_file = Path(yaml_path)
        output_path = yaml_file.parent / f"{yaml_file.stem}_n8n.json"
        
        with open(output_path, 'w') as f:
            json.dump(workflow_json, f, indent=2)
        
        return str(output_path)
    
    def get_workflow_json_for_clipboard(self, yaml_path: str) -> str:
        """
        Get the workflow JSON as a string for clipboard copy.
        
        Args:
            yaml_path: Path to the agents.yaml file
            
        Returns:
            JSON string ready for clipboard
        """
        workflow_json = self.convert_yaml_to_n8n(yaml_path)
        return json.dumps(workflow_json, indent=2)
