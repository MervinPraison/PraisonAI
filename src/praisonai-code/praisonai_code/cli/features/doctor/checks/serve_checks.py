"""
Doctor checks for serve and endpoints functionality.

Checks for:
- Serve module availability
- Endpoints module availability
- Server connectivity
- Discovery endpoint
- Provider types
"""

import os

from ..models import CheckResult, CheckStatus, CheckCategory, CheckSeverity, DoctorConfig
from ..registry import register_check


@register_check(
    id="serve_module",
    title="Serve Module",
    description="Check if serve module is available",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.MEDIUM,
    tags=["serve", "deploy"],
)
def check_serve_module(config: DoctorConfig) -> CheckResult:
    """Check if serve module is available."""
    try:
        from praisonai.cli.features.serve import ServeHandler
        ServeHandler()  # Test instantiation
        return CheckResult(
            id="serve_module",
            title="Serve Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="Serve module available",
            metadata={"handler": "ServeHandler"},
        )
    except ImportError as e:
        return CheckResult(
            id="serve_module",
            title="Serve Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message=f"Serve module not available: {e}",
            remediation="pip install praisonai[serve]",
        )
    except Exception as e:
        return CheckResult(
            id="serve_module",
            title="Serve Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.ERROR,
            message=f"Error checking serve module: {e}",
        )


@register_check(
    id="endpoints_module",
    title="Endpoints Module",
    description="Check if endpoints module is available",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.MEDIUM,
    tags=["endpoints", "deploy"],
)
def check_endpoints_module(config: DoctorConfig) -> CheckResult:
    """Check if endpoints module is available."""
    try:
        from praisonai.endpoints import (
            DiscoveryDocument,
            EndpointInfo,
            ProviderInfo,
            list_provider_types,
        )
        types = list_provider_types()
        return CheckResult(
            id="endpoints_module",
            title="Endpoints Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"Endpoints module available ({len(types)} provider types)",
            metadata={"provider_types": types},
        )
    except ImportError as e:
        return CheckResult(
            id="endpoints_module",
            title="Endpoints Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message=f"Endpoints module not available: {e}",
            remediation="pip install praisonai[serve]",
        )
    except Exception as e:
        return CheckResult(
            id="endpoints_module",
            title="Endpoints Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.ERROR,
            message=f"Error checking endpoints module: {e}",
        )


@register_check(
    id="endpoints_cli",
    title="Endpoints CLI",
    description="Check if endpoints CLI handler is available",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
    tags=["endpoints", "cli"],
)
def check_endpoints_cli(config: DoctorConfig) -> CheckResult:
    """Check if endpoints CLI handler is available."""
    try:
        from praisonai.cli.features.endpoints import EndpointsHandler
        handler = EndpointsHandler()
        return CheckResult(
            id="endpoints_cli",
            title="Endpoints CLI",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="Endpoints CLI handler available",
            metadata={"default_url": handler.DEFAULT_URL},
        )
    except ImportError as e:
        return CheckResult(
            id="endpoints_cli",
            title="Endpoints CLI",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message=f"Endpoints CLI not available: {e}",
            remediation="pip install praisonai",
        )
    except Exception as e:
        return CheckResult(
            id="endpoints_cli",
            title="Endpoints CLI",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.ERROR,
            message=f"Error checking endpoints CLI: {e}",
        )


@register_check(
    id="server_connectivity",
    title="Server Connectivity",
    description="Check if a PraisonAI server is reachable",
    category=CheckCategory.NETWORK,
    severity=CheckSeverity.LOW,
    requires_deep=True,
    tags=["serve", "network"],
)
def check_server_connectivity(config: DoctorConfig) -> CheckResult:
    """Check if a PraisonAI server is reachable."""
    import urllib.request
    import urllib.error
    
    url = os.environ.get("PRAISONAI_ENDPOINTS_URL", "http://localhost:8765")
    health_url = f"{url}/health"
    
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return CheckResult(
                    id="server_connectivity",
                    title="Server Connectivity",
                    category=CheckCategory.NETWORK,
                    status=CheckStatus.PASS,
                    message=f"Server reachable at {url}",
                    metadata={"url": url, "status": resp.status},
                )
            else:
                return CheckResult(
                    id="server_connectivity",
                    title="Server Connectivity",
                    category=CheckCategory.NETWORK,
                    status=CheckStatus.WARN,
                    message=f"Server returned status {resp.status}",
                    metadata={"url": url, "status": resp.status},
                )
    except urllib.error.URLError as e:
        return CheckResult(
            id="server_connectivity",
            title="Server Connectivity",
            category=CheckCategory.NETWORK,
            status=CheckStatus.SKIP,
            message=f"No server running at {url}",
            details=str(e.reason),
            remediation="Start a server: praisonai serve unified --port 8765",
        )
    except Exception as e:
        return CheckResult(
            id="server_connectivity",
            title="Server Connectivity",
            category=CheckCategory.NETWORK,
            status=CheckStatus.ERROR,
            message=f"Error checking server: {e}",
        )


