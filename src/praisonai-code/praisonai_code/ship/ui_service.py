"""Backend facade for the OpenShip PraisonAIUI plugin.

Delegates 100% of ship, self-review, steward, and declarative policy logic to
``praisonai_code.ship.*``. Keeps a lightweight local JSONL ledger of run
summaries (zero source code, diffs, or secrets stored) and enforces strict
safety invariants: never merges, never approves, never force-pushes, and
requires explicit confirmation on any write action.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_PR_RE = re.compile(r"^#?(\d+)$")
_COMMIT_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
_MAX_DIFF_FILES = 8
_MAX_DIFF_CHARS = 40_000
_EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass
class FileDiff:
    path: str
    before: str
    after: str


@dataclass
class RepoStatus:
    repo: str
    branch: str = ""
    base: str = "main"
    dirty_files: List[str] = field(default_factory=list)
    gh_ready: bool = False
    current_pr: Optional[Dict[str, Any]] = None
    error: str = ""


def _run_in(repo: Path) -> Callable[..., subprocess.CompletedProcess]:
    def _runner(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        kwargs.setdefault("cwd", str(repo))
        return subprocess.run(cmd, **kwargs)

    return _runner


def normalize_pr(raw: Optional[str]) -> Optional[str]:
    """Validate and normalize a PR number (digits only, optional leading '#')."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = _PR_RE.match(text)
    if not match:
        raise ValueError(f"invalid PR number {raw!r}; expected digits (e.g. 6852)")
    return match.group(1)


def get_repo_root() -> Path:
    """Resolve the active git repository from OPENSHIP_REPO or CWD."""
    raw = os.environ.get("OPENSHIP_REPO", "").strip()
    base = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(base),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return base


