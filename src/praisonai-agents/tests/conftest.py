"""
Pytest configuration for PraisonAI Agents tests.

Provides fixtures and markers for testing, including:
- live: Tests that require real API keys (opt-in)
- slow: Tests that take longer to run
"""

import os
import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "live: mark test as requiring real API keys (deselect with '-m \"not live\"')"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless PRAISONAI_LIVE_TESTS=1 is set."""
    if os.environ.get("PRAISONAI_LIVE_TESTS") != "1":
        skip_live = pytest.mark.skip(reason="Live tests disabled. Set PRAISONAI_LIVE_TESTS=1 to enable.")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment, skip if not available."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.fixture
def live_test_enabled():
    """Check if live tests are enabled."""
    if os.environ.get("PRAISONAI_LIVE_TESTS") != "1":
        pytest.skip("Live tests disabled. Set PRAISONAI_LIVE_TESTS=1 to enable.")
    return True
