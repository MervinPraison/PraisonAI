"""
Base provider interface for cloud deployments.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from ..models import CloudConfig, DeployResult, DeployStatus, DestroyResult
from ..doctor import DoctorReport


class BaseProvider(ABC):
    """Abstract base class for cloud providers."""
    
    def __init__(self, config: CloudConfig):
        """
        Initialize provider with configuration.
        
        Args:
            config: Cloud configuration
        """
        self.config = config
    
    @abstractmethod
    def deploy(self) -> DeployResult:
        """
        Deploy to cloud provider.
        
        Returns:
            DeployResult with deployment information
        """
        pass
    
    @abstractmethod
    def doctor(self) -> DoctorReport:
        """
        Run provider-specific health checks.
        
        Returns:
            DoctorReport with check results
        """
        pass
    
    @abstractmethod
    def plan(self) -> Dict[str, Any]:
        """
        Generate deployment plan without executing.
        
        Returns:
            Dictionary with planned deployment configuration
        """
        pass
    
    @abstractmethod
    def status(self) -> DeployStatus:
        """
        Get current deployment status.
        
        Returns:
            DeployStatus with current state and info
        """
        pass
    
    @abstractmethod
    def destroy(self, force: bool = False) -> DestroyResult:
        """
        Destroy/delete the deployed service.
        
        Args:
            force: Force deletion without confirmation
            
        Returns:
            DestroyResult with deletion information
        """
        pass


def get_provider(config: CloudConfig) -> BaseProvider:
    """
    Get provider instance based on configuration.
    
    Args:
        config: Cloud configuration
        
    Returns:
        Provider instance
        
    Raises:
        ValueError: If provider is not supported
    """
    from ..models import CloudProvider
    
    if config.provider == CloudProvider.AWS:
        from .aws import AWSProvider
        return AWSProvider(config)
    elif config.provider == CloudProvider.AZURE:
        from .azure import AzureProvider
        return AzureProvider(config)
    elif config.provider == CloudProvider.GCP:
        from .gcp import GCPProvider
        return GCPProvider(config)
    else:
        raise ValueError(f"Unsupported provider: {config.provider}")
