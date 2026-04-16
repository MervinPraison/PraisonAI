"""
Workflow Preview Functionality

Handles opening workflows in n8n visual editor for preview and editing.
"""

from typing import Optional
import webbrowser
import logging
from pathlib import Path

from .converter import YAMLToN8nConverter
from .client import N8nClient

logger = logging.getLogger(__name__)

def preview_workflow(
    yaml_path: str, 
    n8n_url: str = "http://localhost:5678",
    api_key: Optional[str] = None,
    auto_open: bool = True
) -> str:
    """Open workflow in n8n visual editor.
    
    Args:
        yaml_path: Path to YAML workflow file
        n8n_url: n8n instance URL
        api_key: n8n API key (optional, can use env var)
        auto_open: Whether to automatically open browser
        
    Returns:
        URL to the workflow in n8n editor
        
    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ConnectionError: If can't connect to n8n
        ValueError: If YAML is invalid
    """
    logger.info(f"Previewing workflow: {yaml_path}")
    
    # Validate file exists
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        raise FileNotFoundError(f"Workflow file not found: {yaml_path}")
    
    # Load and parse YAML
    try:
        import yaml as yaml_lib
        with open(yaml_file, 'r') as f:
            yaml_content = yaml_lib.safe_load(f)
        if not isinstance(yaml_content, dict):
            raise ValueError("Workflow YAML must deserialize to a mapping")
    except Exception as e:
        raise ValueError(f"Failed to parse YAML workflow: {e}")
    
    # Convert to n8n format
    converter = YAMLToN8nConverter()
    n8n_json = converter.convert(yaml_content)
    
    # Create n8n client
    client = N8nClient(base_url=n8n_url, api_key=api_key)
    
    # Test connection first
    if not client.test_connection():
        raise ConnectionError(
            f"Cannot connect to n8n at {n8n_url}. "
            "Please ensure n8n is running and accessible."
        )
    
    try:
        # Create workflow in n8n
        response = client.create_workflow(n8n_json)
        workflow_id = response.get("id")
        
        if not workflow_id:
            raise ValueError("Failed to create workflow - no ID returned")
        
        # Generate editor URL
        editor_url = f"{n8n_url}/workflow/{workflow_id}"
        
        logger.info(f"Created workflow in n8n with ID: {workflow_id}")
        
        # Open browser if requested
        if auto_open:
            try:
                webbrowser.open(editor_url)
                logger.info(f"Opened browser to: {editor_url}")
            except Exception as e:
                logger.warning(f"Failed to open browser: {e}")
        
        return editor_url
        
    finally:
        client.close()

def export_from_n8n(
    workflow_id: str,
    output_path: str,
    n8n_url: str = "http://localhost:5678",
    api_key: Optional[str] = None
) -> None:
    """Export workflow from n8n back to YAML format.
    
    Args:
        workflow_id: n8n workflow ID
        output_path: Path where to save YAML file
        n8n_url: n8n instance URL
        api_key: n8n API key (optional, can use env var)
        
    Raises:
        ConnectionError: If can't connect to n8n
        ValueError: If workflow not found or conversion fails
    """
    from .reverse_converter import N8nToYAMLConverter
    
    logger.info(f"Exporting workflow {workflow_id} to {output_path}")
    
    # Create n8n client
    client = N8nClient(base_url=n8n_url, api_key=api_key)
    
    # Test connection
    if not client.test_connection():
        raise ConnectionError(
            f"Cannot connect to n8n at {n8n_url}. "
            "Please ensure n8n is running and accessible."
        )
    
    try:
        # Get workflow from n8n
        n8n_workflow = client.get_workflow(workflow_id)
        
        # Convert back to YAML format
        converter = N8nToYAMLConverter()
        yaml_workflow = converter.convert(n8n_workflow)
        
        # Write to file
        import yaml as yaml_lib
        with open(output_path, 'w') as f:
            yaml_lib.dump(yaml_workflow, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Exported workflow to: {output_path}")
        
    finally:
        client.close()

def sync_workflow(
    yaml_path: str,
    workflow_id: str,
    n8n_url: str = "http://localhost:5678", 
    api_key: Optional[str] = None
) -> str:
    """Sync YAML workflow with existing n8n workflow.
    
    Args:
        yaml_path: Path to YAML workflow file
        workflow_id: Existing n8n workflow ID to update
        n8n_url: n8n instance URL
        api_key: n8n API key (optional, can use env var)
        
    Returns:
        URL to the updated workflow in n8n editor
        
    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ConnectionError: If can't connect to n8n
        ValueError: If YAML is invalid or workflow not found
    """
    logger.info(f"Syncing workflow {workflow_id} with {yaml_path}")
    
    # Validate file exists
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        raise FileNotFoundError(f"Workflow file not found: {yaml_path}")
    
    # Load and parse YAML
    try:
        import yaml as yaml_lib
        with open(yaml_file, 'r') as f:
            yaml_content = yaml_lib.safe_load(f)
        if not isinstance(yaml_content, dict):
            raise ValueError("Workflow YAML must deserialize to a mapping")
    except Exception as e:
        raise ValueError(f"Failed to parse YAML workflow: {e}")
    
    # Convert to n8n format
    converter = YAMLToN8nConverter()
    n8n_json = converter.convert(yaml_content)
    
    # Create n8n client
    client = N8nClient(base_url=n8n_url, api_key=api_key)
    
    # Test connection
    if not client.test_connection():
        raise ConnectionError(
            f"Cannot connect to n8n at {n8n_url}. "
            "Please ensure n8n is running and accessible."
        )
    
    try:
        # Update workflow in n8n
        response = client.update_workflow(workflow_id, n8n_json)
        
        # Generate editor URL
        editor_url = f"{n8n_url}/workflow/{workflow_id}"
        
        logger.info(f"Synced workflow {workflow_id}")
        
        return editor_url
        
    finally:
        client.close()