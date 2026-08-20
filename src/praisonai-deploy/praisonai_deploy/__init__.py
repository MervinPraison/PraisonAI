"""
Deploy module for PraisonAI - API, Docker, and Cloud deployments.
"""
from typing import TYPE_CHECKING, Optional, Dict, Any

from praisonai_deploy._version import __version__

if TYPE_CHECKING:
    from .models import DeployConfig, DeployResult, DeployType, CloudProvider
    from .schema import validate_agents_yaml, generate_sample_yaml
    from .doctor import DoctorReport, run_all_checks


def __getattr__(name):
    """Lazy load deploy modules."""
    if name == 'Deploy':
        from .main import Deploy
        return Deploy
    elif name == 'DeployConfig':
        from .models import DeployConfig
        return DeployConfig
    elif name == 'DeployType':
        from .models import DeployType
        return DeployType
    elif name == 'CloudProvider':
        from .models import CloudProvider
        return CloudProvider
    elif name == 'coerce_cloud_provider':
        from .models import coerce_cloud_provider
        return coerce_cloud_provider
    elif name == 'list_cloud_providers':
        from .providers._registry import list_cloud_providers
        return list_cloud_providers
    elif name == 'DeployResult':
        from .models import DeployResult
        return DeployResult
    elif name == 'DeployStatus':
        from .models import DeployStatus
        return DeployStatus
    elif name == 'DestroyResult':
        from .models import DestroyResult
        return DestroyResult
    elif name == 'ServiceState':
        from .models import ServiceState
        return ServiceState
    elif name == 'validate_agents_yaml':
        from .schema import validate_agents_yaml
        return validate_agents_yaml
    elif name == 'generate_sample_yaml':
        from .schema import generate_sample_yaml
        return generate_sample_yaml
    elif name == 'run_all_checks':
        from .doctor import run_all_checks
        return run_all_checks
    elif name == 'get_deployment_status':
        return get_deployment_status
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_deployment_status(
    deployment_name: Optional[str] = None,
    *,
    agents_file: str = "agents.yaml",
) -> Dict[str, Any]:
    """Return deployment status for MCP and tooling."""
    from .main import Deploy

    deploy = Deploy.from_yaml(agents_file)
    status = deploy.status()
    payload: Dict[str, Any] = {
        "state": status.state.value if hasattr(status.state, "value") else str(status.state),
        "message": status.message,
        "url": status.url,
        "service_name": status.service_name,
        "provider": status.provider,
        "healthy": status.healthy,
    }
    if deployment_name:
        payload["deployment_name"] = deployment_name
    return payload


__all__ = [
    'Deploy',
    'DeployConfig',
    'DeployType',
    'CloudProvider',
    'coerce_cloud_provider',
    'list_cloud_providers',
    'DeployResult',
    'DeployStatus',
    'DestroyResult',
    'ServiceState',
    'validate_agents_yaml',
    'generate_sample_yaml',
    'run_all_checks',
    'get_deployment_status',
    '__version__',
]
