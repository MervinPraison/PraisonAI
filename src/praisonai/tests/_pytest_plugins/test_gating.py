"""
PraisonAI Test Gating Plugin

This module provides automatic marker assignment and skip/gating enforcement
for the PraisonAI test suite. It ensures tests are properly classified and
gated based on provider requirements and network access.

Environment Variables:
- PRAISONAI_TEST_TIER: smoke|main|extended|nightly (default: main)
- PRAISONAI_ALLOW_NETWORK: 0|1 (default: 0)
- PRAISONAI_LIVE_TESTS: 0|1 (default: 0)
- PRAISONAI_TEST_PROVIDERS: comma-separated list or 'all' (default: openai)
- PRAISONAI_LOCAL_SERVICES: 0|1 (default: 0)
"""

import os
import re
import socket
from pathlib import Path
from typing import Set, Dict, Optional
import pytest

# Provider detection patterns (case-insensitive)
PROVIDER_PATTERNS: Dict[str, re.Pattern] = {
    'provider_openai': re.compile(r'\b(openai|gpt-[34]|gpt4|chatgpt)\b', re.IGNORECASE),
    'provider_anthropic': re.compile(r'\b(anthropic|claude)\b', re.IGNORECASE),
    'provider_google': re.compile(r'\b(google|gemini|palm|vertex)\b', re.IGNORECASE),
    'provider_ollama': re.compile(r'\b(ollama)\b', re.IGNORECASE),
    'provider_grok_xai': re.compile(r'\b(grok|xai|x\.ai)\b', re.IGNORECASE),
    'provider_groq': re.compile(r'\b(groq)\b', re.IGNORECASE),
    'provider_cohere': re.compile(r'\b(cohere)\b', re.IGNORECASE),
}

# Provider to environment variable mapping
PROVIDER_ENV_KEYS: Dict[str, str] = {
    'provider_openai': 'OPENAI_API_KEY',
    'provider_anthropic': 'ANTHROPIC_API_KEY',
    'provider_google': 'GOOGLE_API_KEY',
    'provider_ollama': None,  # Requires service check
    'provider_grok_xai': 'XAI_API_KEY',
    'provider_groq': 'GROQ_API_KEY',
    'provider_cohere': 'COHERE_API_KEY',
}

# Cache for file content scans (avoid re-reading files)
_file_content_cache: Dict[str, str] = {}


def _get_test_tier() -> str:
    """Get the current test tier from environment."""
    return os.environ.get('PRAISONAI_TEST_TIER', 'main').lower()


def _is_network_allowed() -> bool:
    """Check if network access is allowed."""
    return (
        os.environ.get('PRAISONAI_ALLOW_NETWORK', '0') == '1' or
        os.environ.get('PRAISONAI_LIVE_TESTS', '0') == '1'
    )


def _get_allowed_providers() -> Set[str]:
    """Get the set of allowed providers."""
    providers_str = os.environ.get('PRAISONAI_TEST_PROVIDERS', 'openai')
    if providers_str.lower() == 'all':
        return set(PROVIDER_ENV_KEYS.keys())
    return {f'provider_{p.strip().lower()}' for p in providers_str.split(',')}


def _is_local_services_allowed() -> bool:
    """Check if local services (Docker, etc.) are allowed."""
    return os.environ.get('PRAISONAI_LOCAL_SERVICES', '0') == '1'


