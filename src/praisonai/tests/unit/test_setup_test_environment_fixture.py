import os
from types import SimpleNamespace

import pytest

from tests import conftest as test_conftest


PROVIDER_API_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
)


class MockRequest:
    def __init__(self, markers=None, fspath=__file__):
        markers = markers or []
        self.node = SimpleNamespace(iter_markers=lambda: markers)
        self.fspath = fspath


def _run_fixture(request):
    """Execute the fixture generator directly with a synthetic request object."""
    fixture_impl = test_conftest.setup_test_environment.__wrapped__
    fixture_gen = fixture_impl(request)
    next(fixture_gen)
    return fixture_gen


def _teardown_fixture(fixture_gen):
    with pytest.raises(StopIteration):
        next(fixture_gen)


def test_setup_environment_preserves_existing_provider_key_and_restores_missing_keys():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("OPENAI_API_KEY", "real-openai-key")
        mp.delenv("ANTHROPIC_API_KEY", raising=False)

        fixture_gen = _run_fixture(MockRequest())

        assert os.environ["OPENAI_API_KEY"] == "real-openai-key"
        assert os.environ["ANTHROPIC_API_KEY"] == "test-key"

        _teardown_fixture(fixture_gen)

        assert os.environ["OPENAI_API_KEY"] == "real-openai-key"
        assert "ANTHROPIC_API_KEY" not in os.environ


def test_setup_environment_fills_placeholders_only_when_keys_are_missing():
    with pytest.MonkeyPatch.context() as mp:
        for key in PROVIDER_API_KEYS:
            mp.delenv(key, raising=False)

        fixture_gen = _run_fixture(MockRequest())

        for key in PROVIDER_API_KEYS:
            assert os.environ[key] == "test-key"

        _teardown_fixture(fixture_gen)

        for key in PROVIDER_API_KEYS:
            assert key not in os.environ


def test_setup_environment_skips_placeholder_keys_for_provider_marked_tests():
    marker = SimpleNamespace(name="provider_openai")

    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("OPENAI_API_KEY", raising=False)

        fixture_gen = _run_fixture(MockRequest(markers=[marker]))

        assert "OPENAI_API_KEY" not in os.environ

        _teardown_fixture(fixture_gen)
