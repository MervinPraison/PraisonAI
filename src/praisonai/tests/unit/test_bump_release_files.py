"""bump_and_release.py keeps the MCP Registry manifest and Docker guide in step."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bump_and_release.py"


@pytest.fixture
def bump(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("bump_and_release_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    return mod


def _tree(root: Path) -> None:
    (root / "src/praisonai").mkdir(parents=True)
    (root / "docker").mkdir()
    (root / "src/praisonai/server.json").write_text(json.dumps({
        "name": "io.github.MervinPraison/praisonai",
        "version": "2.3.42",
        "packages": [{"registryType": "pypi", "identifier": "praisonai", "version": "2.3.42"}],
    }, indent=2))
    (root / "docker/README.md").write_text(
        'RUN pip install "praisonai==2.2.95" "praisonaiagents==0.0.92"\n'
    )


def test_bump_updates_server_json_and_docker_guide(bump, tmp_path):
    _tree(tmp_path)
    bump.bump_version("9.8.7", agents_version="1.2.3")

    manifest = json.loads((tmp_path / "src/praisonai/server.json").read_text())
    assert manifest["version"] == "9.8.7"
    assert manifest["packages"][0]["version"] == "9.8.7"
    assert (tmp_path / "docker/README.md").read_text() == (
        'RUN pip install "praisonai==9.8.7" "praisonaiagents==1.2.3"\n'
    )


def test_agents_pin_left_alone_without_agents_version(bump, tmp_path):
    _tree(tmp_path)
    bump.bump_version("9.8.7")
    assert '"praisonaiagents==0.0.92"' in (tmp_path / "docker/README.md").read_text()


def test_release_stages_the_new_files():
    text = SCRIPT.read_text()
    assert '"src/praisonai/server.json",' in text
    assert '"docker/README.md",' in text


def test_repo_server_json_matches_wrapper_version():
    root = SCRIPT.parents[3]
    manifest = json.loads((root / "src/praisonai/server.json").read_text())
    ns = {}
    exec((root / "src/praisonai/praisonai/version.py").read_text(), ns)
    assert manifest["version"] == ns["__version__"]
    assert all(p["version"] == ns["__version__"] for p in manifest["packages"])