def _ledger_path() -> Path:
    raw = os.environ.get("OPENSHIP_LEDGER_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    home = Path(os.environ.get("PRAISONAI_HOME", Path.home() / ".praisonai")).expanduser()
    return home / "openship" / "runs.jsonl"


def append_ledger(entry: Dict[str, Any]) -> None:
    """Append a lightweight metadata record (no diffs or secrets) to the JSONL ledger."""
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **entry,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def load_ledger(limit: int = 100) -> List[Dict[str, Any]]:
    path = _ledger_path()
    if not path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
        except json.JSONDecodeError:
            continue
    return records[-limit:]


def summarize_ledger(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    reviews = [r for r in records if r.get("kind") == "review"]
    stewards = [r for r in records if r.get("kind") == "steward"]
    policies = [r for r in records if r.get("kind") == "policy"]
    sev_counts: Counter[str] = Counter()
    for r in reviews:
        for sev in ("important", "pre_existing", "nit"):
            sev_counts[sev] += int(r.get(sev, 0) or 0)
    passed_policies = sum(1 for r in policies if r.get("passed"))
    pass_rate = f"{round(100 * passed_policies / len(policies))}%" if policies else "—"
    return {
        "total_reviews": len(reviews),
        "important_caught": sev_counts["important"],
        "steward_cycles": len(stewards),
        "policy_checks": len(policies),
        "policy_pass_rate": pass_rate,
        "severity_chart": [
            {"severity": "Important", "count": sev_counts["important"]},
            {"severity": "Pre-existing", "count": sev_counts["pre_existing"]},
            {"severity": "Nit", "count": sev_counts["nit"]},
        ],
    }


def resolve_policy_path(repo: Path, policy_path: Optional[str]) -> Optional[str]:
    """Validate an optional repo-relative policy path using shared path_safety."""
    if policy_path is None or not str(policy_path).strip():
        return None
    from praisonaiagents.tools.path_safety import resolve_inside

    resolved = resolve_inside(repo, str(policy_path).strip())
    return str(resolved)


def _default_base_branch(runner: Callable) -> str:
    """Return the full default branch name (e.g. ``main`` or ``release/2.x``)."""
    base_ref = runner(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], capture_output=True, text=True)
    if base_ref.returncode == 0:
        ref = base_ref.stdout.strip()
        prefix = "refs/remotes/origin/"
        if ref.startswith(prefix) and ref[len(prefix):]:
            return ref[len(prefix):]
    return "main"


def get_repo_status(repo: Path, run: Optional[Callable] = None) -> RepoStatus:
    runner = run or _run_in(repo)
    st = RepoStatus(repo=str(repo))
    br = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    if br.returncode != 0:
        st.error = (br.stderr or br.stdout or "not a git repository").strip()
        return st
    st.branch = br.stdout.strip()
    porcelain = runner(["git", "status", "--porcelain"], capture_output=True, text=True)
    if porcelain.returncode == 0:
        st.dirty_files = [ln[3:].strip() for ln in porcelain.stdout.splitlines() if ln.strip()]
    st.base = _default_base_branch(runner)
    gh = runner(["gh", "pr", "view", "--json", "number,title,url,state,isDraft"], capture_output=True, text=True)
    if gh.returncode == 0 and gh.stdout.strip():
        try:
            st.current_pr = json.loads(gh.stdout)
            st.gh_ready = True
        except json.JSONDecodeError:
            pass
    else:
        auth = runner(["gh", "auth", "status"], capture_output=True, text=True)
        st.gh_ready = auth.returncode == 0
    return st


def list_prs(repo: Path, *, limit: int = 12, run: Optional[Callable] = None) -> Tuple[List[Dict[str, Any]], str]:
    runner = run or _run_in(repo)
    capped = max(1, min(int(limit), 50))
    proc = runner(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            str(capped),
            "--json",
            "number,title,state,isDraft,headRefName,updatedAt,url",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout or "gh pr list unavailable").strip()
    try:
        items = json.loads(proc.stdout or "[]")
        return (items if isinstance(items, list) else []), ""
    except json.JSONDecodeError as exc:
        return [], f"invalid gh output: {exc}"


def split_unified_diff(unified_diff: str, *, max_files: int = _MAX_DIFF_FILES) -> List[FileDiff]:
    """Split a unified git/PR diff into per-file (before, after) pairs for ui.diff_viewer."""
    files: List[FileDiff] = []
    cur_path: Optional[str] = None
    before_lines: List[str] = []
    after_lines: List[str] = []

    def _flush() -> None:
        if cur_path and (before_lines or after_lines):
            files.append(FileDiff(cur_path, "\n".join(before_lines), "\n".join(after_lines)))

    for line in unified_diff.splitlines():
        if line.startswith("diff --git "):
            _flush()
            if len(files) >= max_files:
                cur_path = None
                break
            parts = line.split(" ")
            cur_path = parts[-1][2:] if len(parts) >= 4 and parts[-1].startswith("b/") else parts[-1]
            before_lines, after_lines = [], []
        elif line.startswith("+++ b/"):
            if not cur_path:
                cur_path = line[6:].strip()
        elif cur_path is None:
            continue
        elif line.startswith(("--- ", "+++ ", "index ", "new file ", "deleted file ", "similarity ", "rename ")):
            continue
        elif line.startswith("@@"):
            if before_lines or after_lines:
                before_lines.append("...")
                after_lines.append("...")
        elif line.startswith("-"):
            before_lines.append(line[1:])
        elif line.startswith("+"):
            after_lines.append(line[1:])
        elif line.startswith(" "):
            before_lines.append(line[1:])
            after_lines.append(line[1:])
    _flush()
    return files[:max_files]


def get_diff_bundle(
    repo: Path, *, pr: Optional[str] = None, run: Optional[Callable] = None
) -> Tuple[str, List[FileDiff], str]:
    """Return (filtered_unified_diff, per_file_diffs, source_label)."""
    from praisonai_code.ship._text import strip_noisy_diff

    runner = run or _run_in(repo)
    pr_num = normalize_pr(pr)
    if pr_num:
        proc = runner(["gh", "pr", "diff", pr_num], capture_output=True, text=True)
        if proc.returncode != 0:
            raise ValueError((proc.stderr or proc.stdout or f"gh pr diff {pr_num} failed").strip())
        raw = proc.stdout
        label = f"PR #{pr_num}"
    else:
        proc = runner(["git", "diff", "HEAD"], capture_output=True, text=True)
        raw = proc.stdout if proc.returncode == 0 else ""
        # Include untracked non-ignored files as added diffs so brand-new files review cleanly
        untracked = runner(["git", "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True)
        if untracked.returncode == 0:
            chunks = [raw] if raw.strip() else []
            for rel in untracked.stdout.splitlines()[:10]:
                fp = repo / rel
                if fp.is_file() and fp.stat().st_size <= 32_000:
                    text = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                    chunks.append(
                        f"diff --git a/{rel} b/{rel}\n--- /dev/null\n+++ b/{rel}\n"
                        f"@@ -0,0 +1,{len(text)} @@\n" + "\n".join(f"+{ln}" for ln in text)
                    )
            raw = "\n".join(chunks)
        label = "working branch"
        if not raw.strip():
            # Fall back to committed feature-branch diff against origin/<base> (or local <base> if remote missing)
            base_name = _default_base_branch(runner)
            for ref in (f"origin/{base_name}", base_name):
                bdiff = runner(["git", "diff", f"{ref}...HEAD"], capture_output=True, text=True)
                if bdiff.returncode == 0:
                    if bdiff.stdout.strip():
                        raw = bdiff.stdout
                        label = f"branch vs {ref}"
                    break
    cleaned = strip_noisy_diff(raw)[:_MAX_DIFF_CHARS]
    return cleaned, split_unified_diff(cleaned), label


def run_dry_run(repo: Path, *, pr: Optional[str] = None, run: Optional[Callable] = None) -> str:
    from praisonai_code.ship import orchestrate

    runner = run or _run_in(repo)
    res = orchestrate.ship(normalize_pr(pr), dry_run=True, run=runner)
    return res.dry_run_plan or "No changes to ship."


def run_review(
    repo: Path,
    *,
    pr: Optional[str] = None,
    effort: str = "high",
    model: Optional[str] = None,
    run: Optional[Callable] = None,
    review_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    from praisonai_code.ship.review import load_review_guidelines, review_diff, review_severity

    if effort not in _EFFORTS:
        raise ValueError(f"effort must be one of {', '.join(_EFFORTS)}")
    runner = run or _run_in(repo)
    pr_num = normalize_pr(pr)
    diff_text, file_diffs, label = get_diff_bundle(repo, pr=pr_num, run=runner)
    if not diff_text.strip():
        return {"source": label, "pr": pr_num, "severity": "none", "findings": [], "diff": "", "files": []}
    if review_fn is not None:
        findings = review_fn(diff_text, effort=effort, llm=(model or None))
    else:
        base_name = _default_base_branch(runner)
        guidelines = load_review_guidelines(base=base_name, repo_root=repo, run=runner)
        findings = review_diff(diff_text, effort=effort, llm=(model or None), guidelines=(guidelines or None))
    sev = review_severity(findings)
    counts = Counter(f.severity for f in findings)
    append_ledger(
        {
            "kind": "review",
            "repo": repo.name,
            "pr": pr_num or "local",
            "effort": effort,
            "model": model or "default",
            "severity": sev,
            "total": len(findings),
            "important": counts["important"],
            "pre_existing": counts["pre_existing"],
            "nit": counts["nit"],
        }
    )
    return {
        "source": label,
        "pr": pr_num,
        "effort": effort,
        "model": model or "default",
        "severity": sev,
        "findings": [f.model_dump() for f in findings],
        "diff": diff_text,
        "files": file_diffs,
    }


def post_review_comment(
    repo: Path,
    *,
    pr: str,
    findings: List[Dict[str, Any]],
    severity: str,
    confirm: bool = False,
    run: Optional[Callable] = None,
) -> str:
    if not confirm:
        raise ValueError("Confirmation required before posting a review comment to GitHub.")
    pr_num = normalize_pr(pr)
    if not pr_num:
        raise ValueError("A PR number is required to post a review comment.")
    rows = [
        f"- **[{f.get('severity', 'important')}]** `{f.get('path', '')}"
        f"{':' + str(f['line']) if f.get('line') else ''}`: {f.get('title', '')}"
        + (f" — {f['fix']}" if f.get("fix") else "")
        for f in findings
    ]
    body = f"### OpenShip self-review (severity: `{severity}`)\n\n" + (
        "\n".join(rows) if rows else "No issues found."
    )
    runner = run or _run_in(repo)
    proc = runner(["gh", "pr", "comment", pr_num, "--body", body], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError((proc.stderr or proc.stdout or "gh pr comment failed").strip())
    append_ledger({"kind": "review_posted", "repo": repo.name, "pr": pr_num, "severity": severity})
    return f"Posted OpenShip self-review comment on PR #{pr_num}."


def create_draft_pr(
    repo: Path,
    *,
    effort: str = "high",
    model: Optional[str] = None,
    message: Optional[str] = None,
    post_review: bool = False,
    confirm: bool = False,
    run: Optional[Callable] = None,
) -> Dict[str, Any]:
    if not confirm:
        raise ValueError("Confirmation required before committing, pushing, and opening a draft PR.")
    from praisonai_code.ship import orchestrate

    runner = run or _run_in(repo)
    res = orchestrate.ship(
        None,
        message=(message or None),
        dry_run=False,
        effort=effort,
        model=(model or None),
        review=True,
        post_review=post_review,
        watch=False,
        run=runner,
    )
    append_ledger(
        {
            "kind": "ship",
            "repo": repo.name,
            "pr": res.pr_url,
            "severity": res.severity,
            "findings": len(res.findings),
        }
    )
    return {
        "pr_url": res.pr_url,
        "severity": res.severity,
        "posted_review": res.posted_review,
        "findings": [f.model_dump() for f in res.findings],
    }


def evaluate_pr_policy(
    repo: Path,
    *,
    pr: Optional[str] = None,
    policy_path: Optional[str] = None,
    run: Optional[Callable] = None,
) -> Dict[str, Any]:
    from praisonai_code.ship.approvals import check_pr_policy

    pr_num = normalize_pr(pr)
    safe_policy = resolve_policy_path(repo, policy_path)
    runner = run or _run_in(repo)
    report = check_pr_policy(pr_num, policy_path=safe_policy, run=runner)
    policy_yaml = ""
    if safe_policy and Path(safe_policy).is_file():
        policy_yaml = Path(safe_policy).read_text(encoding="utf-8", errors="replace")
    else:
        for ref in ("origin/main", "main"):
            p = runner(["git", "show", f"{ref}:.praisonai/approvals.yml"], capture_output=True, text=True)
            if p.returncode == 0:
                policy_yaml = p.stdout
                break
    append_ledger(
        {
            "kind": "policy",
            "repo": repo.name,
            "pr": pr_num or "current",
            "mode": report.mode,
            "passed": report.passed,
            "blocking": report.blocking,
            "summary": report.summary,
        }
    )
    return {
        "pr": pr_num or "current",
        "passed": report.passed,
        "mode": report.mode,
        "blocking": report.blocking,
        "summary": report.summary,
        "protected_touched": list(report.protected_touched),
        "verdicts": [
            {"rule": v.rule, "passed": v.passed, "reasons": list(v.reasons)} for v in report.verdicts
        ],
        "policy_yaml": policy_yaml,
    }


def inspect_steward(
    repo: Path, *, pr: Optional[str] = None, max_attempts: int = 3, run: Optional[Callable] = None
) -> Dict[str, Any]:
    from praisonai_code.ship.steward import next_action, read_pr_state

    pr_num = normalize_pr(pr)
    runner = run or _run_in(repo)
    state = read_pr_state(pr_num, run=runner)
    action = next_action(state, {}, max_attempts=max_attempts)
    return {
        "number": state.number,
        "url": state.url,
        "state": state.state,
        "mergeable": state.mergeable,
        "head": state.head,
        "base": state.base,
        "failing": list(state.failing),
        "threads": [
            {"id": t.id, "path": t.path, "line": t.line, "author": t.author, "body": t.body}
            for t in state.threads
        ],
        "next_action": {"kind": action.kind, "key": action.key, "detail": action.detail},
        "max_attempts": max_attempts,
    }


def run_steward_once(
    repo: Path,
    *,
    pr: Optional[str] = None,
    model: Optional[str] = None,
    max_attempts: int = 3,
    confirm: bool = False,
    run: Optional[Callable] = None,
) -> Dict[str, Any]:
    if not confirm:
        raise ValueError("Confirmation required before running a PR Steward cycle.")
    from praisonai_code.ship.steward_loop import watch_pr

    pr_num = normalize_pr(pr)
    runner = run or _run_in(repo)
    events: List[str] = []
    watch_pr(
        pr_num,
        once=True,
        max_attempts=max_attempts,
        llm=(model or None),
        run=runner,
        on_event=events.append,
    )
    revert_sha = ""
    for line in reversed(events):
        if "revert" in line.lower() or "pushed" in line.lower():
            m = _COMMIT_RE.search(line)
            if m:
                revert_sha = m.group(1)
                break
    append_ledger(
        {
            "kind": "steward",
            "repo": repo.name,
            "pr": pr_num or "current",
            "model": model or "default",
            "events_count": len(events),
            "revert_sha": revert_sha,
        }
    )
    return {"pr": pr_num or "current", "events": events, "revert_sha": revert_sha}
