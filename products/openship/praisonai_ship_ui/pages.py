"""Pure-Python PraisonAIUI block builders for OpenShip (zero custom JS/CSS).

Every page composes built-in ``praisonaiui.ui`` components so the React app
shell renders them with native DESIGN.md tokens, light + dark mode, 390px
mobile responsiveness, WCAG AA contrast, and automatic XSS escaping.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from praisonaiui import ui

from . import service

_SAFETY_TEXT = "Draft PRs only · Never merges, approves, or force-pushes. Humans always merge."


def _header_block(title: str, subtitle: str) -> List[dict]:
    return [
        ui.header(title, level=2),
        ui.caption(subtitle),
        ui.alert(_SAFETY_TEXT, variant="info", title="OpenShip Safety Guarantee"),
    ]


def build_overview_page(
    *,
    repo_status: service.RepoStatus,
    prs: List[Dict[str, Any]],
    prs_error: str,
    ledger: List[Dict[str, Any]],
    settings: Dict[str, Any],
) -> dict:
    summary = service.summarize_ledger(ledger)
    active_step = 0
    if repo_status.current_pr:
        active_step = 2
    elif repo_status.dirty_files:
        active_step = 1

    blocks: List[dict] = _header_block(
        "OpenShip Overview",
        f"Repository: {repo_status.repo} · Branch: {repo_status.branch or '—'} → {repo_status.base}",
    )

    blocks.append(
        ui.stepper(
            [
                {"title": "Draft PR", "description": "Commit, push, open draft"},
                {"title": "Self-Review", "description": "Typed findings on any LLM"},
                {"title": "PR Steward", "description": "CI, conflicts & threads (3-try cap)"},
                {"title": "Policy Check", "description": ".praisonai/approvals.yml"},
            ],
            active=active_step,
            title="OpenShip Pipeline",
        )
    )

    blocks.append(
        ui.stat_group(
            [
                {"label": "Self-Reviews", "value": summary["total_reviews"], "delta": settings.get("default_model") or "any LLM"},
                {"label": "Important Caught", "value": summary["important_caught"]},
                {"label": "Steward Cycles", "value": summary["steward_cycles"]},
                {"label": "Policy Pass Rate", "value": summary["policy_pass_rate"]},
            ]
        )
    )

    blocks.append(
        ui.columns(
            [
                ui.page_link("openship-review", "Open Self-Review & Diff", variant="outline"),
                ui.page_link("openship-steward", "Open PR Steward", variant="outline"),
                ui.page_link("openship-policy", "Open PR Policy", variant="outline"),
            ]
        )
    )

    if any(row["count"] > 0 for row in summary["severity_chart"]):
        blocks.append(
            ui.chart(
                "Findings by Severity",
                data=summary["severity_chart"],
                chart_type="bar",
                x="severity",
                y="count",
                height=220,
            )
        )

    blocks.append(ui.header("Pull Requests", level=3))
    if prs_error:
        blocks.append(ui.alert(prs_error, variant="warning", title="GitHub PR list unavailable"))
    elif prs:
        blocks.append(
            ui.table(
                headers=["PR", "Title", "State", "Draft", "Branch"],
                rows=[
                    [
                        f"#{p.get('number', '')}",
                        str(p.get("title", ""))[:80],
                        str(p.get("state", "")),
                        "Draft" if p.get("isDraft") else "Ready",
                        str(p.get("headRefName", "")),
                    ]
                    for p in prs
                ],
            )
        )
    else:
        blocks.append(ui.empty("No pull requests found for this repository."))

    if ledger:
        timeline_items = [
            {
                "title": f"{str(r.get('kind', 'event')).title()} · PR #{r.get('pr', 'local')}",
                "description": r.get("summary")
                or f"severity={r.get('severity', '—')} · model={r.get('model', '—')}",
                "timestamp": r.get("timestamp", ""),
                "badge": str(r.get("severity") or r.get("mode") or r.get("kind") or ""),
                "status": "error"
                if r.get("severity") == "high" or r.get("blocking")
                else ("success" if r.get("passed") else "info"),
            }
            for r in reversed(ledger[-10:])
        ]
        blocks.append(ui.timeline(timeline_items, title="Recent OpenShip Activity"))

    blocks.append(
        ui.button_group([{"label": "Refresh Overview", "variant": "outline", "action": "refresh"}])
    )
    return ui.layout(blocks)


def build_review_page(
    *,
    pr: str = "",
    effort: str = "high",
    model: str = "",
    dry_run_plan: str = "",
    review_result: Optional[Dict[str, Any]] = None,
    diff_text: str = "",
    file_diffs: Optional[List[service.FileDiff]] = None,
    ship_result: Optional[Dict[str, Any]] = None,
    notice: str = "",
    error: str = "",
) -> dict:
    blocks: List[dict] = _header_block(
        "Self-Review & Diff Inspector",
        "Inspect changes on your current branch or any GitHub PR and run OpenShip Self-Review on any LLM or local Ollama.",
    )

    if error:
        blocks.append(ui.alert(error, variant="error", title="OpenShip Review Error"))
    if notice:
        blocks.append(ui.alert(notice, variant="success", title="Done"))

    blocks.append(
        ui.form(
            "run_review",
            children=[
                ui.columns(
                    [
                        ui.text_input(
                            "PR Number (blank = current branch)",
                            value=pr,
                            placeholder="e.g. 6852",
                            name="pr",
                        ),
                        ui.select_input(
                            "Review Effort",
                            options=[
                                {"value": "low", "label": "Low (important bugs/secrets only)"},
                                {"value": "medium", "label": "Medium (top 5 findings)"},
                                {"value": "high", "label": "High (default, top 10)"},
                                {"value": "xhigh", "label": "Extra High (top 20)"},
                                {"value": "max", "label": "Max (all findings)"},
                            ],
                            value=effort,
                            name="effort",
                        ),
                        ui.text_input(
                            "Model (blank = default)",
                            value=model,
                            placeholder="gpt-4o-mini or ollama/qwen3.5:9b",
                            name="model",
                        ),
                    ]
                )
            ],
            submit_label="Run Self-Review",
            update_url=True,
        )
    )

    blocks.append(
        ui.button_group(
            [
                {"label": "Preview Dry-Run Plan", "variant": "outline", "action": "dry_run"},
                {"label": "Load Diff Only", "variant": "outline", "action": "load_diff"},
            ]
        )
    )

    if dry_run_plan:
        blocks.append(ui.header("Dry-Run Plan", level=3))
        blocks.append(ui.code_block(dry_run_plan, language="text"))

    if ship_result:
        blocks.append(
            ui.alert(
                f"Draft PR opened: {ship_result.get('pr_url', '')} · Severity: {ship_result.get('severity', 'none')}",
                variant="success",
                title="Ship Completed (Draft Only)",
            )
        )

    if review_result is not None:
        findings = review_result.get("findings") or []
        sev = str(review_result.get("severity", "none")).upper()
        variant = "error" if sev == "HIGH" else ("warning" if sev == "MINIMAL" else "success")
        blocks.append(
            ui.alert(
                f"Source: {review_result.get('source', '')} · Model: {review_result.get('model', 'default')} · "
                f"Findings: {len(findings)}",
                variant=variant,
                title=f"Self-Review Severity: {sev}",
            )
        )
        if findings:
            blocks.append(
                ui.table(
                    headers=["Severity", "Location", "Finding", "Suggested Fix"],
                    rows=[
                        [
                            str(f.get("severity", "")).upper(),
                            f"{f.get('path', '')}:{f['line']}" if f.get("line") else str(f.get("path", "")),
                            str(f.get("title", "")),
                            str(f.get("fix", "")),
                        ]
                        for f in findings
                    ],
                )
            )
        else:
            blocks.append(ui.empty("No issues found in this diff."))

    if file_diffs:
        blocks.append(ui.header(f"Changed Files ({len(file_diffs)})", level=3))
        for idx, fd in enumerate(file_diffs):
            blocks.append(
                ui.expander(
                    fd.path,
                    children=[
                        ui.diff_viewer(
                            fd.before,
                            fd.after,
                            title=fd.path,
                            before_label="Base",
                            after_label="Proposed",
                        )
                    ],
                    expanded=(idx == 0),
                )
            )

    if diff_text:
        blocks.append(
            ui.expander(
                "Raw Filtered Unified Diff",
                children=[ui.code_block(diff_text, language="diff")],
                expanded=False,
            )
        )

    # Explicit confirmation gate for any GitHub write action
    write_fields: List[dict] = [
        ui.select_input(
            "Write Action",
            options=[
                {"value": "ship_draft", "label": "Commit, push & open Draft PR (never merges)"},
                {"value": "post_comment", "label": "Post latest self-review comment to PR"},
            ],
            value="post_comment" if pr else "ship_draft",
            name="write_op",
        ),
        ui.text_input("Optional Commit Message (for Draft PR)", value="", placeholder="feat: ...", name="message"),
        ui.checkbox_input(
            "I confirm this write action (draft PR / comment only — never merges)",
            checked=False,
            name="confirm",
        ),
    ]
    blocks.append(
        ui.expander(
            "GitHub Write Actions (Confirmation Required)",
            children=[ui.form("write_action", children=write_fields, submit_label="Execute Confirmed Action")],
            expanded=False,
        )
    )

    params: Dict[str, Any] = {"pr": pr or None, "effort": effort}
    return ui.layout(blocks, params=params)


def build_steward_page(
    *,
    pr: str = "",
    max_attempts: int = 3,
    model: str = "",
    state: Optional[Dict[str, Any]] = None,
    events: Optional[List[str]] = None,
    revert_sha: str = "",
    notice: str = "",
    error: str = "",
) -> dict:
    blocks: List[dict] = _header_block(
        "PR Steward",
        "Inspect failing CI checks, merge conflicts, and unresolved review threads with a 3-attempt circuit breaker.",
    )

    if error:
        blocks.append(ui.alert(error, variant="error", title="Steward Error"))
    if notice:
        blocks.append(ui.alert(notice, variant="success", title="Steward Cycle Finished"))

    blocks.append(
        ui.form(
            "select_pr",
            children=[
                ui.text_input(
                    "PR Number (blank = current branch PR)",
                    value=pr,
                    placeholder="e.g. 6852",
                    name="pr",
                )
            ],
            submit_label="Inspect PR",
            method="get",
        )
    )

    if state:
        pr_state = str(state.get("state", "UNKNOWN"))
        next_act = state.get("next_action") or {}
        job_state = "done" if pr_state == "MERGED" or next_act.get("kind") == "wait" else (
            "failed" if state.get("failing") or state.get("mergeable") == "CONFLICTING" else "running"
        )
        blocks.append(
            ui.status(
                f"PR #{state.get('number')} ({pr_state})",
                state=job_state,
                detail=f"Next steward action: {next_act.get('kind', '—')} — {next_act.get('detail', '')}",
                log=events or None,
            )
        )
        blocks.append(
            ui.key_value_list(
                [
                    {"key": "PR URL", "value": str(state.get("url", ""))},
                    {"key": "Branch", "value": f"{state.get('head', '')} → {state.get('base', '')}"},
                    {"key": "Mergeable", "value": str(state.get("mergeable", "UNKNOWN"))},
                    {"key": "Failing Checks", "value": str(len(state.get("failing") or []))},
                    {"key": "Unresolved Threads", "value": str(len(state.get("threads") or []))},
                    {"key": "Circuit Breaker Cap", "value": f"{max_attempts} attempt(s) per check/thread"},
                ],
                title="PR State",
            )
        )
        if state.get("url"):
            blocks.append(ui.link_button("Open PR on GitHub", href=str(state["url"]), external=True))

        failing = state.get("failing") or []
        if failing:
            blocks.append(ui.header("Failing CI Checks", level=3))
            blocks.append(ui.table(headers=["Check"], rows=[[name] for name in failing]))

        threads = state.get("threads") or []
        if threads:
            blocks.append(ui.header("Unresolved Review Threads", level=3))
            blocks.append(
                ui.table(
                    headers=["File", "Author", "Latest Comment"],
                    rows=[
                        [
                            f"{t.get('path', '')}:{t['line']}" if t.get("line") else str(t.get("path", "")),
                            str(t.get("author", "")),
                            str(t.get("body", ""))[:160],
                        ]
                        for t in threads
                    ],
                )
            )
    elif not error:
        blocks.append(ui.empty("Enter a PR number above (or check out a branch with an open PR) to inspect Steward state."))

    if revert_sha:
        blocks.append(ui.copy_field(f"git revert {revert_sha}", label="One-Click Revert Command"))

    blocks.append(
        ui.expander(
            "Run Single Steward Cycle (--once, Confirmation Required)",
            children=[
                ui.form(
                    "steward_once",
                    children=[
                        ui.text_input("PR Number", value=pr, placeholder="e.g. 6852", name="pr"),
                        ui.text_input("Model (blank = default)", value=model, placeholder="gpt-4o-mini", name="model"),
                        ui.checkbox_input(
                            "I confirm running one Steward cycle (may push fix commits; never merges or force-pushes)",
                            checked=False,
                            name="confirm",
                        ),
                    ],
                    submit_label="Run Steward --once",
                )
            ],
            expanded=False,
        )
    )

    return ui.layout(blocks, params={"pr": pr or None})


def build_policy_page(
    *,
    pr: str = "",
    policy_path: str = "",
    report: Optional[Dict[str, Any]] = None,
    ledger: Optional[List[Dict[str, Any]]] = None,
    error: str = "",
) -> dict:
    blocks: List[dict] = _header_block(
        "Declarative PR Policy & Approvals",
        "Evaluate any PR against .praisonai/approvals.yml loaded strictly from origin/<base> (observe or enforce mode).",
    )

    if error:
        blocks.append(ui.alert(error, variant="error", title="Policy Evaluation Error"))

    blocks.append(
        ui.form(
            "evaluate_policy",
            children=[
                ui.columns(
                    [
                        ui.text_input(
                            "PR Number (blank = current branch PR)",
                            value=pr,
                            placeholder="e.g. 6852",
                            name="pr",
                        ),
                        ui.text_input(
                            "Optional Repo-Relative Policy Preview Path",
                            value=policy_path,
                            placeholder="products/openship/examples/approvals.yml",
                            name="policy_path",
                        ),
                    ]
                )
            ],
            submit_label="Evaluate PR Policy",
            update_url=True,
        )
    )

    if report:
        passed = bool(report.get("passed"))
        blocking = bool(report.get("blocking"))
        variant = "success" if passed else ("error" if blocking else "warning")
        blocks.append(
            ui.alert(
                str(report.get("summary", "")),
                variant=variant,
                title=f"PR #{report.get('pr')} · Mode: {str(report.get('mode', 'observe')).upper()}"
                + (" (BLOCKING)" if blocking else " (non-blocking)"),
            )
        )
        verdicts = report.get("verdicts") or []
        if verdicts:
            blocks.append(
                ui.table(
                    headers=["Rule", "Status", "Details"],
                    rows=[
                        [
                            str(v.get("rule", "")),
                            "PASS" if v.get("passed") else "FAIL",
                            "; ".join(v.get("reasons") or []) or "All requirements satisfied",
                        ]
                        for v in verdicts
                    ],
                )
            )
        if report.get("protected_touched"):
            blocks.append(
                ui.alert(
                    "Touched protected paths (requires human approval): "
                    + ", ".join(report["protected_touched"]),
                    variant="warning",
                    title="Protected Paths Matched",
                )
            )
        if report.get("policy_yaml"):
            blocks.append(
                ui.expander(
                    "Active approvals.yml Policy",
                    children=[ui.code_block(report["policy_yaml"], language="yaml")],
                    expanded=False,
                )
            )

    policy_history = [r for r in (ledger or []) if r.get("kind") == "policy"]
    if policy_history:
        blocks.append(
            ui.timeline(
                [
                    {
                        "title": f"PR #{r.get('pr')} — {r.get('summary', '')}",
                        "timestamp": r.get("timestamp", ""),
                        "badge": str(r.get("mode", "observe")),
                        "status": "success" if r.get("passed") else ("error" if r.get("blocking") else "warning"),
                    }
                    for r in reversed(policy_history[-10:])
                ],
                title="Observe & Enforce Audit History",
            )
        )

    return ui.layout(blocks, params={"pr": pr or None, "policy_path": policy_path or None})
