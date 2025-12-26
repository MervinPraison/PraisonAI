"""
YAML schema validation for deploy configurations.
"""
import yaml
from pathlib import Path
from typing import Optional
from .models import DeployConfig, DeployType, CloudProvider, APIConfig, DockerConfig, CloudConfig


def validate_agents_yaml(file_path: str) -> Optional[DeployConfig]:
    """
    Validate agents.yaml file and extract deploy configuration.
    
    Args:
        file_path: Path to agents.yaml file
        
    Returns:
        DeployConfig if deploy section exists, None otherwise
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If deploy config is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    
    if not data or 'deploy' not in data:
        return None
    
    deploy_data = data['deploy']
    
    # Parse deploy type
    deploy_type_str = deploy_data.get('type')
    if not deploy_type_str:
        raise ValueError("Deploy type is required")
    
    try:
        deploy_type = DeployType(deploy_type_str)
    except ValueError:
        raise ValueError(f"Invalid deploy type: {deploy_type_str}. Must be one of: api, docker, cloud")
    
    # Build config based on type
    config_dict = {'type': deploy_type}
    
    if deploy_type == DeployType.API:
        api_data = deploy_data.get('api', {})
        config_dict['api'] = APIConfig(**api_data) if api_data else APIConfig()
    
    elif deploy_type == DeployType.DOCKER:
        docker_data = deploy_data.get('docker', {})
        config_dict['docker'] = DockerConfig(**docker_data) if docker_data else DockerConfig()
    
    elif deploy_type == DeployType.CLOUD:
        cloud_data = deploy_data.get('cloud', {})
        if not cloud_data:
            raise ValueError("Cloud configuration is required for cloud deployment type")
        
        # Parse provider
        provider_str = cloud_data.get('provider')
        if not provider_str:
            raise ValueError("Cloud provider is required")
        
        try:
            cloud_data['provider'] = CloudProvider(provider_str)
        except ValueError:
            raise ValueError(f"Invalid cloud provider: {provider_str}. Must be one of: aws, azure, gcp")
        
        config_dict['cloud'] = CloudConfig(**cloud_data)
    
    # Parse agents if present
    if 'agents' in deploy_data:
        config_dict['agents'] = deploy_data['agents']
    
    return DeployConfig(**config_dict)


def generate_sample_yaml(deploy_type: DeployType, provider: Optional[CloudProvider] = None) -> str:
    """
    Generate sample agents.yaml with deploy configuration.
    
    Args:
        deploy_type: Type of deployment
        provider: Cloud provider (required if deploy_type is CLOUD)
        
    Returns:
        YAML string with sample configuration
    """
    base_yaml = """name: Sample Agent
description: Sample agent configuration with deploy settings
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users with tasks
    backstory: Experienced assistant ready to help
    instructions: |
      Provide helpful responses to user queries.
      Be concise and accurate.

"""
    
    if deploy_type == DeployType.API:
        deploy_yaml = """deploy:
  type: api
  api:
    host: 0.0.0.0
    port: 8005
    workers: 1
    cors_enabled: true
    auth_enabled: false
"""
    
    elif deploy_type == DeployType.DOCKER:
        deploy_yaml = """deploy:
  type: docker
  docker:
    image_name: praisonai-app
    tag: latest
    base_image: python:3.11-slim
    expose:
      - 8005
    registry: null
    push: false
"""
    
    elif deploy_type == DeployType.CLOUD:
        if provider == CloudProvider.AWS:
            deploy_yaml = """deploy:
  type: cloud
  cloud:
    provider: aws
    region: us-east-1
    service_name: praisonai-service
    cpu: "256"
    memory: "512"
    min_instances: 1
    max_instances: 10
    # image: your-registry/praisonai-app:latest
    # cluster_name: praisonai-cluster
"""
        
        elif provider == CloudProvider.AZURE:
            deploy_yaml = """deploy:
  type: cloud
  cloud:
    provider: azure
    region: eastus
    service_name: praisonai-service
    resource_group: praisonai-rg
    subscription_id: your-subscription-id
    cpu: "0.5"
    memory: "1.0"
    min_instances: 1
    max_instances: 10
    # image: your-registry.azurecr.io/praisonai-app:latest
"""
        
        elif provider == CloudProvider.GCP:
            deploy_yaml = """deploy:
  type: cloud
  cloud:
    provider: gcp
    region: us-central1
    service_name: praisonai-service
    project_id: your-project-id
    cpu: "1"
    memory: "512"
    min_instances: 1
    max_instances: 10
    # image: gcr.io/your-project-id/praisonai-app:latest
"""
        else:
            deploy_yaml = """deploy:
  type: cloud
  cloud:
    provider: aws  # or azure, gcp
    region: us-east-1
    service_name: praisonai-service
"""
    
    else:
        deploy_yaml = ""
    
    return base_yaml + deploy_yaml


def save_sample_yaml(file_path: str, deploy_type: DeployType, provider: Optional[CloudProvider] = None):
    """
    Save sample agents.yaml to file.
    
    Args:
        file_path: Path to save the file
        deploy_type: Type of deployment
        provider: Cloud provider (required if deploy_type is CLOUD)
    """
    yaml_content = generate_sample_yaml(deploy_type, provider)
    
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w') as f:
        f.write(yaml_content)
