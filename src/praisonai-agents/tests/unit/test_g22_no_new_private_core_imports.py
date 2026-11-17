"""No new imports of private core names from other PraisonAI packages (G-22 gate).

Tier-2 packages and the wrapper must use public core names. ``_*_bridge``
modules are the sanctioned cross-tier route (ARCHITECTURE.md) and are allowed.
The sites below predate the gate; each private name now has a public alias, and
these move to it once a core release ships the alias. Do not add to the list:
use or add a public name instead.
"""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3]
PACKAGES = ["praisonai", "praisonai-code", "praisonai-bot", "praisonai-train", "praisonai-browser",
            "praisonai-mcp", "praisonai-sandbox", "praisonai-deploy"]
KNOWN = {
    ("praisonai-bot/praisonai_bot/bots/_registry.py", "_project_plugins_allowed"),
    ("praisonai-bot/praisonai_bot/bots/botos.py", "_get_store"),
    ("praisonai-bot/praisonai_bot/bots/email.py", "_parse_email_list"),
    ("praisonai-bot/praisonai_bot/gateway/server.py", "_is_trusted_hop"),
    ("praisonai-bot/praisonai_bot/gateway/server.py", "_parse_auth_scopes"),
    ("praisonai-code/praisonai_code/cli/commands/plugins.py", "_project_plugins_allowed"),
    ("praisonai-code/praisonai_code/cli/interactive/async_tui.py", "_litellm_model_info"),
    ("praisonai-code/praisonai_code/cli/interactive/async_tui.py", "_callbacks_lock"),
    ("praisonai-code/praisonai_code/cli/state/redact.py", "_redaction_values"),
    ("praisonai-code/praisonai_code/cli/state/redact.py", "_redaction_lock"),
    ("praisonai/praisonai/cli/commands/schedule.py", "_get_store"),
    ("praisonai/praisonai/code/tools/execute_command.py", "_find_shell_syntax"),
    ("praisonai/praisonai/code/tools/execute_command.py", "_build_subprocess_env"),
    ("praisonai/praisonai/replay/recorder.py", "_run_scope"),
    ("praisonai/praisonai/replay/rerun.py", "_flow_graph"),
}
IMPORT = re.compile(r"from\s+(praisonaiagents[\w.]*)\s+import\s+\(?([^)\n]*(?:\n[^)\n]*)*?)\)?\s*$", re.M)


def _private_imports():
    found = set()
    for pkg in PACKAGES:
        for path in (SRC / pkg).rglob("*.py"):
            rel = path.relative_to(SRC).as_posix()
            if "/tests/" in rel or "/node_modules/" in rel:
                continue
            for m in IMPORT.finditer(path.read_text(errors="ignore")):
                module, names = m.group(1), m.group(2)
                if any(part.startswith("_") and part.endswith("_bridge") for part in module.split(".")):
                    continue
                for item in names.replace("\n", " ").split(","):
                    name = item.split("#")[0].strip().split(" as ")[0].strip()
                    if name.startswith("_") and not name.startswith("__"):
                        found.add((rel, name))
    return found


@pytest.mark.skipif(not (SRC / "praisonai").is_dir(), reason="monorepo checkout only")
def test_no_new_private_core_imports():
    new = sorted(_private_imports() - KNOWN)
    assert new == [], "import a public core name instead (add one if needed): " + ", ".join(f"{p}: {n}" for p, n in new)