@register_check(
    id="discovery_endpoint",
    title="Discovery Endpoint",
    description="Check if discovery endpoint is available",
    category=CheckCategory.NETWORK,
    severity=CheckSeverity.LOW,
    requires_deep=True,
    dependencies=["server_connectivity"],
    tags=["serve", "discovery"],
)
def check_discovery_endpoint(config: DoctorConfig) -> CheckResult:
    """Check if discovery endpoint is available."""
    import urllib.request
    import urllib.error
    import json
    
    url = os.environ.get("PRAISONAI_ENDPOINTS_URL", "http://localhost:8765")
    discovery_url = f"{url}/__praisonai__/discovery"
    
    try:
        req = urllib.request.Request(discovery_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                providers = data.get("providers", [])
                endpoints = data.get("endpoints", [])
                return CheckResult(
                    id="discovery_endpoint",
                    title="Discovery Endpoint",
                    category=CheckCategory.NETWORK,
                    status=CheckStatus.PASS,
                    message=f"Discovery available: {len(providers)} providers, {len(endpoints)} endpoints",
                    metadata={
                        "url": discovery_url,
                        "schema_version": data.get("schema_version"),
                        "server_name": data.get("server_name"),
                        "providers": [p.get("type") for p in providers],
                    },
                )
            else:
                return CheckResult(
                    id="discovery_endpoint",
                    title="Discovery Endpoint",
                    category=CheckCategory.NETWORK,
                    status=CheckStatus.WARN,
                    message=f"Discovery returned status {resp.status}",
                )
    except urllib.error.URLError:
        return CheckResult(
            id="discovery_endpoint",
            title="Discovery Endpoint",
            category=CheckCategory.NETWORK,
            status=CheckStatus.SKIP,
            message="No server running (skipped)",
        )
    except Exception as e:
        return CheckResult(
            id="discovery_endpoint",
            title="Discovery Endpoint",
            category=CheckCategory.NETWORK,
            status=CheckStatus.ERROR,
            message=f"Error checking discovery: {e}",
        )


@register_check(
    id="a2u_module",
    title="A2U Module",
    description="Check if A2U server module is available",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
    tags=["serve", "a2u"],
)
def check_a2u_module(config: DoctorConfig) -> CheckResult:
    """Check if A2U server module is available."""
    try:
        from praisonai.endpoints.a2u_server import (
            A2UEvent,
            A2USubscription,
            A2UEventBus,
            create_a2u_routes,
        )
        return CheckResult(
            id="a2u_module",
            title="A2U Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message="A2U server module available",
        )
    except ImportError as e:
        return CheckResult(
            id="a2u_module",
            title="A2U Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message=f"A2U module not available: {e}",
            remediation="pip install praisonai[serve]",
        )
    except Exception as e:
        return CheckResult(
            id="a2u_module",
            title="A2U Module",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.ERROR,
            message=f"Error checking A2U module: {e}",
        )


@register_check(
    id="provider_adapters",
    title="Provider Adapters",
    description="Check if all provider adapters are available",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.LOW,
    tags=["serve", "providers"],
)
def check_provider_adapters(config: DoctorConfig) -> CheckResult:
    """Check if all provider adapters are available."""
    try:
        from praisonai.endpoints.providers import (
            BaseProvider,
            RecipeProvider,
            AgentsAPIProvider,
            MCPProvider,
            ToolsMCPProvider,
            A2AProvider,
            A2UProvider,
        )
        providers = [
            "BaseProvider",
            "RecipeProvider",
            "AgentsAPIProvider",
            "MCPProvider",
            "ToolsMCPProvider",
            "A2AProvider",
            "A2UProvider",
        ]
        return CheckResult(
            id="provider_adapters",
            title="Provider Adapters",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"All {len(providers)} provider adapters available",
            metadata={"providers": providers},
        )
    except ImportError as e:
        return CheckResult(
            id="provider_adapters",
            title="Provider Adapters",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message=f"Some provider adapters not available: {e}",
            remediation="pip install praisonai[serve]",
        )
    except Exception as e:
        return CheckResult(
            id="provider_adapters",
            title="Provider Adapters",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.ERROR,
            message=f"Error checking provider adapters: {e}",
        )


@register_check(
    id="fastapi_available",
    title="FastAPI Available",
    description="Check if FastAPI is available for serving",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.MEDIUM,
    tags=["serve", "dependencies"],
)
def check_fastapi_available(config: DoctorConfig) -> CheckResult:
    """Check if FastAPI is available."""
    try:
        import fastapi
        version = getattr(fastapi, "__version__", "unknown")
        return CheckResult(
            id="fastapi_available",
            title="FastAPI Available",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"FastAPI {version} available",
            metadata={"version": version},
        )
    except ImportError:
        return CheckResult(
            id="fastapi_available",
            title="FastAPI Available",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message="FastAPI not installed",
            remediation="pip install fastapi uvicorn",
        )


@register_check(
    id="uvicorn_available",
    title="Uvicorn Available",
    description="Check if Uvicorn is available for serving",
    category=CheckCategory.ENVIRONMENT,
    severity=CheckSeverity.MEDIUM,
    tags=["serve", "dependencies"],
)
def check_uvicorn_available(config: DoctorConfig) -> CheckResult:
    """Check if Uvicorn is available."""
    try:
        import uvicorn
        version = getattr(uvicorn, "__version__", "unknown")
        return CheckResult(
            id="uvicorn_available",
            title="Uvicorn Available",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.PASS,
            message=f"Uvicorn {version} available",
            metadata={"version": version},
        )
    except ImportError:
        return CheckResult(
            id="uvicorn_available",
            title="Uvicorn Available",
            category=CheckCategory.ENVIRONMENT,
            status=CheckStatus.WARN,
            message="Uvicorn not installed",
            remediation="pip install uvicorn",
        )
