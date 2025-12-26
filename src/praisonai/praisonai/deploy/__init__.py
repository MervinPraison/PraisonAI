"""
Deploy module for PraisonAI - API, Docker, and Cloud deployments.
"""
from typing import TYPE_CHECKING, Optional, Dict, Any

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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    'Deploy',
    'DeployConfig',
    'DeployType',
    'CloudProvider',
    'DeployResult',
    'DeployStatus',
    'DestroyResult',
    'ServiceState',
    'validate_agents_yaml',
    'generate_sample_yaml',
    'run_all_checks'
]
