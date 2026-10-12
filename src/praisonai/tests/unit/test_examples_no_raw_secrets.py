"""Shipped examples must never contain raw credentials (issue #5783).

Operators copy example configs verbatim into durable stores, so every bot
credential in ``examples/`` must be an environment (``${VAR}``) or SecretRef
(``{source, id}``) reference, and no high-confidence secret literal may appear.
Intentionally fake demo values must say so (contain ``FAKE``).
"""

import re
from pathlib import Path

import pytest
import yaml

# repo_root/src/praisonai/tests/unit/this_file -> up 4 to repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXAMPLES_DIR = _REPO_ROOT / "examples"

_SECRET_PATTERNS = re.compile(
    r"\bxox[abprs]-[0-9A-Za-z-]{10,}"  # Slack bot/user tokens
    r"|\bxapp-\d-[0-9A-Za-z-]{10,}"  # Slack app tokens
    r"|\bsk-(?:proj-|live-|ant-)?[A-Za-z0-9_-]{20,}"  # OpenAI/Anthropic keys
    r"|\bgh[pousr]_[A-Za-z0-9]{36}"  # GitHub tokens
    r"|\bAKIA[0-9A-Z]{16}"  # AWS access key ids
    r"|\bAIza[0-9A-Za-z_-]{35}"  # Google API keys
    r"|\b\d{8,10}:AA[0-9A-Za-z_-]{33}\b"  # Telegram bot tokens
)
_TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".env", ".toml", ".ts", ".js", ".ipynb"}
_CREDENTIAL_KEYS = {
    "token", "bot_token", "app_token", "verify_token", "access_token",
    "signing_secret", "api_key", "password", "secret", "auth_token",
}
_ENV_REF = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")


def _is_text_file(path):
    # ``.env.example`` etc. have no useful suffix, so match env templates by name.
    return path.suffix in _TEXT_SUFFIXES or path.name == ".env" or path.name.startswith(".env.")


def _example_files(predicate):
    if not _EXAMPLES_DIR.exists():
        return []
    return sorted(
        p for p in _EXAMPLES_DIR.rglob("*")
        if p.is_file() and predicate(p) and "node_modules" not in p.parts
    )


def test_env_templates_are_scanned():
    assert _is_text_file(Path(".env.example"))
    assert _is_text_file(Path(".env"))


@pytest.mark.skipif(not _EXAMPLES_DIR.exists(), reason="examples not present")
def test_examples_contain_no_secret_literals():
    hits = []
    for path in _example_files(_is_text_file):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in _SECRET_PATTERNS.finditer(text):
            if "FAKE" not in match.group(0).upper():
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{path.relative_to(_REPO_ROOT)}:{line}")
    assert not hits, "Raw secret literals in examples (use ${VAR}): " + ", ".join(hits)


def _literal_credentials(node, where=""):
    """Yield dotted paths of credential keys holding a literal, at any depth.

    Walking the whole document covers every bot config shape (``channels:``,
    ``platforms:`` and top-level keys such as ``signing_secret``).
    """
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{where}.{key}" if where else str(key)
            if key in _CREDENTIAL_KEYS and value not in (None, ""):
                is_secret_ref = isinstance(value, dict) and {"source", "id"} <= value.keys()
                is_env_ref = isinstance(value, str) and bool(_ENV_REF.match(value))
                if not (is_secret_ref or is_env_ref):
                    yield path
            yield from _literal_credentials(value, path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _literal_credentials(item, f"{where}[{i}]")


def test_literal_credential_detection_covers_bot_shapes():
    assert list(_literal_credentials({"channels": {"slack": {"token": "x"}}})) == ["channels.slack.token"]
    assert list(_literal_credentials({"platforms": {"telegram": {"token": "x"}}})) == ["platforms.telegram.token"]
    assert list(_literal_credentials({"signing_secret": "x"})) == ["signing_secret"]
    assert not list(_literal_credentials({"token": "${T}", "api_key": {"source": "env", "id": "K"}}))


@pytest.mark.skipif(not _EXAMPLES_DIR.exists(), reason="examples not present")
def test_yaml_credentials_are_references():
    hits = []
    for path in _example_files(lambda p: p.suffix in {".yaml", ".yml"}):
        try:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except (yaml.YAMLError, OSError):
            continue
        for doc in docs:
            hits += [f"{path.relative_to(_REPO_ROOT)}: {k}" for k in _literal_credentials(doc)]
    assert not hits, "Credentials must be ${VAR} or SecretRef references: " + ", ".join(hits)
