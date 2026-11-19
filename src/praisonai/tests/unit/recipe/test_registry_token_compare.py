"""The recipe registry server compares its write token in constant time."""

import hmac

from praisonai.recipe.server import RegistryServer


def test_registry_check_auth_uses_constant_time(tmp_path, monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    server = RegistryServer(registry_path=tmp_path, token="secret")

    assert server._check_auth({"Authorization": "Bearer secret"})
    assert not server._check_auth({"Authorization": "Bearer nope"})
    assert not server._check_auth({"Authorization": "Bearer tökén"})
    assert not server._check_auth({})
    assert calls, "registry token check did not use hmac.compare_digest"


def test_registry_without_token_stays_open(tmp_path, monkeypatch):
    monkeypatch.delenv("PRAISONAI_REGISTRY_TOKEN", raising=False)
    assert RegistryServer(registry_path=tmp_path)._check_auth({})
