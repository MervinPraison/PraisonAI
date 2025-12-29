"""
Observability checks for the Doctor CLI module.

Validates observability provider configurations.
"""

import os

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


# Observability providers and their required env vars
OBS_PROVIDERS = {
    "langfuse": {
        "env_vars": ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
        "optional_vars": ["LANGFUSE_HOST"],
        "package": "langfuse",
    },
    "langsmith": {
        "env_vars": ["LANGSMITH_API_KEY"],
        "optional_vars": ["LANGSMITH_PROJECT"],
        "package": "langsmith",
    },
    "agentops": {
        "env_vars": ["AGENTOPS_API_KEY"],
        "optional_vars": [],
        "package": "agentops",
    },
    "arize": {
        "env_vars": ["ARIZE_API_KEY"],
        "optional_vars": ["ARIZE_SPACE_KEY"],
        "package": "arize",
    },
    "datadog": {
        "env_vars": ["DATADOG_API_KEY"],
        "optional_vars": ["DD_SITE"],
        "package": "ddtrace",
    },
    "mlflow": {
        "env_vars": [],
        "optional_vars": ["MLFLOW_TRACKING_URI"],
        "package": "mlflow",
    },
    "wandb": {
        "env_vars": ["WANDB_API_KEY"],
        "optional_vars": ["WANDB_PROJECT"],
        "package": "wandb",
    },
    "braintrust": {
        "env_vars": ["BRAINTRUST_API_KEY"],
        "optional_vars": [],
        "package": "braintrust",
    },
}


@register_check(
    id="obs_config",
    title="Observability Configuration",
    description="Check observability provider configuration",
    category=CheckCategory.OBSERVABILITY,
    severity=CheckSeverity.INFO,
)
def check_obs_config(config: DoctorConfig) -> CheckResult:
    """Check observability provider configuration."""
    configured = []
    
    for provider, info in OBS_PROVIDERS.items():
        env_vars = info["env_vars"]
        if env_vars:
            if all(os.environ.get(var) for var in env_vars):
                configured.append(provider)
        else:
            # Check optional vars for providers without required vars
            if any(os.environ.get(var) for var in info.get("optional_vars", [])):
                configured.append(provider)
    
    if configured:
        return CheckResult(
            id="obs_config",
            title="Observability Configuration",
            category=CheckCategory.OBSERVABILITY,
            status=CheckStatus.PASS,
            message=f"Configured provider(s): {', '.join(configured)}",
            metadata={"providers": configured},
        )
    else:
        return CheckResult(
            id="obs_config",
            title="Observability Configuration",
            category=CheckCategory.OBSERVABILITY,
            status=CheckStatus.SKIP,
            message="No observability providers configured (optional)",
            details="Set provider API keys to enable observability",
        )


@register_check(
    id="obs_langfuse",
    title="Langfuse",
    description="Check Langfuse observability provider",
    category=CheckCategory.OBSERVABILITY,
    severity=CheckSeverity.LOW,
)
def check_obs_langfuse(config: DoctorConfig) -> CheckResult:
    """Check Langfuse observability provider."""
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    
    if public_key and secret_key:
        try:
            import langfuse
            version = getattr(langfuse, "__version__", "unknown")
            return CheckResult(
                id="obs_langfuse",
                title="Langfuse",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.PASS,
                message=f"Langfuse configured (SDK {version})",
            )
        except ImportError:
            return CheckResult(
                id="obs_langfuse",
                title="Langfuse",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.WARN,
                message="Langfuse keys set but SDK not installed",
                remediation="Install with: pip install langfuse",
            )
    else:
        return CheckResult(
            id="obs_langfuse",
            title="Langfuse",
            category=CheckCategory.OBSERVABILITY,
            status=CheckStatus.SKIP,
            message="Langfuse not configured (optional)",
        )


@register_check(
    id="obs_langsmith",
    title="LangSmith",
    description="Check LangSmith observability provider",
    category=CheckCategory.OBSERVABILITY,
    severity=CheckSeverity.LOW,
)
def check_obs_langsmith(config: DoctorConfig) -> CheckResult:
    """Check LangSmith observability provider."""
    api_key = os.environ.get("LANGSMITH_API_KEY")
    
    if api_key:
        try:
            import langsmith
            version = getattr(langsmith, "__version__", "unknown")
            return CheckResult(
                id="obs_langsmith",
                title="LangSmith",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.PASS,
                message=f"LangSmith configured (SDK {version})",
            )
        except ImportError:
            return CheckResult(
                id="obs_langsmith",
                title="LangSmith",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.WARN,
                message="LangSmith key set but SDK not installed",
                remediation="Install with: pip install langsmith",
            )
    else:
        return CheckResult(
            id="obs_langsmith",
            title="LangSmith",
            category=CheckCategory.OBSERVABILITY,
            status=CheckStatus.SKIP,
            message="LangSmith not configured (optional)",
        )


