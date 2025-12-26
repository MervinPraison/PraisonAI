"""
Deploy configuration models using Pydantic.
"""
from enum import Enum
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, field_validator


class DeployType(str, Enum):
    """Deployment type enum."""
    API = "api"
    DOCKER = "docker"
    CLOUD = "cloud"


class CloudProvider(str, Enum):
    """Cloud provider enum."""
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class APIConfig(BaseModel):
    """Configuration for API server deployment."""
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8005, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")
    cors_enabled: bool = Field(default=True, description="Enable CORS")
    auth_enabled: bool = Field(default=False, description="Enable authentication")
    auth_token: Optional[str] = Field(default=None, description="Authentication token")
    reload: bool = Field(default=False, description="Enable auto-reload for development")


class DockerConfig(BaseModel):
    """Configuration for Docker deployment."""
    image_name: str = Field(default="praisonai-app", description="Docker image name")
    tag: str = Field(default="latest", description="Docker image tag")
    base_image: str = Field(default="python:3.11-slim", description="Base Docker image")
    expose: List[int] = Field(default=[8005], description="Ports to expose")
    registry: Optional[str] = Field(default=None, description="Docker registry URL")
    push: bool = Field(default=False, description="Push image to registry after build")
    build_args: Optional[Dict[str, str]] = Field(default=None, description="Docker build arguments")


class CloudConfig(BaseModel):
    """Configuration for cloud deployment."""
    provider: CloudProvider = Field(..., description="Cloud provider")
    region: str = Field(..., description="Deployment region")
    service_name: str = Field(..., description="Service/application name")
    
    # Common cloud config
    image: Optional[str] = Field(default=None, description="Container image URL")
    cpu: Optional[str] = Field(default="256", description="CPU allocation")
    memory: Optional[str] = Field(default="512", description="Memory allocation (MB)")
    min_instances: int = Field(default=1, description="Minimum instances")
    max_instances: int = Field(default=10, description="Maximum instances")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables")
    
    # AWS-specific
    cluster_name: Optional[str] = Field(default=None, description="ECS cluster name (AWS)")
    task_definition: Optional[str] = Field(default=None, description="Task definition (AWS)")
    
    # Azure-specific
    resource_group: Optional[str] = Field(default=None, description="Resource group (Azure)")
    subscription_id: Optional[str] = Field(default=None, description="Subscription ID (Azure)")
    
    # GCP-specific
    project_id: Optional[str] = Field(default=None, description="Project ID (GCP)")


class AgentConfig(BaseModel):
    """Configuration for an agent to deploy."""
    name: str = Field(..., description="Agent name/identifier")
    entrypoint: str = Field(..., description="Agent entrypoint file (e.g., agents.yaml)")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    secrets: Dict[str, str] = Field(default_factory=dict, description="Secret references")
    ports: Optional[List[int]] = Field(default=None, description="Ports to expose")
    resources: Optional[Dict[str, str]] = Field(default=None, description="Resource requirements")


class DeployConfig(BaseModel):
    """Main deployment configuration."""
    type: DeployType = Field(..., description="Deployment type")
    api: Optional[APIConfig] = Field(default=None, description="API server configuration")
    docker: Optional[DockerConfig] = Field(default=None, description="Docker configuration")
    cloud: Optional[CloudConfig] = Field(default=None, description="Cloud configuration")
    agents: Optional[List[AgentConfig]] = Field(default=None, description="Agent configurations")
    
    @field_validator('api', 'docker', 'cloud')
    @classmethod
    def validate_config_for_type(cls, v, info):
        """Validate that required config is present for the deployment type."""
        if info.data.get('type') == DeployType.API and info.field_name == 'api':
            return v or APIConfig()
        elif info.data.get('type') == DeployType.DOCKER and info.field_name == 'docker':
            return v or DockerConfig()
        elif info.data.get('type') == DeployType.CLOUD and info.field_name == 'cloud':
            if v is None:
                raise ValueError("cloud config required for cloud deployment type")
            return v
        return v
    
    def model_post_init(self, __context):
        """Post-initialization validation."""
        if self.type == DeployType.API and self.api is None:
            self.api = APIConfig()
        elif self.type == DeployType.DOCKER and self.docker is None:
            self.docker = DockerConfig()
        elif self.type == DeployType.CLOUD and self.cloud is None:
            raise ValueError("cloud config required for cloud deployment type")


class DeployResult(BaseModel):
    """Result of a deployment operation."""
    success: bool = Field(..., description="Whether deployment succeeded")
    message: str = Field(..., description="Result message")
    url: Optional[str] = Field(default=None, description="Deployed service URL")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ServiceState(str, Enum):
    """Service state enum."""
    RUNNING = "running"
    STOPPED = "stopped"
    PENDING = "pending"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


class DeployStatus(BaseModel):
    """Status of a deployed service."""
    state: ServiceState = Field(..., description="Current service state")
    url: Optional[str] = Field(default=None, description="Service URL/endpoint")
    message: str = Field(default="", description="Status message")
    
    # Resource identifiers
    service_name: Optional[str] = Field(default=None, description="Service name")
    provider: Optional[str] = Field(default=None, description="Provider (api/docker/aws/azure/gcp)")
    region: Optional[str] = Field(default=None, description="Deployment region")
    
    # Health info
    healthy: bool = Field(default=False, description="Whether service is healthy")
    instances_running: int = Field(default=0, description="Number of running instances")
    instances_desired: int = Field(default=0, description="Desired number of instances")
    
    # Timestamps
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp")
    
    # Provider-specific metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific metadata")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "state": self.state.value,
            "url": self.url,
            "message": self.message,
            "service_name": self.service_name,
            "provider": self.provider,
            "region": self.region,
            "healthy": self.healthy,
            "instances_running": self.instances_running,
            "instances_desired": self.instances_desired,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }


class DestroyResult(BaseModel):
    """Result of a destroy operation."""
    success: bool = Field(..., description="Whether destroy succeeded")
    message: str = Field(..., description="Result message")
    resources_deleted: List[str] = Field(default_factory=list, description="List of deleted resources")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
