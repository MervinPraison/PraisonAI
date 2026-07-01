"""
Shared YAML utilities for recipe creation and optimization.

DRY: This module extracts common YAML processing functions used by both
recipe_creator.py and recipe_optimizer.py to avoid duplication.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_litellm():
    """
    Lazy import litellm.
    
    Returns:
        The litellm module
        
    Raises:
        ImportError: If litellm is not installed
    """
    try:
        import litellm
        return litellm
    except ImportError:
        raise ImportError(
            "litellm is required for recipe operations. "
            "Install with: pip install litellm"
        )


def fix_variable_format(yaml_content: str) -> str:
    """
    Fix common variable format issues in YAML content.
    
    Converts incorrect formats like {{agent}}_output to {{agent_output}}.
    
    Args:
        yaml_content: YAML content to fix
        
    Returns:
        Fixed YAML content
    """
    # Fix {{agent}}_output -> {{agent_output}}
    # This is the most common LLM mistake
    pattern = r'\{\{(\w+)\}\}_output'
    replacement = r'{{\1_output}}'
    yaml_content = re.sub(pattern, replacement, yaml_content)
    
    # Fix common input variable patterns
    input_patterns = [
        (r'\{\{(\w+)\}\}_input', r'{{\1_input}}'),
        (r'\{\{(\w+)\}\}_query', r'{{\1_query}}'),
        (r'\{\{(\w+)\}\}_topic', r'{{\1_topic}}'),
        (r'\{\{(\w+)\}\}_file_path', r'{{\1_file_path}}'),
        (r'\{\{(\w+)\}\}_data', r'{{\1_data}}'),
        (r'\{\{(\w+)\}\}_content', r'{{\1_content}}'),
        (r'\{\{(\w+)\}\}_text', r'{{\1_text}}'),
    ]
    
    for pattern, replacement in input_patterns:
        yaml_content = re.sub(pattern, replacement, yaml_content)
    
    # Fix agent reference patterns
    # "from {{agent}}" -> "from {{agent_output}}"
    yaml_content = re.sub(
        r'from \{\{(\w+)\}\}(?!_)',
        r'from {{\1_output}}',
        yaml_content
    )
    
    # "Using output from {{agent}}" -> "Using {{agent_output}}"
    yaml_content = re.sub(
        r'Using output from \{\{(\w+)\}\}',
        r'Using {{\1_output}}',
        yaml_content
    )
    
    return yaml_content


def validate_yaml_structure(yaml_content: str) -> Tuple[bool, List[str]]:
    """
    Validate YAML structure for PraisonAI recipe requirements.
    
    Args:
        yaml_content: YAML content to validate
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    import yaml
    errors = []
    
    try:
        data = yaml.safe_load(yaml_content)
        if not data:
            errors.append("YAML is empty")
            return False, errors
        
        # Check for required sections
        if 'agents' not in data:
            errors.append("Missing 'agents' section")
        elif not isinstance(data['agents'], dict):
            errors.append("'agents' must be a dictionary")
        else:
            # Validate each agent
            for agent_name, agent_config in data['agents'].items():
                if not isinstance(agent_config, dict):
                    errors.append(f"Agent '{agent_name}' config must be a dictionary")
                    continue
                
                # Check for required agent fields
                if 'role' not in agent_config:
                    errors.append(f"Agent '{agent_name}' missing 'role' field")
                if 'goal' not in agent_config:
                    errors.append(f"Agent '{agent_name}' missing 'goal' field")
                
                # Validate tools is a list if present
                if 'tools' in agent_config and not isinstance(agent_config['tools'], list):
                    errors.append(f"Agent '{agent_name}' tools must be a list")
        
        # Check for steps section
        if 'steps' not in data:
            errors.append("Missing 'steps' section")
        elif not isinstance(data['steps'], list):
            errors.append("'steps' must be a list")
        else:
            # Validate each step
            for i, step in enumerate(data['steps']):
                if not isinstance(step, dict):
                    errors.append(f"Step {i+1} must be a dictionary")
                    continue
                if 'agent' not in step:
                    errors.append(f"Step {i+1} missing 'agent' field")
                if 'action' not in step:
                    errors.append(f"Step {i+1} missing 'action' field")
        
        return len(errors) == 0, errors
        
    except yaml.YAMLError as e:
        errors.append(f"Invalid YAML syntax: {str(e)[:200]}")
        return False, errors


