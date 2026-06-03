import inspect

from praisonai.integration.host_app import configure_host
from praisonai.integration.gateway_host import run_integrated_gateway

EXPECTED_DEFAULT_GATEWAY_PORT = 8765


def test_run_integrated_gateway_default_port_matches_cli():
    assert (
        inspect.signature(run_integrated_gateway).parameters["port"].default
        == EXPECTED_DEFAULT_GATEWAY_PORT
    )


def test_configure_host_accepts_agents_file_kwarg():
    assert any(
        param.kind is inspect.Parameter.VAR_KEYWORD
        for param in inspect.signature(configure_host).parameters.values()
    )
