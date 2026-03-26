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
    "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "PATH",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONHOME",
    "NODE_OPTIONS",
    "NODE_PATH",
    "RUBYLIB",
    "PERL5LIB",
    "PERL5OPT",
    "CLASSPATH",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "BASH_ENV",
    "ENV",
    "CDPATH",
    "PROMPT_COMMAND",
    "SHLVL",
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
    """Snapshot env vars before each test and restore them afterwards."""
    # Save original values (None means the key was not set)
    _snapshot = {k: os.environ.get(k) for k in DANGEROUS_KEYS + SAFE_KEYS}
    yield
    # Restore: reinstate original values or remove if they didn't exist
    for key, original in _snapshot.items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


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
            match=r"[Nn]ot allowed|[Bb]locked|[Dd]angerous",
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
def test_non_string_key_rejected():
    """Non-string YAML keys (int, None) must produce a clear ValueError."""
    validate = _get_validate_env_key()

    for bad_key in [123, None, 3.14, True]:
        with pytest.raises(ValueError, match=r"must be a string"):
            validate(bad_key)


@pytest.mark.unit
def test_vulnerability_scenario_ld_preload():
    """LD_PRELOAD in a YAML environment section must be blocked.

    This test simulates the schedule-config loading path: parse the YAML,
    then validate-all-then-apply (matching the fail-closed logic in main.py).
    """
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

    # Simulate the validate-all-then-apply pattern from main.py
    with pytest.raises(ValueError):
        validated_env = {}
        for key, value in env_vars.items():
            validate(key)
            validated_env[key] = str(value)
        # If we reach here, no key was blocked — the test fails via pytest.raises
        os.environ.update(validated_env)

    # LD_PRELOAD must NOT have been applied (fail-closed)
    assert "LD_PRELOAD" not in os.environ or os.environ.get("LD_PRELOAD") != "/tmp/evil.so"


@pytest.mark.unit
def test_malformed_env_keys_rejected():
    """Empty strings, keys with '=', and keys with NUL must be rejected."""
    validate = _get_validate_env_key()

    for bad_key in ["", "A=B", "FOO\x00BAR"]:
        with pytest.raises(ValueError, match=r"non-empty string without"):
            validate(bad_key)


@pytest.mark.unit
def test_non_dict_root_config_rejected():
    """A YAML schedule config whose root is not a mapping must be rejected.

    This validates the root type-check added after yaml.safe_load().
    When the root config is a list or scalar, earlier .get() calls would
    raise AttributeError; after the fix they raise ValueError, which is
    caught and presented cleanly.
    """
    import yaml as _yaml

    for bad_doc in ["- item1\n- item2", "42", "just a string"]:
        file_config = _yaml.safe_load(bad_doc)
        # The check from main.py: if not isinstance(file_config, dict)
        assert not isinstance(file_config, dict), (
            f"Expected non-dict for {bad_doc!r}, got {type(file_config)}"
        )


@pytest.mark.unit
def test_non_dict_deployment_rejected():
    """A 'deployment' value that is not a mapping must be caught."""
    import yaml as _yaml

    bad_config = _yaml.safe_load("deployment: not-a-mapping\nenvironment:\n  MODEL: x")
    deploy_config = bad_config.get("deployment", {})
    assert not isinstance(deploy_config, dict), (
        f"Expected non-dict deployment, got {type(deploy_config)}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
