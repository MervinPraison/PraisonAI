"""Recipe registry name/version path parts cannot leave the registry."""

import json
import os
import tarfile
from urllib.parse import quote

import pytest

from praisonai.recipe.registry import RegistryError
from praisonai.recipe.server import RegistryServer

ESCAPES = ["..", "../..", "../../victim", "1.0.0/../../../victim", "link"]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PRAISONAI_REGISTRY_TOKEN", raising=False)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep")
    (victim / "manifest.json").write_text(json.dumps({"secret": True}))
    (victim / "demo-link.praison").write_text("secret")

    src = tmp_path / "src"
    src.mkdir()
    (src / "manifest.json").write_text(json.dumps({"name": "demo", "version": "1.0.0"}))
    bundle = tmp_path / "demo-1.0.0.praison"
    with tarfile.open(bundle, "w:gz") as tar:
        tar.add(src / "manifest.json", arcname="manifest.json")

    server = RegistryServer(registry_path=tmp_path / "registry")
    server.registry.publish(bundle)
    os.symlink(victim, server.registry.recipes_path / "demo" / "link")
    return server, victim


@pytest.mark.parametrize("version", ESCAPES)
def test_delete_version_stays_inside(setup, version):
    server, victim = setup
    with pytest.raises(RegistryError):
        server.registry.delete("demo", version)
    assert (victim / "keep.txt").exists()
    assert (server.registry.recipes_path / "demo" / "1.0.0").exists()


@pytest.mark.parametrize("version", ESCAPES)
def test_reads_stay_inside(setup, version):
    server, _ = setup
    with pytest.raises(RegistryError):
        server.registry.get_info("demo", version)
    quoted = quote(quote(version, safe=""), safe="")  # double-encoded, as a client could send
    for v in (version, quoted):
        status, _, body = server.handle_request("GET", f"/v1/recipes/demo/{v}/download", {}, b"")
        assert status != 200 and b"secret" not in body


@pytest.mark.parametrize("version", ESCAPES)
def test_server_delete_refuses_traversal(setup, version):
    server, victim = setup
    once = quote(version, safe="")
    status, _, _ = server.handle_request("DELETE", f"/v1/recipes/demo/{once}", {}, b"")
    assert status == 400
    server.handle_request("DELETE", f"/v1/recipes/demo/{quote(once, safe='')}", {}, b"")
    assert (victim / "keep.txt").exists()
    assert (server.registry.recipes_path / "demo" / "1.0.0").exists()


def test_normal_paths_still_work(setup):
    server, _ = setup
    assert server.registry.get_info("demo", "1.0.0")["name"] == "demo"
    assert server.registry.delete("demo", "1.0.0") is True
