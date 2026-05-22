"""Generated deploy API servers must enable auth by default."""

from praisonai.deploy.api import generate_api_server_code
from praisonai.deploy.models import APIConfig


def test_generate_api_server_auth_enabled_by_default():
    code = generate_api_server_code("agents.yaml", APIConfig())
    assert "AUTH_ENABLED" in code
    assert "'enabled'" in code or '"enabled"' in code
    assert "check_auth" in code
    assert "compare_digest" in code


def test_generate_api_server_respects_disabled_config():
    code = generate_api_server_code(
        "agents.yaml", APIConfig(auth_enabled=False)
    )
    assert "'disabled'" in code or '"disabled"' in code
