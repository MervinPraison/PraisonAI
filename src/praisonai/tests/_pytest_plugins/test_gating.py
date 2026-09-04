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

import ast
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

# Cache for per-file AST provider maps: filepath -> {(class, func): providers} or None
_file_provider_cache: Dict[str, Optional[Dict[tuple, Set[str]]]] = {}


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
    
    if provider_marker == 'provider_google':
        if os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY'):
            return True, ""
        return False, "GOOGLE_API_KEY or GEMINI_API_KEY not set"

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


# Paths that should NEVER have provider markers auto-assigned
# These are test infrastructure files that may contain provider keywords
# but are not actual provider tests
EXCLUDED_PATHS = (
    '_pytest_plugins',
    '_meta',
    'test_test_command',
    'test_real_key_smoke',
    'test_gating',
    'test_network_guard',
    'conftest',
    'fixtures/',
)


def _is_excluded_path(filepath_str: str, nodeid: str = '') -> bool:
    """
    Check if a path should be excluded from provider auto-detection.
    
    This prevents test infrastructure files from being incorrectly
    classified as provider tests just because they contain provider
    keywords in their validation/testing logic.
    """
    check_str = filepath_str.lower() + nodeid.lower()
    for excluded in EXCLUDED_PATHS:
        if excluded.lower() in check_str:
            return True
    return False


def _detect_providers_in_text(text: str) -> Set[str]:
    """Return every provider marker whose pattern appears in ``text``."""
    detected = set()
    for marker, pattern in PROVIDER_PATTERNS.items():
        if pattern.search(text):
            detected.add(marker)
    return detected


def _detect_providers_in_file(filepath: Path) -> Set[str]:
    """Detect which providers are referenced anywhere in a test file.

    This is the coarse, whole-file answer. It is deliberately retained: it still
    decides the ``network`` marker (see pytest_collection_modifyitems), so
    narrowing per-test provider markers can never silently un-gate a test that
    lives in a file which really does talk to a provider.
    """
    filepath_str = str(filepath)

    # Skip detection for excluded paths (plugin tests, meta, fixtures)
    if _is_excluded_path(filepath_str):
        return set()

    return _detect_providers_in_text(_get_file_content(filepath))


def _build_per_test_provider_map(filepath: Path) -> Optional[Dict[tuple, Set[str]]]:
    """Map ``(class_name, func_name)`` -> provider markers for one test file.

    The text considered for a test is that test's own source segment plus its
    decorators, **plus the file's module-level scope** (docstring, imports,
    module constants, ``pytestmark``, and fixture/helper bodies). A mocked OpenAI
    test that sits next to an Ollama test therefore no longer inherits
    ``provider_ollama`` from that *sibling's* body -- but a live test whose
    provider identity comes from a shared fixture or module-level config is still
    marked, so positive selectors like ``-m "provider_openai or real"`` keep it.

    Only test functions leak nothing to each other; everything at module scope is
    shared by design, mirroring how a fixture is shared at runtime.

    Returns ``None`` if the file cannot be parsed, so callers fall back to the
    whole-file behaviour rather than under-marking.
    """
    key = str(filepath)
    if key in _file_provider_cache:
        return _file_provider_cache[key]

    result: Optional[Dict[tuple, Set[str]]] = None
    try:
        source = _get_file_content(filepath)
        tree = ast.parse(source)

        # Provider keywords visible at module scope are shared by every test in
        # the file: blank out each test's own body so only genuinely shared
        # context (fixtures, module constants, pytestmark) contributes here.
        module_segments = []

        def _is_test_callable(node) -> bool:
            return (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith('test')
            )

        for child in tree.body:
            if _is_test_callable(child):
                continue
            if isinstance(child, ast.ClassDef):
                # Keep decorators/class-level code, drop only the test bodies.
                for grandchild in child.body:
                    if _is_test_callable(grandchild):
                        continue
                    seg = ast.get_source_segment(source, grandchild)
                    if seg:
                        module_segments.append(seg)
                for decorator in child.decorator_list:
                    seg = ast.get_source_segment(source, decorator)
                    if seg:
                        module_segments.append(seg)
                continue
            seg = ast.get_source_segment(source, child)
            if seg:
                module_segments.append(seg)

        module_providers = _detect_providers_in_text("\n".join(module_segments))

        result = {}

        def _visit(node, class_name=None):
            for child in getattr(node, 'body', ()):
                if isinstance(child, ast.ClassDef):
                    _visit(child, child.name)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    segment = ast.get_source_segment(source, child) or ""
                    for decorator in child.decorator_list:
                        segment += "\n" + (ast.get_source_segment(source, decorator) or "")
                    result[(class_name, child.name)] = (
                        _detect_providers_in_text(segment) | module_providers
                    )

        _visit(tree)
    except (SyntaxError, ValueError, RecursionError):
        result = None

    _file_provider_cache[key] = result
    return result


def _detect_providers_for_item(item) -> Set[str]:
    """Provider markers for a single collected item (per test, not per file)."""
    filepath = Path(item.fspath)
    if _is_excluded_path(str(filepath)):
        return set()

    per_test = _build_per_test_provider_map(filepath)
    if per_test is None:
        return _detect_providers_in_file(filepath)

    parts = item.nodeid.split("::")[1:]
    if not parts:
        return _detect_providers_in_file(filepath)
    func = parts[-1].split("[")[0]
    cls = parts[-2] if len(parts) >= 2 else None

    if (cls, func) in per_test:
        return set(per_test[(cls, func)])
    if (None, func) in per_test:
        return set(per_test[(None, func)])
    # Dynamically generated item we cannot locate in the AST: stay conservative.
    return _detect_providers_in_file(filepath)


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
    _file_provider_cache.clear()


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
        # Skip auto-detection entirely for excluded paths (plugin tests, etc.)
        if item.fspath and test_type != 'unit':
            filepath = Path(item.fspath)
            filepath_str = str(filepath)
            
            # Check if this path should be excluded from provider detection
            if not _is_excluded_path(filepath_str, item.nodeid):
                # An explicit @pytest.mark.offline (or module-level pytestmark)
                # is the author asserting "this test is fully mocked". It turns
                # off provider and network auto-marking for that test.
                if 'offline' not in existing_markers:
                    # Providers are detected per test function, not per file, so
                    # one Ollama test can no longer gate its mocked neighbours.
                    detected_providers = _detect_providers_for_item(item)

                    # Also check nodeid for provider keywords (but not for excluded paths)
                    for marker, pattern in PROVIDER_PATTERNS.items():
                        if pattern.search(item.nodeid):
                            detected_providers.add(marker)

                    for provider in detected_providers:
                        if provider not in existing_markers:
                            item.add_marker(getattr(pytest.mark, provider))

                    # The `network` marker stays WHOLE-FILE derived. Narrowing the
                    # per-test provider markers must not, by itself, un-deselect a
                    # test that really is live -- only `offline` does that. Without
                    # this, 48 currently-deselected integration tests would newly
                    # select, 25 of them with no skipif.
                    if (_detect_providers_in_file(filepath)
                            and 'network' not in existing_markers):
                        item.add_marker(pytest.mark.network)
        
        # Refresh existing markers after additions
        existing_markers = {m.name for m in item.iter_markers()}
        
        # 3. Add network marker if any provider marker is present
        provider_markers = {m for m in existing_markers if m.startswith('provider_')}
        if (provider_markers and 'network' not in existing_markers
                and 'offline' not in existing_markers):
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
    _file_provider_cache.clear()