@register_check(
    id="obs_agentops",
    title="AgentOps",
    description="Check AgentOps observability provider",
    category=CheckCategory.OBSERVABILITY,
    severity=CheckSeverity.LOW,
)
def check_obs_agentops(config: DoctorConfig) -> CheckResult:
    """Check AgentOps observability provider."""
    api_key = os.environ.get("AGENTOPS_API_KEY")
    
    if api_key:
        try:
            import agentops
            version = getattr(agentops, "__version__", "unknown")
            return CheckResult(
                id="obs_agentops",
                title="AgentOps",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.PASS,
                message=f"AgentOps configured (SDK {version})",
            )
        except ImportError:
            return CheckResult(
                id="obs_agentops",
                title="AgentOps",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.WARN,
                message="AgentOps key set but SDK not installed",
                remediation="Install with: pip install agentops",
            )
    else:
        return CheckResult(
            id="obs_agentops",
            title="AgentOps",
            category=CheckCategory.OBSERVABILITY,
            status=CheckStatus.SKIP,
            message="AgentOps not configured (optional)",
        )


@register_check(
    id="obs_praisonai_telemetry",
    title="PraisonAI Telemetry",
    description="Check PraisonAI built-in telemetry",
    category=CheckCategory.OBSERVABILITY,
    severity=CheckSeverity.INFO,
)
def check_obs_praisonai_telemetry(config: DoctorConfig) -> CheckResult:
    """Check PraisonAI built-in telemetry."""
    telemetry_enabled = os.environ.get("PRAISONAI_TELEMETRY_ENABLED", "").lower() in ("true", "1", "yes")
    
    try:
        from praisonaiagents.telemetry import get_telemetry
        
        if telemetry_enabled:
            return CheckResult(
                id="obs_praisonai_telemetry",
                title="PraisonAI Telemetry",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.PASS,
                message="PraisonAI telemetry enabled",
            )
        else:
            return CheckResult(
                id="obs_praisonai_telemetry",
                title="PraisonAI Telemetry",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.SKIP,
                message="PraisonAI telemetry available but not enabled",
                details="Set PRAISONAI_TELEMETRY_ENABLED=true to enable",
            )
    except ImportError:
        return CheckResult(
            id="obs_praisonai_telemetry",
            title="PraisonAI Telemetry",
            category=CheckCategory.OBSERVABILITY,
            status=CheckStatus.SKIP,
            message="PraisonAI telemetry module not available",
        )


@register_check(
    id="obs_connectivity",
    title="Observability Connectivity",
    description="Test connectivity to observability providers",
    category=CheckCategory.OBSERVABILITY,
    severity=CheckSeverity.LOW,
    requires_deep=True,
)
def check_obs_connectivity(config: DoctorConfig) -> CheckResult:
    """Test connectivity to observability providers (deep mode)."""
    # Only test if a specific provider is requested or if we have configured providers
    provider = config.provider
    
    if provider == "langfuse":
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        
        if not (public_key and secret_key):
            return CheckResult(
                id="obs_connectivity",
                title="Observability Connectivity",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.SKIP,
                message="Langfuse not configured",
            )
        
        try:
            from langfuse import Langfuse
            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
            )
            # Try to authenticate
            client.auth_check()
            return CheckResult(
                id="obs_connectivity",
                title="Observability Connectivity",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.PASS,
                message="Langfuse connectivity verified",
            )
        except Exception as e:
            return CheckResult(
                id="obs_connectivity",
                title="Observability Connectivity",
                category=CheckCategory.OBSERVABILITY,
                status=CheckStatus.FAIL,
                message=f"Langfuse connection failed: {type(e).__name__}",
                details=str(e)[:200],
            )
    
    # Default: skip if no specific provider requested
    return CheckResult(
        id="obs_connectivity",
        title="Observability Connectivity",
        category=CheckCategory.OBSERVABILITY,
        status=CheckStatus.SKIP,
        message="Use --provider to test specific provider connectivity",
    )