def ensure_hierarchical_preserved(original_yaml: str, new_yaml: str) -> str:
    """
    Ensure hierarchical process fields are preserved after optimization.
    
    If the original YAML had process: hierarchical and manager_llm,
    ensure they are present in the new YAML. If missing, add them.
    
    Args:
        original_yaml: Original YAML content
        new_yaml: New YAML content after optimization
        
    Returns:
        Updated YAML with hierarchical fields preserved
    """
    import yaml
    
    try:
        original_data = yaml.safe_load(original_yaml)
        new_data = yaml.safe_load(new_yaml)
        
        if not original_data or not new_data:
            return new_yaml
        
        # Check if original had hierarchical process
        original_process = original_data.get('process')
        original_manager_llm = original_data.get('manager_llm')
        
        modified = False
        
        # Preserve process field
        if original_process == 'hierarchical':
            if new_data.get('process') != 'hierarchical':
                new_data['process'] = 'hierarchical'
                modified = True
                logger.info("Restored process: hierarchical (was removed by LLM)")
        
        # Preserve manager_llm field
        if original_manager_llm:
            if not new_data.get('manager_llm'):
                new_data['manager_llm'] = original_manager_llm
                modified = True
                logger.info(f"Restored manager_llm: {original_manager_llm} (was removed by LLM)")
        
        if modified:
            # Rebuild YAML with proper ordering
            return rebuild_yaml_with_order(new_data)
        
        return new_yaml
        
    except Exception as e:
        logger.debug(f"Could not validate hierarchical preservation: {e}")
        return new_yaml


def rebuild_yaml_with_order(data: Dict[str, Any]) -> str:
    """
    Rebuild YAML with proper field ordering.
    
    Ensures metadata, process, manager_llm come before agents and steps.
    
    Args:
        data: YAML data dictionary
        
    Returns:
        YAML string with proper ordering
    """
    import yaml
    
    # Define field order
    field_order = [
        'name',
        'description',
        'version',
        'process',
        'manager_llm',
        'agents',
        'steps',
    ]
    
    # Build ordered dict
    ordered_data = {}
    
    # Add fields in order
    for field in field_order:
        if field in data:
            ordered_data[field] = data[field]
    
    # Add any remaining fields
    for key, value in data.items():
        if key not in ordered_data:
            ordered_data[key] = value
    
    return yaml.dump(ordered_data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def extract_yaml_from_response(response: str) -> Optional[str]:
    """
    Extract YAML content from LLM response.
    
    Handles various formats:
    - ```yaml ... ```
    - ``` ... ```
    - Raw YAML
    
    Args:
        response: LLM response text
        
    Returns:
        Extracted YAML content or None
    """
    # Try to extract from code blocks
    yaml_patterns = [
        r'```yaml\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
    ]
    
    for pattern in yaml_patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    # Check if response looks like raw YAML
    if response.strip().startswith('agents:') or response.strip().startswith('name:'):
        return response.strip()
    
    return None


def add_tool_choice_required(yaml_content: str) -> str:
    """
    Add tool_choice: required to agents that have tools.
    
    Args:
        yaml_content: YAML content
        
    Returns:
        Updated YAML content
    """
    import yaml
    
    try:
        data = yaml.safe_load(yaml_content)
        if not data or 'agents' not in data:
            return yaml_content
        
        modified = False
        for agent_name, agent_config in data['agents'].items():
            if isinstance(agent_config, dict):
                tools = agent_config.get('tools', [])
                if tools and 'tool_choice' not in agent_config:
                    agent_config['tool_choice'] = 'required'
                    modified = True
                    logger.debug(f"Added tool_choice: required to agent '{agent_name}'")
        
        if modified:
            return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        return yaml_content
        
    except Exception as e:
        logger.debug(f"Could not add tool_choice: {e}")
        return yaml_content


__all__ = [
    'get_litellm',
    'fix_variable_format',
    'validate_yaml_structure',
    'ensure_hierarchical_preserved',
    'rebuild_yaml_with_order',
    'extract_yaml_from_response',
    'add_tool_choice_required',
]
