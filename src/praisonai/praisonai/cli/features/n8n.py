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
                 use_execute_command: bool = False, api_url: str = "http://127.0.0.1:8005"):
        """
        Initialize the n8n handler.
        
        Args:
            verbose: Enable verbose output
            n8n_url: Base URL of the n8n instance
            use_execute_command: Use Execute Command nodes (runs praisonai directly)
                                 instead of HTTP Request nodes
            api_url: PraisonAI API URL that n8n will call (for tunnel/cloud deployments)
        """
        super().__init__(verbose=verbose)
        self.n8n_url = n8n_url
        self.praisonai_api_url = api_url
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
        
        webhook_url = None
        if workflow_id:
            # Successfully created via API - open directly
            url = f"{self.n8n_url}/workflow/{workflow_id}"
            self.print_status("🚀 Workflow created in n8n!", "success")
            
            # Activate the workflow so webhook is available
            if self._activate_workflow(workflow_id, api_key):
                self.print_status("✅ Workflow activated!", "success")
                
                # Get webhook path from the workflow
                trigger_node = next((n for n in workflow_json["nodes"] 
                                    if n.get("type") == "n8n-nodes-base.webhook"), None)
                if trigger_node:
                    webhook_path = trigger_node["parameters"].get("path", "praisonai")
                    webhook_url = f"{self.n8n_url}/webhook/{webhook_path}"
                    self.print_status("", "info")
                    self.print_status("🔗 Webhook URL (to trigger workflow):", "info")
                    self.print_status(f"   POST {webhook_url}", "info")
            else:
                self.print_status("⚠️  Could not activate workflow (activate manually in n8n)", "warning")
            
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
            "workflow_id": workflow_id,
            "webhook_url": webhook_url
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
    
    def _activate_workflow(self, workflow_id: str, api_key: str) -> bool:
        """
        Activate a workflow via n8n API.
        
        Args:
            workflow_id: The workflow ID to activate
            api_key: n8n API key
            
        Returns:
            True if successful, False otherwise
        """
        if not REQUESTS_AVAILABLE:
            return False
        
        try:
            response = requests.post(
                f"{self.n8n_url}/api/v1/workflows/{workflow_id}/activate",
                headers={
                    "X-N8N-API-KEY": api_key,
                    "Content-Type": "application/json"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return True
            else:
                self.log(f"Activation error: {response.status_code} - {response.text}", "warning")
                return False
                
        except Exception as e:
            self.log(f"Failed to activate workflow: {e}", "warning")
            return False
    
    def convert_yaml_to_n8n(self, yaml_path: str, use_webhook: bool = True) -> Dict[str, Any]:
        """
        Convert a PraisonAI YAML workflow to n8n JSON format.
        
        The n8n workflow will have:
        - A webhook trigger to receive requests
        - One HTTP Request node per agent (calls /agents/{agent_name})
        - Each agent node passes its output to the next agent
        
        Args:
            yaml_path: Path to the agents.yaml file
            use_webhook: Use webhook trigger for programmatic execution (default: True)
            
        Returns:
            n8n workflow JSON as dictionary
        """
        # Load YAML file
        with open(yaml_path, 'r') as f:
            yaml_content = yaml.safe_load(f)
        
        # Extract workflow metadata
        workflow_name = yaml_content.get('name', 'PraisonAI Workflow')
        description = yaml_content.get('description', '')
        
        # Generate a unique webhook path from workflow name
        webhook_path = workflow_name.lower().replace(' ', '-').replace('/', '-')[:50]
        
        # Get agents and steps
        agents = yaml_content.get('agents', yaml_content.get('roles', {}))
        steps = yaml_content.get('steps', [])
        
        # If no steps defined, create steps from agents
        if not steps and agents:
            steps = self._create_steps_from_agents(agents)
        
        # Build n8n nodes and connections
        nodes = []
        connections = {}
        
        # Add trigger node (webhook for programmatic execution, manual otherwise)
        trigger_node = self._create_trigger_node(use_webhook=use_webhook, webhook_path=webhook_path)
        nodes.append(trigger_node)
        
        # Track previous node for connections
        prev_node_name = trigger_node["name"]
        x_position = 450
        
        # Create one HTTP node per agent step
        for i, step in enumerate(steps):
            if isinstance(step, dict):
                agent_id = step.get('agent', '')
                action = step.get('action', step.get('description', ''))
                agent_config = agents.get(agent_id, {})
                
                # Create HTTP node that calls the specific agent endpoint
                agent_node = self._create_per_agent_node(
                    agent_id=agent_id,
                    agent_config=agent_config,
                    action=action,
                    position=[x_position, 300],
                    index=i,
                    is_first=(i == 0)
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
                x_position += 250
        
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
    
    def _create_trigger_node(self, use_webhook: bool = False, 
                              webhook_path: str = "praisonai") -> Dict[str, Any]:
        """Create a trigger node (webhook or manual).
        
        Args:
            use_webhook: If True, creates a webhook trigger for programmatic execution
            webhook_path: Path for the webhook URL (only used if use_webhook=True)
        """
        if use_webhook:
            # Generate a unique webhook ID
            webhook_id = hashlib.md5(webhook_path.encode()).hexdigest()[:16]
            return {
                "id": "trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [250, 300],
                "webhookId": webhook_id,
                "parameters": {
                    "path": webhook_path,
                    "httpMethod": "POST",
                    "responseMode": "lastNode",
                    "options": {}
                }
            }
        return {
            "id": "trigger",
            "name": "Manual Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [250, 300],
            "parameters": {}
        }
    
    def _create_per_agent_node(self, agent_id: str, agent_config: Dict,
                                action: str, position: List[int],
                                index: int, is_first: bool = False) -> Dict[str, Any]:
        """
        Create an HTTP Request node that calls a specific agent endpoint.
        
        Args:
            agent_id: Agent identifier (used in URL path)
            agent_config: Agent configuration from YAML
            action: The action/task description for this agent
            position: Node position [x, y]
            index: Node index
            is_first: Whether this is the first agent (uses webhook input)
            
        Returns:
            n8n HTTP Request node configuration
        """
        agent_name = agent_config.get('name', agent_id.title())
        # Convert agent_id to URL-safe format (lowercase, underscores)
        agent_url_id = agent_id.lower().replace(' ', '_')
        
        # Build the query - first agent uses webhook input, others use previous response
        # Escape single quotes and double braces (n8n expression syntax)
        escaped_action = action.replace("'", "\\'").replace("{{", "").replace("}}", "")
        if is_first:
            # First agent: use query from webhook body
            query_expr = "$json.body?.query || $json.query || '" + escaped_action + "'"
        else:
            # Subsequent agents: use previous agent's response + original action context
            query_expr = "$json.response || '" + escaped_action + "'"
        
        return {
            "id": f"agent_{index}",
            "name": agent_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": position,
            "parameters": {
                "method": "POST",
                "url": f"{self.praisonai_api_url}/agents/{agent_url_id}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": f"={{{{ JSON.stringify({{ query: {query_expr} }}) }}}}",
                "options": {
                    "timeout": 300000  # 5 minute timeout per agent
                }
            },
            "notes": f"Agent: {agent_name}\nTask: {action[:100]}"
        }
    
    def _create_praisonai_workflow_node(self, workflow_name: str,
                                         agent_names: List[str],
                                         position: List[int]) -> Dict[str, Any]:
        """
        Create a single HTTP Request node that triggers the entire PraisonAI workflow.
        
        The PraisonAI API will run all agents sequentially when called.
        
        Args:
            workflow_name: Name of the workflow
            agent_names: List of agent names (for documentation)
            position: Node position [x, y]
            
        Returns:
            n8n HTTP Request node configuration
        """
        # The query will be passed from the webhook trigger
        # Using n8n expression to get the body from the webhook
        return {
            "id": "praisonai_workflow",
            "name": f"PraisonAI: {workflow_name}",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": position,
            "parameters": {
                "method": "POST",
                "url": f"{self.praisonai_api_url}/agents",
                "sendBody": True,
                "specifyBody": "json",
                # Pass the query from webhook body, or use a default
                "jsonBody": "={{ JSON.stringify({ query: $json.body?.query || $json.query || 'Start workflow' }) }}",
                "options": {
                    "timeout": 600000  # 10 minute timeout for full workflow
                }
            },
            "notes": f"Runs agents: {', '.join(agent_names)}"
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
