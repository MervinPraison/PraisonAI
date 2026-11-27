"""``praisonai ship`` (S-5): orchestrate draft PR, self-review, reviewer request, and optional watch."""

import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from praisonai_code.ship import flow, is_ship_disabled
from praisonai_code.ship.flow import ShipRefused
from praisonai_code.ship.review import ReviewFinding, review_diff, review_severity


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
    rows = [f"- **[{f.severity}]** `{f.path}{f':{f.line}' if f.line else ''}`: {f.title}"
            + (f" — {f.fix}" if f.fix else "") for f in findings]
    return f"### Ship self-review (severity: `{severity}`)\n\n" + "\n".join(rows)


def ship(
    target: Optional[str] = None, *, message: Optional[str] = None, dry_run: bool = False,
    effort: str = "high", model: Optional[str] = None, review: bool = True,
    post_review: bool = False, watch: bool = False, reviewer: Optional[str] = None,
    run: Callable = subprocess.run, review_fn=None, watch_fn=None,
) -> ShipResult:
    """Commit/push/open a draft PR (or target an existing PR), self-review, and optionally watch."""
    if reason := is_ship_disabled():
        raise ShipRefused(reason)
    if target and target.startswith("+"):
        reviewer, target = target[1:].strip() or reviewer, None
    if target is None:
        out = flow.ship_to_draft_pr(message=message, dry_run=dry_run, run=run, llm=model)
        if dry_run:
            return ShipResult(pr_url="", dry_run_plan=out)
        pr_url = out
    elif target.lstrip("#").isdigit() or "/pull/" in target:
        pr_url = target.lstrip("#") if target.startswith("#") else target
        if dry_run:
            steps = [s for s, on in ((f"add reviewer {reviewer}", reviewer), (f"review ({effort})", review),
                                     ("post review", review and post_review), ("watch", watch)) if on]
            return ShipResult(pr_url=pr_url, reviewer=reviewer,
                              dry_run_plan=f"Would run on PR {pr_url}: {', '.join(steps) or 'no-op'}")
    else:
        raise ShipRefused(f"unrecognized target {target!r}; pass a PR number, PR URL, or +reviewer")
    if reviewer:
        run(["gh", "pr", "edit", pr_url, "--add-reviewer", reviewer], capture_output=True, text=True)
    findings, severity, posted = [], "none", False
    if review:
        proc = run(["gh", "pr", "diff", pr_url], capture_output=True, text=True)
        findings = (review_fn or review_diff)(proc.stdout if proc.returncode == 0 else "", effort=effort, llm=model)
        severity = review_severity(findings)
        if post_review and findings:
            posted = run(["gh", "pr", "comment", pr_url, "--body", _format_review(findings, severity)],
                         capture_output=True, text=True).returncode == 0
    if watch:
        if watch_fn is None:
            from praisonai_code.ship.steward_loop import watch_pr as watch_fn
        watch_fn(pr_url, llm=model, run=run)
    return ShipResult(pr_url, findings, severity, posted, bool(watch), reviewer)
