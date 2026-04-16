"""
n8n API Client

Handles communication with n8n instances for workflow management.
"""

from typing import Dict, Any, Optional, List
import os
import logging

logger = logging.getLogger(__name__)

class N8nClient:
    """Client for interacting with n8n API."""
    
    def __init__(self, base_url: str = "http://localhost:5678", api_key: Optional[str] = None):
        """Initialize n8n client.
        
        Args:
            base_url: n8n instance URL
            api_key: n8n API key (or from N8N_API_KEY env var)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("N8N_API_KEY")
        self.session = None
        
    def _get_session(self):
        """Get HTTP session with lazy loading."""
        if self.session is None:
            try:
                import httpx
                self.session = httpx.Client()
            except ImportError:
                raise ImportError(
                    "httpx is required for n8n API client. "
                    "Install with: pip install 'praisonai[n8n]'"
                )
        return self.session
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["X-N8N-API-KEY"] = self.api_key
            
        return headers
    
    def create_workflow(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new workflow in n8n.
        
        Args:
            workflow_data: n8n workflow JSON data
            
        Returns:
            Created workflow response with ID
        """
        logger.info(f"Creating workflow: {workflow_data.get('name', 'Untitled')}")
        
        session = self._get_session()
        response = session.post(
            f"{self.base_url}/api/v1/workflows",
            json=workflow_data,
            headers=self._get_headers()
        )
        
        response.raise_for_status()
        return response.json()
    
    def update_workflow(self, workflow_id: str, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing workflow in n8n.
        
        Args:
            workflow_id: n8n workflow ID
            workflow_data: Updated workflow JSON data
            
        Returns:
            Updated workflow response
        """
        logger.info(f"Updating workflow: {workflow_id}")
        
        session = self._get_session()
        response = session.put(
            f"{self.base_url}/api/v1/workflows/{workflow_id}",
            json=workflow_data,
            headers=self._get_headers()
        )
        
        response.raise_for_status()
        return response.json()
    
    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Get workflow by ID from n8n.
        
        Args:
            workflow_id: n8n workflow ID
            
        Returns:
            Workflow JSON data
        """
        logger.info(f"Getting workflow: {workflow_id}")
        
        session = self._get_session()
        response = session.get(
            f"{self.base_url}/api/v1/workflows/{workflow_id}",
            headers=self._get_headers()
        )
        
        response.raise_for_status()
        return response.json()
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows in n8n.
        
        Returns:
            List of workflow summaries
        """
        logger.info("Listing workflows")
        
        session = self._get_session()
        response = session.get(
            f"{self.base_url}/api/v1/workflows",
            headers=self._get_headers()
        )
        
        response.raise_for_status()
        result = response.json()
        return result.get("data", [])
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete workflow from n8n.
        
        Args:
            workflow_id: n8n workflow ID
            
        Returns:
            True if successful
        """
        logger.info(f"Deleting workflow: {workflow_id}")
        
        session = self._get_session()
        response = session.delete(
            f"{self.base_url}/api/v1/workflows/{workflow_id}",
            headers=self._get_headers()
        )
        
        response.raise_for_status()
        return True
    
    def execute_workflow(self, workflow_id: str, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a workflow in n8n.
        
        Args:
            workflow_id: n8n workflow ID
            input_data: Input data for workflow execution
            
        Returns:
            Execution response
        """
        logger.info(f"Executing workflow: {workflow_id}")
        
        session = self._get_session()
        
        payload = {}
        if input_data:
            payload["data"] = input_data
            
        response = session.post(
            f"{self.base_url}/api/v1/workflows/{workflow_id}/execute",
            json=payload,
            headers=self._get_headers()
        )
        
        response.raise_for_status()
        return response.json()
    
    def get_execution(self, execution_id: str) -> Dict[str, Any]:
        """Get execution details from n8n.
        
        Args:
            execution_id: n8n execution ID
            
        Returns:
            Execution details
        """
        logger.info(f"Getting execution: {execution_id}")
        
        session = self._get_session()
        response = session.get(
            f"{self.base_url}/api/v1/executions/{execution_id}",
            headers=self._get_headers()
        )
        
        response.raise_for_status()
        return response.json()
    
    def test_connection(self) -> bool:
        """Test connection to n8n instance.
        
        Returns:
            True if connection successful
        """
        try:
            session = self._get_session()
            response = session.get(
                f"{self.base_url}/healthz",
                headers=self._get_headers(),
                timeout=5.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Connection test failed: {e}")
            return False
    
    def close(self):
        """Close HTTP session."""
        if self.session:
            self.session.close()
            self.session = None