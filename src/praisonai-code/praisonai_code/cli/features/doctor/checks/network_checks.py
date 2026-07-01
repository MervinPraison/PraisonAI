"""
Network checks for the Doctor CLI module.

Validates network connectivity and configuration.
"""

import os
import socket

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


@register_check(
    id="network_dns",
    title="DNS Resolution",
    description="Check DNS resolution",
    category=CheckCategory.NETWORK,
    severity=CheckSeverity.MEDIUM,
    requires_deep=True,
)
def check_network_dns(config: DoctorConfig) -> CheckResult:
    """Check DNS resolution."""
    test_hosts = [
        "api.openai.com",
        "api.anthropic.com",
        "google.com",
    ]
    
    resolved = []
    failed = []
    
    for host in test_hosts:
        try:
            socket.gethostbyname(host)
            resolved.append(host)
        except socket.gaierror:
            failed.append(host)
    
    if failed:
        return CheckResult(
            id="network_dns",
            title="DNS Resolution",
            category=CheckCategory.NETWORK,
            status=CheckStatus.WARN,
            message=f"DNS resolution failed for {len(failed)} host(s)",
            details=f"Failed: {', '.join(failed)}",
            remediation="Check DNS configuration and network connectivity",
        )
    else:
        return CheckResult(
            id="network_dns",
            title="DNS Resolution",
            category=CheckCategory.NETWORK,
            status=CheckStatus.PASS,
            message=f"DNS resolution working ({len(resolved)} hosts tested)",
        )


@register_check(
    id="network_https",
    title="HTTPS Connectivity",
    description="Check HTTPS connectivity to key endpoints",
    category=CheckCategory.NETWORK,
    severity=CheckSeverity.MEDIUM,
    requires_deep=True,
)
def check_network_https(config: DoctorConfig) -> CheckResult:
    """Check HTTPS connectivity to key endpoints."""
    import urllib.request
    import urllib.error
    
    endpoints = [
        ("https://api.openai.com/v1/models", "OpenAI"),
        ("https://api.anthropic.com/v1/messages", "Anthropic"),
    ]
    
    reachable = []
    unreachable = []
    
    for url, name in endpoints:
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "PraisonAI-Doctor/1.0")
            urllib.request.urlopen(req, timeout=5)
            reachable.append(name)
        except urllib.error.HTTPError as e:
            # HTTP errors (401, 403, etc.) mean we reached the server
            if e.code in (401, 403, 404, 405):
                reachable.append(name)
            else:
                unreachable.append(f"{name} ({e.code})")
        except Exception as e:
            unreachable.append(f"{name} ({type(e).__name__})")
    
    if unreachable:
        return CheckResult(
            id="network_https",
            title="HTTPS Connectivity",
            category=CheckCategory.NETWORK,
            status=CheckStatus.WARN,
            message=f"Cannot reach {len(unreachable)} endpoint(s)",
            details=f"Unreachable: {', '.join(unreachable)}",
            remediation="Check network connectivity and firewall settings",
        )
    else:
        return CheckResult(
            id="network_https",
            title="HTTPS Connectivity",
            category=CheckCategory.NETWORK,
            status=CheckStatus.PASS,
            message=f"HTTPS connectivity verified ({len(reachable)} endpoints)",
        )


@register_check(
    id="network_proxy",
    title="Proxy Configuration",
    description="Check proxy environment variables",
    category=CheckCategory.NETWORK,
    severity=CheckSeverity.INFO,
)
def check_network_proxy(config: DoctorConfig) -> CheckResult:
    """Check proxy environment variables."""
    proxy_vars = {
        "HTTP_PROXY": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
        "NO_PROXY": os.environ.get("NO_PROXY") or os.environ.get("no_proxy"),
    }
    
    configured = {k: v for k, v in proxy_vars.items() if v}
    
    if configured:
        # Mask proxy URLs that might contain credentials
        masked = {}
        for k, v in configured.items():
            if "@" in v:
                # Contains credentials, mask them
                parts = v.split("@")
                masked[k] = f"***@{parts[-1]}"
            else:
                masked[k] = v
        
        return CheckResult(
            id="network_proxy",
            title="Proxy Configuration",
            category=CheckCategory.NETWORK,
            status=CheckStatus.PASS,
            message=f"Proxy configured: {', '.join(configured.keys())}",
            details="; ".join(f"{k}={v}" for k, v in masked.items()),
        )
    else:
        return CheckResult(
            id="network_proxy",
            title="Proxy Configuration",
            category=CheckCategory.NETWORK,
            status=CheckStatus.SKIP,
            message="No proxy configured (direct connection)",
        )


@register_check(
    id="network_ssl",
    title="SSL Configuration",
    description="Check SSL/TLS configuration",
    category=CheckCategory.NETWORK,
    severity=CheckSeverity.INFO,
)
def check_network_ssl(config: DoctorConfig) -> CheckResult:
    """Check SSL/TLS configuration."""
    ssl_vars = {
        "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE"),
        "SSL_CERT_DIR": os.environ.get("SSL_CERT_DIR"),
        "REQUESTS_CA_BUNDLE": os.environ.get("REQUESTS_CA_BUNDLE"),
        "CURL_CA_BUNDLE": os.environ.get("CURL_CA_BUNDLE"),
    }
    
    configured = {k: v for k, v in ssl_vars.items() if v}
    
    # Check for SSL verification disable (security concern)
    ssl_verify = os.environ.get("PYTHONHTTPSVERIFY", "1")
    requests_verify = os.environ.get("REQUESTS_SSL_VERIFY", "1")
    
    warnings = []
    if ssl_verify == "0":
        warnings.append("PYTHONHTTPSVERIFY=0 (SSL verification disabled)")
    if requests_verify.lower() in ("0", "false"):
        warnings.append("REQUESTS_SSL_VERIFY disabled")
    
    if warnings:
        return CheckResult(
            id="network_ssl",
            title="SSL Configuration",
            category=CheckCategory.NETWORK,
            status=CheckStatus.WARN,
            message="SSL verification disabled",
            details="; ".join(warnings),
            remediation="Enable SSL verification for security",
        )
    elif configured:
        return CheckResult(
            id="network_ssl",
            title="SSL Configuration",
            category=CheckCategory.NETWORK,
            status=CheckStatus.PASS,
            message=f"Custom SSL config: {', '.join(configured.keys())}",
        )
    else:
        return CheckResult(
            id="network_ssl",
            title="SSL Configuration",
            category=CheckCategory.NETWORK,
            status=CheckStatus.PASS,
            message="Using default SSL configuration",
        )


@register_check(
    id="network_openai_base_url",
    title="OpenAI Base URL",
    description="Check OpenAI base URL configuration",
    category=CheckCategory.NETWORK,
    severity=CheckSeverity.INFO,
)
def check_network_openai_base_url(config: DoctorConfig) -> CheckResult:
    """Check OpenAI base URL configuration."""
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")
    
    if base_url:
        return CheckResult(
            id="network_openai_base_url",
            title="OpenAI Base URL",
            category=CheckCategory.NETWORK,
            status=CheckStatus.PASS,
            message=f"Custom OpenAI base URL: {base_url}",
            details="Using custom endpoint (e.g., Azure, local proxy)",
        )
    else:
        return CheckResult(
            id="network_openai_base_url",
            title="OpenAI Base URL",
            category=CheckCategory.NETWORK,
            status=CheckStatus.PASS,
            message="Using default OpenAI endpoint",
        )
