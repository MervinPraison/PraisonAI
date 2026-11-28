from unittest.mock import patch

from praisonai.cli.features.n8n import N8nHandler, _default_api_url


def test_default_api_url_uses_host_docker_internal_on_macos_with_docker(monkeypatch):
    monkeypatch.setenv("N8N_DOCKER", "1")
    with patch("praisonai.cli.features.n8n.platform.system", return_value="Darwin"):
        assert _default_api_url("http://localhost:5678") == "http://host.docker.internal:8005"


def test_default_api_url_keeps_loopback_on_linux_with_docker(monkeypatch):
    monkeypatch.setenv("N8N_DOCKER", "1")
    with patch("praisonai.cli.features.n8n.platform.system", return_value="Linux"):
        assert _default_api_url("http://localhost:5678") == "http://127.0.0.1:8005"


def test_per_agent_node_uses_sanitized_agent_id_in_invoke_url():
    handler = N8nHandler(api_url="http://127.0.0.1:8005")
    node = handler._create_per_agent_node(
        agent_id="Sales-Agent (2023)'",
        agent_config={},
        action="Do work",
        position=[100, 200],
        index=1,
        is_first=True,
    )

    assert node["parameters"]["url"] == "http://127.0.0.1:8005/agents/sales_agent_2023/invoke"
    assert node["parameters"]["jsonBody"] == (
        '={{ JSON.stringify({ query: $json.body?.query || $json.query || "Do work" }) }}'
    )
