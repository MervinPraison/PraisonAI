"""``praisonai ship`` (S-5): orchestrate draft PR, inline self-review, reviewer request, and optional watch."""

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from praisonai_code.ship import flow, is_ship_disabled
from praisonai_code.ship.flow import ShipRefused
from praisonai_code.ship.review import (
    EFFORTS,
    ReviewFinding,
    load_review_guidelines,
    review_diff,
    review_severity,
)

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class ShipResult:
    pr_url: str
    findings: List[ReviewFinding] = field(default_factory=list)
    severity: str = "none"
    posted_review: bool = False
    watched: bool = False
    reviewer: Optional[str] = None
    dry_run_plan: str = ""


def _format_review(findings: List[ReviewFinding], severity: str) -> str:
    rows = [
        f"- **[{f.severity}]** `{f.path}{f':{f.line}' if f.line else ''}`: {f.title}"
        + (f" — {f.fix}" if f.fix else "")
        for f in findings
    ]
    return f"### Ship self-review (severity: `{severity}`)\n\n" + "\n".join(rows)


def _diff_right_lines(diff_text: str) -> Dict[str, Set[int]]:
    """Map each file path in a unified diff to its valid new-file line numbers for inline comments."""
    valid: Dict[str, Set[int]] = {}
    cur_path: Optional[str] = None
    new_line = 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" ")
            cur_path = parts[-1][2:] if len(parts) >= 4 and parts[-1].startswith("b/") else parts[-1]
            valid.setdefault(cur_path, set())
            new_line = 0
        elif line.startswith("+++ b/"):
            cur_path = line[6:].strip()
            valid.setdefault(cur_path, set())
        elif m := _HUNK_RE.match(line):
            new_line = int(m.group(1))
        elif cur_path and new_line > 0:
            if line.startswith("+") and not line.startswith("+++"):
                valid[cur_path].add(new_line)
                new_line += 1
            elif line.startswith(" "):
                valid[cur_path].add(new_line)
                new_line += 1
    return valid


def post_inline_review(
    pr_url: str,
    findings: List[ReviewFinding],
    severity: str,
    diff_text: str = "",
    *,
    run: Callable = subprocess.run,
) -> bool:
    """Post inline diff comments via GitHub Pull Request Reviews API (event=COMMENT, never APPROVE).

    Falls back cleanly to a summary ``gh pr comment`` if PR metadata is unavailable
    or no finding lands on a diff hunk line.
    """
    if not findings:
        return False
    valid_lines = _diff_right_lines(diff_text) if diff_text else {}
    inline_comments, overflow = [], []
    for f in findings:
        norm_path = f.path.lstrip("./")
        if f.line and f.line in valid_lines.get(norm_path, set()):
            body = f"**[{f.severity.upper()}] {f.title}**" + (f"\n\nSuggested fix: {f.fix}" if f.fix else "")
            inline_comments.append({"path": norm_path, "line": f.line, "side": "RIGHT", "body": body})
        else:
            overflow.append(f)

    if inline_comments:
        meta = run(
            ["gh", "pr", "view", pr_url, "--json", "number,url,headRefOid"],
            capture_output=True,
            text=True,
        )
        if meta.returncode == 0 and (meta.stdout or "").strip():
            try:
                info = json.loads(meta.stdout)
                url_parts = str(info.get("url", "")).split("/")
                owner, name, num = url_parts[3], url_parts[4], info["number"]
                sha = info.get("headRefOid") or ""
                summary = f"### OpenShip self-review (severity: `{severity}`)\n\nPosted {len(inline_comments)} inline finding(s)."
                if overflow:
                    summary += "\n\n**Additional findings:**\n" + "\n".join(
                        f"- **[{f.severity}]** `{f.path}{f':{f.line}' if f.line else ''}`: {f.title}"
                        + (f" — {f.fix}" if f.fix else "")
                        for f in overflow
                    )
                payload: Dict[str, object] = {"event": "COMMENT", "body": summary, "comments": inline_comments}
                if sha:
                    payload["commit_id"] = sha
                posted = run(
                    ["gh", "api", f"repos/{owner}/{name}/pulls/{num}/reviews", "--method", "POST", "--input", "-"],
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                )
                if posted.returncode == 0:
                    return True
            except (ValueError, KeyError, IndexError):
                pass

    return run(
        ["gh", "pr", "comment", pr_url, "--body", _format_review(findings, severity)],
        capture_output=True,
        text=True,
    ).returncode == 0


def ship(
    target: Optional[str] = None, *, message: Optional[str] = None, dry_run: bool = False,
    effort: str = "high", model: Optional[str] = None, review: bool = True,
    post_review: bool = False, watch: bool = False, reviewer: Optional[str] = None,
    run: Callable = subprocess.run, review_fn=None, watch_fn=None, on_event=None,
) -> ShipResult:
    """Commit/push/open a draft PR (or target an existing PR), self-review, and optionally watch."""
    if reason := is_ship_disabled():
        raise ShipRefused(reason)
    if target in EFFORTS:
        effort, target = target, None
    elif target and target.startswith("+"):
        reviewer, target = target[1:].strip() or reviewer, None
    if review and effort not in EFFORTS:
        raise ValueError(f"unknown review effort {effort!r}; use one of {', '.join(EFFORTS)}")
    if target is None:
        out = flow.ship_to_draft_pr(message=message, dry_run=dry_run, run=run, llm=model)
        if dry_run:
            return ShipResult(pr_url="", dry_run_plan=out)
        pr_url = out
    elif target.lstrip("#").isdigit() or "/pull/" in target:
        pr_url = target.lstrip("#") if target.startswith("#") else target
        if dry_run:
            steps = [s for s, on in ((f"add reviewer {reviewer}", reviewer), (f"review ({effort})", review), ("post review", review and post_review), ("watch", watch)) if on]
            return ShipResult(pr_url=pr_url, reviewer=reviewer, dry_run_plan=f"Would run on PR {pr_url}: {', '.join(steps) or 'no-op'}")
    else:
        raise ShipRefused(f"unrecognized target {target!r}; pass a PR number, PR URL, or +reviewer")
    if reviewer:
        run(["gh", "pr", "edit", pr_url, "--add-reviewer", reviewer], capture_output=True, text=True)
    findings, severity, posted = [], "none", False
    if review:
        proc = run(["gh", "pr", "diff", pr_url], capture_output=True, text=True)
        diff_text = proc.stdout if proc.returncode == 0 else ""
        if review_fn is not None:
            findings = review_fn(diff_text, effort=effort, llm=model)
        else:
            guidelines = load_review_guidelines(run=run)
            findings = review_diff(diff_text, effort=effort, llm=model, guidelines=(guidelines or None))
        severity = review_severity(findings)
        if post_review and findings:
            posted = post_inline_review(pr_url, findings, severity, diff_text, run=run)
    if watch:
        if watch_fn is None:
            from praisonai_code.ship.steward_loop import watch_pr as watch_fn
        watch_fn(pr_url, llm=model, run=run, **({"on_event": on_event} if on_event is not None else {}))
    return ShipResult(pr_url, findings, severity, posted, bool(watch), reviewer)