def _check_ollama_available() -> bool:
    """Check if Ollama is running locally."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('127.0.0.1', 11434))
        sock.close()
        return result == 0
    except Exception:
        return False


def _check_provider_available(provider_marker: str) -> tuple[bool, str]:
    """
    Check if a provider is available.
    Returns (is_available, reason_if_not).
    """
    env_key = PROVIDER_ENV_KEYS.get(provider_marker)
    
    if provider_marker == 'provider_ollama':
        if _check_ollama_available():
            return True, ""
        return False, "Ollama not running on localhost:11434"
    
    if env_key:
        if os.environ.get(env_key):
            return True, ""
        return False, f"{env_key} not set"
    
    return True, ""  # Unknown provider, allow by default


def _get_file_content(filepath: Path) -> str:
    """Get file content with caching."""
    filepath_str = str(filepath)
    if filepath_str not in _file_content_cache:
        try:
            _file_content_cache[filepath_str] = filepath.read_text(errors='ignore')
        except Exception:
            _file_content_cache[filepath_str] = ""
    return _file_content_cache[filepath_str]


def _detect_providers_in_file(filepath: Path) -> Set[str]:
    """Detect which providers are referenced in a test file."""
    # Skip detection for plugin test files and meta directories
    filepath_str = str(filepath)
    if '_pytest_plugins' in filepath_str or '_meta' in filepath_str:
        return set()
    if 'test_test_command' in filepath_str or 'test_gating' in filepath_str:
        return set()
    
    content = _get_file_content(filepath)
    detected = set()
    for marker, pattern in PROVIDER_PATTERNS.items():
        if pattern.search(content):
            detected.add(marker)
    return detected


def _get_test_type_from_path(nodeid: str) -> Optional[str]:
    """Determine test type based on path conventions."""
    nodeid_lower = nodeid.lower()
    if '/unit/' in nodeid_lower or '\\unit\\' in nodeid_lower:
        return 'unit'
    if '/integration/' in nodeid_lower or '\\integration\\' in nodeid_lower:
        return 'integration'
    if '/e2e/' in nodeid_lower or '\\e2e\\' in nodeid_lower:
        return 'e2e'
    if '/live/' in nodeid_lower or '\\live\\' in nodeid_lower:
        return 'e2e'
    return None


def pytest_configure(config):
    """Register custom markers and initialize plugin state."""
    # Clear file content cache at start of session
    _file_content_cache.clear()


def pytest_collection_modifyitems(config, items):
    """
    Auto-assign markers and apply skip logic based on gating rules.
    
    This hook runs after test collection and:
    1. Adds test type markers (unit/integration/e2e) based on path
    2. Adds provider markers based on file content analysis
    3. Adds network marker if any provider marker is present
    4. Applies skip logic based on environment configuration
    """
    tier = _get_test_tier()
    network_allowed = _is_network_allowed()
    allowed_providers = _get_allowed_providers()
    local_services_allowed = _is_local_services_allowed()
    
    for item in items:
        # Get existing markers
        existing_markers = {m.name for m in item.iter_markers()}
        
        # 1. Auto-assign test type marker based on path
        test_type = _get_test_type_from_path(item.nodeid)
        if test_type and test_type not in existing_markers:
            item.add_marker(getattr(pytest.mark, test_type))
        
        # 2. Auto-detect and assign provider markers from file content
        if item.fspath:
            filepath = Path(item.fspath)
            detected_providers = _detect_providers_in_file(filepath)
            
            # Also check nodeid for provider keywords
            for marker, pattern in PROVIDER_PATTERNS.items():
                if pattern.search(item.nodeid):
                    detected_providers.add(marker)
            
            for provider in detected_providers:
                if provider not in existing_markers:
                    item.add_marker(getattr(pytest.mark, provider))
        
        # Refresh existing markers after additions
        existing_markers = {m.name for m in item.iter_markers()}
        
        # 3. Add network marker if any provider marker is present
        provider_markers = {m for m in existing_markers if m.startswith('provider_')}
        if provider_markers and 'network' not in existing_markers:
            item.add_marker(pytest.mark.network)
        
        # Handle 'real' marker as alias for network
        if 'real' in existing_markers and 'network' not in existing_markers:
            item.add_marker(pytest.mark.network)
        
        # Refresh markers again
        existing_markers = {m.name for m in item.iter_markers()}
        
        # 4. Apply skip logic based on tier and gating rules
        
        # Smoke tier: only unit tests, no network, no slow
        if tier == 'smoke':
            if 'integration' in existing_markers or 'e2e' in existing_markers:
                item.add_marker(pytest.mark.skip(
                    reason="Smoke tier: skipping non-unit tests"
                ))
                continue
            if 'slow' in existing_markers:
                item.add_marker(pytest.mark.skip(
                    reason="Smoke tier: skipping slow tests"
                ))
                continue
        
        # Skip network tests if network not allowed
        if 'network' in existing_markers and not network_allowed:
            item.add_marker(pytest.mark.skip(
                reason="Network tests disabled. Set PRAISONAI_ALLOW_NETWORK=1 or PRAISONAI_LIVE_TESTS=1"
            ))
            continue
        
        # Skip provider tests if provider not in allowed list or key missing
        for provider in provider_markers:
            if provider not in allowed_providers:
                item.add_marker(pytest.mark.skip(
                    reason=f"Provider {provider} not in PRAISONAI_TEST_PROVIDERS"
                ))
                break
            
            # Check if provider is actually available
            if network_allowed:
                available, reason = _check_provider_available(provider)
                if not available:
                    item.add_marker(pytest.mark.skip(reason=reason))
                    break
        
        # Skip local_service tests if not allowed
        if 'local_service' in existing_markers and not local_services_allowed:
            item.add_marker(pytest.mark.skip(
                reason="Local service tests disabled. Set PRAISONAI_LOCAL_SERVICES=1"
            ))
            continue


def pytest_sessionfinish(session, exitstatus):
    """Clean up at end of session."""
    _file_content_cache.clear()
