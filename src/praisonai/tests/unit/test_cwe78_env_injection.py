"""
PoC test for CWE-78: YAML-loaded environment variables set via
os.environ without sanitization.

The schedule config YAML can set arbitrary environment variables
including dangerous ones like LD_PRELOAD, PATH, PYTHONPATH, etc.,
which can lead to arbitrary code execution.

This test verifies that dangerous environment variable keys are
rejected by the _validate_env_key function added in the fix.
"""
import os
import textwrap
import pytest
import yaml


DANGEROUS_KEYS = [
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "DYLD_FRAMEWORK_PATH",
    "PATH",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONHOME",
    "NODE_OPTIONS",
    "NODE_PATH",
    "RUBYLIB",
    "PERL5LIB",
    "CLASSPATH",
    "ld_preload",        # lowercase variant
    "Ld_Preload",        # mixed case variant
]

# Generic key names that won't trigger provider-detection
SAFE_KEYS = [
    "MODEL_NAME",
    "MY_API_KEY",
    "MY_MODEL_NAME",
    "MY_BASE_URL",
    "MY_CUSTOM_VAR",
]


@pytest.fixture(autouse=True)
def _clean_env():
    """Remove any test-set env vars after each test."""
    yield
    for key in DANGEROUS_KEYS + SAFE_KEYS:
        os.environ.pop(key, None)


def _get_validate_env_key():
    """Import _validate_env_key, failing clearly if absent."""
    try:
        from praisonai.cli.main import _validate_env_key
        return _validate_env_key
    except ImportError:
        pytest.fail(
            "_validate_env_key not found in praisonai.cli.main"
            " — the env-var validation fix has not been applied"
        )


@pytest.mark.unit
def test_dangerous_env_keys_are_blocked():
    """Dangerous keys must be rejected with a ValueError."""
    validate = _get_validate_env_key()

    for key in DANGEROUS_KEYS:
        with pytest.raises(
            ValueError,
            match="[Nn]ot allowed|[Bb]locked|[Dd]angerous",
        ):
            validate(key)


@pytest.mark.unit
def test_safe_env_keys_are_allowed():
    """Safe keys must pass validation without error."""
    validate = _get_validate_env_key()

    for key in SAFE_KEYS:
        # Should not raise
        validate(key)


@pytest.mark.unit
def test_vulnerability_scenario_ld_preload():
    """LD_PRELOAD in a YAML environment section must be blocked."""
    validate = _get_validate_env_key()

    config_content = textwrap.dedent("""\
        deployment:
          schedule: "*/5 * * * *"
          provider: gcp
        environment:
          LD_PRELOAD: /tmp/evil.so
          MODEL_NAME: test-model
    """)

    file_config = yaml.safe_load(config_content)
    env_vars = file_config.get("environment", {})

    with pytest.raises(ValueError):
        for key in env_vars:
            validate(key)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
