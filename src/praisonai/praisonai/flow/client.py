"""Langflow REST API Client.

Provides high-level interface for interacting with Langflow server via REST API.
Handles flow upload, download, execution, and management operations.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import requests
except ImportError:
    requests = None


class LangflowClient:
    """High-level client for Langflow REST API operations."""
    
    def __init__(self, base_url: str = "http://localhost:7860", api_key: Optional[str] = None):
        """
        Initialize Langflow client.
        
        Args:
            base_url: Base URL of Langflow server
            api_key: Optional API key for authenticated requests
        """
        if not requests:
            raise ImportError("requests is required for Langflow operations. Install with: pip install requests")
        
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        
        # Set API key header if provided
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"
        
        # Set default headers
        self.session.headers["Content-Type"] = "application/json"
        self.session.headers["User-Agent"] = "PraisonAI/1.0"
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check Langflow server health and get version info.
        
        Returns:
            Health status and server information
        """
        try:
            # Try v1 API first
            response = self.session.get(f"{self.base_url}/api/v1/health", timeout=10)
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "version": "v1",
                    "url": self.base_url,
                    "data": response.json()
                }
        except requests.RequestException:
            pass
        
        try:
            # Fallback: try root endpoint
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                return {
                    "status": "healthy", 
                    "version": "unknown",
                    "url": self.base_url,
                    "data": response.json()
                }
        except requests.RequestException:
            pass
        
        return {
            "status": "unhealthy",
            "version": None,
            "url": self.base_url,
            "error": "Unable to connect to Langflow server"
        }
    
    def list_flows(self) -> List[Dict[str, Any]]:
        """
        List all flows in Langflow.
        
        Returns:
            List of flow metadata
        """
        url = f"{self.base_url}/api/v1/flows/"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "flows" in data:
                return data["flows"]
            else:
                return []
                
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to list flows: {e}")
    
    def get_flow(self, flow_id: str) -> Dict[str, Any]:
        """
        Get flow details by ID.
        
        Args:
            flow_id: UUID of the flow
            
        Returns:
            Flow metadata and definition
        """
        url = f"{self.base_url}/api/v1/flows/{flow_id}"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to get flow {flow_id}: {e}")
    
    def upload_flow(self, flow_data: Dict[str, Any], name: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload a new flow to Langflow.
        
        Args:
            flow_data: Langflow JSON flow definition
            name: Optional flow name (overrides name in flow_data)
            
        Returns:
            Upload response with flow ID
        """
        # Prepare flow data
        flow_payload = flow_data.copy()
        if name:
            flow_payload["name"] = name
        
        # Ensure required fields
        if "name" not in flow_payload:
            flow_payload["name"] = "Imported Flow"
        
        url = f"{self.base_url}/api/v1/flows/upload/"
        
        try:
            response = self.session.post(url, json=flow_payload, timeout=60)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to upload flow: {e}")
    
    def update_flow(self, flow_id: str, flow_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing flow.
        
        Args:
            flow_id: UUID of the flow to update
            flow_data: Updated flow definition
            
        Returns:
            Update response
        """
        url = f"{self.base_url}/api/v1/flows/{flow_id}"
        
        try:
            response = self.session.patch(url, json=flow_data, timeout=60)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to update flow {flow_id}: {e}")
    
    def delete_flow(self, flow_id: str) -> Dict[str, Any]:
        """
        Delete a flow.
        
        Args:
            flow_id: UUID of the flow to delete
            
        Returns:
            Delete response
        """
        url = f"{self.base_url}/api/v1/flows/{flow_id}"
        
        try:
            response = self.session.delete(url, timeout=30)
            response.raise_for_status()
            return {"success": True, "message": f"Flow {flow_id} deleted"}
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to delete flow {flow_id}: {e}")
    
    def run_flow(self, flow_id: str, input_data: Dict[str, Any], 
                 session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a flow with input data.
        
        Args:
            flow_id: UUID of the flow to run
            input_data: Input data for the flow
            session_id: Optional session ID for conversation tracking
            
        Returns:
            Execution result
        """
        url = f"{self.base_url}/api/v1/flows/{flow_id}/run"
        
        # Prepare payload
        payload = {
            "input_value": input_data.get("input_value", input_data.get("message", "")),
            "output_type": "chat",
        }
        
        if session_id:
            payload["session_id"] = session_id
        
        try:
            response = self.session.post(url, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to run flow {flow_id}: {e}")
    
    def get_flow_status(self, flow_id: str) -> Dict[str, Any]:
        """
        Get flow execution status.
        
        Args:
            flow_id: UUID of the flow
            
        Returns:
            Status information
        """
        url = f"{self.base_url}/api/v1/flows/{flow_id}/status"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            # Status endpoint might not exist in all versions
            return {"status": "unknown", "error": str(e)}
    
    def export_flow(self, flow_id: str, output_path: Optional[Union[str, Path]] = None) -> Union[str, Dict]:
        """
        Export flow to file or return as dict.
        
        Args:
            flow_id: UUID of the flow to export
            output_path: Optional path to save flow JSON
            
        Returns:
            Flow JSON dict (if no output_path) or file path (if saved)
        """
        flow_data = self.get_flow(flow_id)
        
        if output_path:
            output_path = Path(output_path)
            
            # Ensure .json extension
            if not output_path.suffix:
                output_path = output_path.with_suffix('.json')
            
            # Create parent directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write flow data
            with open(output_path, 'w') as f:
                json.dump(flow_data, f, indent=2)
            
            return str(output_path)
        
        return flow_data
    
    def import_flow(self, input_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Import flow from file.
        
        Args:
            input_path: Path to flow JSON file
            
        Returns:
            Upload response with flow ID
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Flow file not found: {input_path}")
        
        with open(input_path, 'r') as f:
            flow_data = json.load(f)
        
        return self.upload_flow(flow_data)
    
    def wait_for_server(self, timeout: int = 60, check_interval: int = 2) -> bool:
        """
        Wait for Langflow server to become available.
        
        Args:
            timeout: Maximum time to wait in seconds
            check_interval: Time between health checks in seconds
            
        Returns:
            True if server becomes healthy, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            health = self.health_check()
            if health["status"] == "healthy":
                return True
            
            time.sleep(check_interval)
        
        return False
    
    def search_flows(self, query: str) -> List[Dict[str, Any]]:
        """
        Search flows by name or description.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching flows
        """
        flows = self.list_flows()
        
        # Simple text search
        query_lower = query.lower()
        matching_flows = []
        
        for flow in flows:
            name = flow.get("name", "").lower()
            description = flow.get("description", "").lower()
            
            if query_lower in name or query_lower in description:
                matching_flows.append(flow)
        
        return matching_flows
    
    def clone_flow(self, flow_id: str, new_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Clone an existing flow.
        
        Args:
            flow_id: UUID of the flow to clone
            new_name: Name for the cloned flow
            
        Returns:
            Upload response for cloned flow
        """
        # Get original flow
        flow_data = self.get_flow(flow_id)
        
        # Modify for cloning
        flow_data.pop("id", None)  # Remove ID so it gets a new one
        
        if new_name:
            flow_data["name"] = new_name
        elif "name" in flow_data:
            flow_data["name"] = f"{flow_data['name']} (Copy)"
        
        # Upload as new flow
        return self.upload_flow(flow_data)
    
    def get_flow_logs(self, flow_id: str) -> Dict[str, Any]:
        """
        Get execution logs for a flow.
        
        Args:
            flow_id: UUID of the flow
            
        Returns:
            Log data
        """
        url = f"{self.base_url}/api/v1/flows/{flow_id}/logs"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            # Logs endpoint might not exist in all versions
            return {"logs": [], "error": str(e)}


def create_client(base_url: str = "http://localhost:7860", api_key: Optional[str] = None) -> LangflowClient:
    """
    Create a Langflow client instance.
    
    Args:
        base_url: Base URL of Langflow server
        api_key: Optional API key for authentication
        
    Returns:
        Configured LangflowClient instance
    """
    return LangflowClient(base_url, api_key)


# Convenience functions
def upload_flow_from_file(file_path: Union[str, Path], 
                         base_url: str = "http://localhost:7860",
                         api_key: Optional[str] = None) -> str:
    """
    Upload flow from JSON file to Langflow.
    
    Args:
        file_path: Path to flow JSON file
        base_url: Langflow server URL
        api_key: Optional API key
        
    Returns:
        Flow ID of uploaded flow
    """
    client = create_client(base_url, api_key)
    response = client.import_flow(file_path)
    return response.get("id", response.get("flow_id", ""))


def download_flow_to_file(flow_id: str, output_path: Union[str, Path],
                         base_url: str = "http://localhost:7860",
                         api_key: Optional[str] = None) -> str:
    """
    Download flow from Langflow and save to file.
    
    Args:
        flow_id: UUID of flow to download
        output_path: Path to save flow JSON
        base_url: Langflow server URL
        api_key: Optional API key
        
    Returns:
        Path to saved file
    """
    client = create_client(base_url, api_key)
    return client.export_flow(flow_id, output_path)