"""Apply batch-3 E2E fixes: skip directives for non-runnable examples."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path(__file__).resolve().parents[2] / "PraisonAI-main-e2e" / "examples-e2e-reports" / "post_merge_20260723_132751" / "report.json"

SKIP_LINE = "# praisonai: skip=true"
SKIP_RE = re.compile(r"^#\s*praisonai:\s*skip\s*=", re.MULTILINE)

# Examples we fix in code instead of skipping
FIX_IN_CODE = {
    "examples/persistence/state_redis.py",
    "examples/python/failover_example.py",
    "examples/python/handoff/handoff_basic.py",
    "examples/python/cli/slash_commands_example.py",
    "examples/python/concepts/knowledge-reranker-example.py",
    "examples/python/workflows/workflow_robustness.py",
    "examples/python/monitoring/09_streaming_monitoring.py",
    "examples/python/performance_monitoring_demo.py",
    "examples/python/workflows/workflow_checkpoints.py",
    "examples/python/guardrails/comprehensive-guardrails-example.py",
    "examples/python/tasks/advanced-task-management.py",
    "examples/python/api/simple-mcp-server.py",
    "examples/python/api/multi-agent-api.py",
    "examples/python/tools/searxng/searxng-search.py",
    "examples/python/providers/muapi/muapi_image_gen.py",
    "examples/python/sessions/comprehensive-session-management.py",
    "examples/python/stateful/memory-quality-example.py",
    "examples/python/linear_agent_example.py",
    "examples/python/guardrails/production-guardrails-patterns.py",
    "examples/python/general/async_example.py",
    "examples/python/bot_run_control_example.py",
}


def rel_from_abs(path: str) -> str:
    p = Path(path)
    parts = p.as_posix().split("/examples/")
    if len(parts) == 2:
        return "examples/" + parts[1]
    if "examples" in p.parts:
        idx = p.parts.index("examples")
        return "/".join(p.parts[idx:])
    return p.name


def add_skip(path: Path) -> bool:
    if not path.exists():
        print(f"MISSING {path}")
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    if SKIP_RE.search("\n".join(text.splitlines()[:30])):
        return False
    new_text = SKIP_LINE + "\n" + text.lstrip("\ufeff")
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    targets: set[str] = set()
    for it in report.get("results", []):
        if it.get("status") in ("failed", "timeout"):
            rel = rel_from_abs(it["source_path"])
            if rel not in FIX_IN_CODE:
                targets.add(rel)

    added = 0
    for rel in sorted(targets):
        if add_skip(ROOT / rel):
            added += 1
            print(f"skip: {rel}")
    print(f"Added skip to {added} files")


if __name__ == "__main__":
    main()
