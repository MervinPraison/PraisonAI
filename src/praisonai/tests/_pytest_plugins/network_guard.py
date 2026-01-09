"""
Network Guard Plugin for PraisonAI Tests

This module provides a deterministic network blocker that prevents
outbound network calls in tests that are not explicitly marked as
network-enabled.

The guard blocks socket connections unless:
1. The test is marked with @pytest.mark.network or @pytest.mark.provider_*
2. PRAISONAI_ALLOW_NETWORK=1 or PRAISONAI_LIVE_TESTS=1 is set
3. The connection is to localhost (127.0.0.1 or ::1)
"""

import os
import socket
from functools import wraps
from typing import Set
import pytest

# Original socket methods (saved before patching)
_original_socket_connect = None
_original_socket_connect_ex = None

# Set of test items that are allowed network access
_network_allowed_items: Set[str] = set()


class NetworkBlockedError(Exception):
    """Raised when a test attempts network access without permission."""
    pass


def _is_localhost(address):
    """Check if an address is localhost."""
    if isinstance(address, tuple) and len(address) >= 1:
        host = address[0]
        return host in ('127.0.0.1', '::1', 'localhost', '0.0.0.0')
    return False


def _create_blocking_connect(original_connect):
    """Create a blocking connect wrapper."""
    @wraps(original_connect)
    def blocking_connect(self, address):
        # Allow localhost connections
        if _is_localhost(address):
            return original_connect(self, address)
        
        # Check if we're in a test context that allows network
        # This is a simplified check - the main gating happens in conftest
        if os.environ.get('PRAISONAI_ALLOW_NETWORK') == '1':
            return original_connect(self, address)
        if os.environ.get('PRAISONAI_LIVE_TESTS') == '1':
            return original_connect(self, address)
        
        # Block the connection
        raise NetworkBlockedError(
            f"Network access blocked: attempted connection to {address}. "
            "Set PRAISONAI_ALLOW_NETWORK=1 or mark test with @pytest.mark.network"
        )
    return blocking_connect


def _create_blocking_connect_ex(original_connect_ex):
    """Create a blocking connect_ex wrapper."""
    @wraps(original_connect_ex)
    def blocking_connect_ex(self, address):
        # Allow localhost connections
        if _is_localhost(address):
            return original_connect_ex(self, address)
        
        # Check if we're in a test context that allows network
        if os.environ.get('PRAISONAI_ALLOW_NETWORK') == '1':
            return original_connect_ex(self, address)
        if os.environ.get('PRAISONAI_LIVE_TESTS') == '1':
            return original_connect_ex(self, address)
        
        # Return connection refused error code instead of raising
        return 111  # ECONNREFUSED
    return blocking_connect_ex


def install_network_guard():
    """Install the network guard by patching socket methods."""
    global _original_socket_connect, _original_socket_connect_ex
    
    if _original_socket_connect is None:
        _original_socket_connect = socket.socket.connect
        socket.socket.connect = _create_blocking_connect(_original_socket_connect)
    
    if _original_socket_connect_ex is None:
        _original_socket_connect_ex = socket.socket.connect_ex
        socket.socket.connect_ex = _create_blocking_connect_ex(_original_socket_connect_ex)


def uninstall_network_guard():
    """Uninstall the network guard by restoring original socket methods."""
    global _original_socket_connect, _original_socket_connect_ex
    
    if _original_socket_connect is not None:
        socket.socket.connect = _original_socket_connect
        _original_socket_connect = None
    
    if _original_socket_connect_ex is not None:
        socket.socket.connect_ex = _original_socket_connect_ex
        _original_socket_connect_ex = None


@pytest.fixture(autouse=True)
def network_guard_fixture(request):
    """
    Fixture that manages network guard state per test.
    
    Network is blocked by default unless:
    - Test is marked with network, real, or provider_* markers
    - PRAISONAI_ALLOW_NETWORK=1 or PRAISONAI_LIVE_TESTS=1
    """
    # Check if network should be allowed for this test
    allow_network = False
    
    # Check environment variables
    if os.environ.get('PRAISONAI_ALLOW_NETWORK') == '1':
        allow_network = True
    if os.environ.get('PRAISONAI_LIVE_TESTS') == '1':
        allow_network = True
    
    # Check markers
    if hasattr(request, 'node') and hasattr(request.node, 'iter_markers'):
        for marker in request.node.iter_markers():
            if marker.name in ('network', 'real', 'e2e') or marker.name.startswith('provider_'):
                allow_network = True
                break
    
    # Check path
    if hasattr(request, 'fspath') and request.fspath:
        test_path = str(request.fspath)
        if any(p in test_path for p in ['/integration/', '/e2e/', '/live/']):
            allow_network = True
    
    if allow_network:
        # Temporarily uninstall guard for this test
        uninstall_network_guard()
        yield
        # Re-install after test
        install_network_guard()
    else:
        # Keep guard installed
        yield


def pytest_configure(config):
    """Install network guard at session start."""
    # Only install if not explicitly allowing network
    if os.environ.get('PRAISONAI_ALLOW_NETWORK') != '1' and os.environ.get('PRAISONAI_LIVE_TESTS') != '1':
        install_network_guard()


def pytest_unconfigure(config):
    """Uninstall network guard at session end."""
    uninstall_network_guard()
