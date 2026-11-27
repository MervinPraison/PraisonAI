"""OpenShip PraisonAIUI plugin (entry point ``praisonaiui.plugins``).

Pure-Python ``kind="blocks"`` extension living inside ``praisonai-code``:
uses only PraisonAIUI's built-in block SDK (zero custom JS/CSS build, zero
core changes to PraisonAIUI, automatic light/dark/mobile styling, and
automatic auth across every PraisonAIUI auth mode).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from praisonaiui import ui
from praisonaiui.plugin_registry import (
    NavGroupSpec,
    PageSpec,
    SettingsField,
    SettingsSectionSpec,
    get_plugin_settings,
)

from . import ui_service as service

__all__ = ["OpenShipPlugin", "plugin"]
__version__ = "0.2.2"

_SAFETY_TEXT = "Draft PRs only · Never merges, approves, or force-pushes. Humans always merge."
_LAST_REVIEW: Dict[str, Dict[str, Any]] = {}


def _prefs() -> Dict[str, Any]:
    try:
        return get_plugin_settings("openship", "defaults")
    except Exception:
        return {"default_model": "", "default_effort": "high", "steward_max_attempts": 3, "policy_path": ""}


def _truthy(val: Any) -> bool:
    return val if isinstance(val, bool) else str(val or "").strip().lower() in {"1", "true", "yes", "on"}


async def _read_json(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _header(title: str, subtitle: str) -> List[dict]:
    return [
        ui.header(title, level=2),
        ui.caption(subtitle),
        ui.alert(_SAFETY_TEXT, variant="info", title="OpenShip Safety Guarantee"),
    ]


# ── Pure block page builders ─────────────────────────────────────────────────


def build_overview_page(
    *,
    repo_status: service.RepoStatus,
    prs: List[Dict[str, Any]],
    prs_error: str,
    ledger: List[Dict[str, Any]],
    settings: Dict[str, Any],
) -> dict:
    summary = service.summarize_ledger(ledger)
    active_step = 2 if repo_status.current_pr else (1 if repo_status.dirty_files else 0)
    blocks = _header(
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
            ui.chart("Findings by Severity", data=summary["severity_chart"], chart_type="bar", x="severity", y="count", height=220)
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
        blocks.append(
            ui.timeline(
                [
                    {
                        "title": f"{str(r.get('kind', 'event')).title()} · PR #{r.get('pr', 'local')}",
                        "description": r.get("summary") or f"severity={r.get('severity', '—')} · model={r.get('model', '—')}",
                        "timestamp": r.get("timestamp", ""),
                        "badge": str(r.get("severity") or r.get("mode") or r.get("kind") or ""),
                        "status": "error" if r.get("severity") == "high" or r.get("blocking") else ("success" if r.get("passed") else "info"),
                    }
                    for r in reversed(ledger[-10:])
                ],
                title="Recent OpenShip Activity",
            )
        )
    blocks.append(ui.button_group([{"label": "Refresh Overview", "variant": "outline", "action": "refresh"}]))
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
    blocks = _header(
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
                        ui.text_input("PR Number (blank = current branch)", value=pr, placeholder="e.g. 6852", name="pr"),
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
                        ui.text_input("Model (blank = default)", value=model, placeholder="gpt-4o-mini or ollama/qwen3.5:9b", name="model"),
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
        blocks.extend([ui.header("Dry-Run Plan", level=3), ui.code_block(dry_run_plan, language="text")])
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
                f"Source: {review_result.get('source', '')} · Model: {review_result.get('model', 'default')} · Findings: {len(findings)}",
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
                    children=[ui.diff_viewer(fd.before, fd.after, title=fd.path, before_label="Base", after_label="Proposed")],
                    expanded=(idx == 0),
                )
            )
    if diff_text:
        blocks.append(ui.expander("Raw Filtered Unified Diff", children=[ui.code_block(diff_text, language="diff")], expanded=False))
    blocks.append(
        ui.expander(
            "GitHub Write Actions (Confirmation Required)",
            children=[
                ui.form(
                    "write_action",
                    children=[
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
                    ],
                    submit_label="Execute Confirmed Action",
                )
            ],
            expanded=False,
        )
    )
    return ui.layout(blocks, params={"pr": pr or None, "effort": effort})


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
    blocks = _header(
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
            children=[ui.text_input("PR Number (blank = current branch PR)", value=pr, placeholder="e.g. 6852", name="pr")],
            submit_label="Inspect PR",
            method="get",
        )
    )
    if state:
        pr_state = str(state.get("state", "UNKNOWN"))
        next_act = state.get("next_action") or {}
        job_state = (
            "done"
            if pr_state == "MERGED" or next_act.get("kind") == "wait"
            else ("failed" if state.get("failing") or state.get("mergeable") == "CONFLICTING" else "running")
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
        if state.get("failing"):
            blocks.extend([ui.header("Failing CI Checks", level=3), ui.table(headers=["Check"], rows=[[n] for n in state["failing"]])])
        if state.get("threads"):
            blocks.extend(
                [
                    ui.header("Unresolved Review Threads", level=3),
                    ui.table(
                        headers=["File", "Author", "Latest Comment"],
                        rows=[
                            [
                                f"{t.get('path', '')}:{t['line']}" if t.get("line") else str(t.get("path", "")),
                                str(t.get("author", "")),
                                str(t.get("body", ""))[:160],
                            ]
                            for t in state["threads"]
                        ],
                    ),
                ]
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
    blocks = _header(
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
                        ui.text_input("PR Number (blank = current branch PR)", value=pr, placeholder="e.g. 6852", name="pr"),
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
        passed, blocking = bool(report.get("passed")), bool(report.get("blocking"))
        variant = "success" if passed else ("error" if blocking else "warning")
        blocks.append(
            ui.alert(
                str(report.get("summary", "")),
                variant=variant,
                title=f"PR #{report.get('pr')} · Mode: {str(report.get('mode', 'observe')).upper()}"
                + (" (BLOCKING)" if blocking else " (non-blocking)"),
            )
        )
        if report.get("verdicts"):
            blocks.append(
                ui.table(
                    headers=["Rule", "Status", "Details"],
                    rows=[
                        [
                            str(v.get("rule", "")),
                            "PASS" if v.get("passed") else "FAIL",
                            "; ".join(v.get("reasons") or []) or "All requirements satisfied",
                        ]
                        for v in report["verdicts"]
                    ],
                )
            )
        if report.get("protected_touched"):
            blocks.append(
                ui.alert(
                    "Touched protected paths (requires human approval): " + ", ".join(report["protected_touched"]),
                    variant="warning",
                    title="Protected Paths Matched",
                )
            )
        if report.get("policy_yaml"):
            blocks.append(ui.expander("Active approvals.yml Policy", children=[ui.code_block(report["policy_yaml"], language="yaml")], expanded=False))
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


# ── Starlette routes ─────────────────────────────────────────────────────────


async def _overview_get(request: Request) -> JSONResponse:
    repo = service.get_repo_root()
    prefs = _prefs()
    status, (prs, prs_err), ledger = await asyncio.gather(
        asyncio.to_thread(service.get_repo_status, repo),
        asyncio.to_thread(service.list_prs, repo),
        asyncio.to_thread(service.load_ledger),
    )
    return JSONResponse(build_overview_page(repo_status=status, prs=prs, prs_error=prs_err, ledger=ledger, settings=prefs))


async def _review_get(request: Request) -> JSONResponse:
    prefs = _prefs()
    repo = service.get_repo_root()
    pr = request.query_params.get("pr", "").strip()
    effort = request.query_params.get("effort", "").strip() or str(prefs.get("default_effort") or "high")
    model = request.query_params.get("model", "").strip() or str(prefs.get("default_model") or "")
    diff_text, file_diffs, err = "", [], ""
    try:
        diff_text, file_diffs, _ = await asyncio.to_thread(service.get_diff_bundle, repo, pr=(pr or None))
    except Exception as exc:
        err = str(exc)
    return JSONResponse(
        build_review_page(pr=pr, effort=effort, model=model, review_result=_LAST_REVIEW.get(pr or "local"), diff_text=diff_text, file_diffs=file_diffs, error=err)
    )


async def _review_action(request: Request) -> JSONResponse:
    body = await _read_json(request)
    prefs = _prefs()
    repo = service.get_repo_root()
    action = str(body.get("action") or "")
    pr = str(body.get("pr") or (body.get("_params") or {}).get("pr") or "").strip()
    effort = str(body.get("effort") or prefs.get("default_effort") or "high").strip()
    model = str(body.get("model") or prefs.get("default_model") or "").strip()
    try:
        if action == "dry_run":
            plan = await asyncio.to_thread(service.run_dry_run, repo, pr=(pr or None))
            diff_text, file_diffs, _ = await asyncio.to_thread(service.get_diff_bundle, repo, pr=(pr or None))
            return JSONResponse({**build_review_page(pr=pr, effort=effort, model=model, dry_run_plan=plan, review_result=_LAST_REVIEW.get(pr or "local"), diff_text=diff_text, file_diffs=file_diffs), "message": "Dry-run plan ready"})
        if action == "load_diff":
            diff_text, file_diffs, _ = await asyncio.to_thread(service.get_diff_bundle, repo, pr=(pr or None))
            return JSONResponse({**build_review_page(pr=pr, effort=effort, model=model, review_result=_LAST_REVIEW.get(pr or "local"), diff_text=diff_text, file_diffs=file_diffs), "message": f"Loaded {len(file_diffs)} changed file(s)"})
        if action == "write_action" or (not action and "write_op" in body):
            confirm = _truthy(body.get("confirm"))
            if str(body.get("write_op") or "ship_draft") == "post_comment":
                cached = _LAST_REVIEW.get(pr or "local") or {}
                msg = await asyncio.to_thread(service.post_review_comment, repo, pr=pr, findings=cached.get("findings") or [], severity=str(cached.get("severity") or "none"), confirm=confirm)
                return JSONResponse({**build_review_page(pr=pr, effort=effort, model=model, review_result=cached, notice=msg), "message": msg})
            ship_res = await asyncio.to_thread(service.create_draft_pr, repo, effort=effort, model=(model or None), message=str(body.get("message") or "").strip() or None, confirm=confirm)
            return JSONResponse({**build_review_page(pr=pr, effort=effort, model=model, ship_result=ship_res, review_result={"source": ship_res.get("pr_url", ""), "severity": ship_res.get("severity", "none"), "findings": ship_res.get("findings") or [], "model": model or "default"}), "message": f"Opened draft PR: {ship_res.get('pr_url', '')}"})
        if action in ("", "run_review"):
            res = await asyncio.to_thread(service.run_review, repo, pr=(pr or None), effort=effort, model=(model or None))
            _LAST_REVIEW[pr or "local"] = res
            return JSONResponse({**build_review_page(pr=pr, effort=effort, model=model, review_result=res, diff_text=res.get("diff", ""), file_diffs=res.get("files") or []), "message": f"Self-review finished: {len(res['findings'])} finding(s)"})
        return JSONResponse({"error": f"Unknown action: {action!r}"}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def _steward_get(request: Request) -> JSONResponse:
    prefs = _prefs()
    repo = service.get_repo_root()
    pr = request.query_params.get("pr", "").strip()
    max_attempts = int(prefs.get("steward_max_attempts") or 3)
    model = str(prefs.get("default_model") or "")
    state, err = None, ""
    try:
        state = await asyncio.to_thread(service.inspect_steward, repo, pr=(pr or None), max_attempts=max_attempts)
    except Exception as exc:
        if pr:
            err = str(exc)
    return JSONResponse(build_steward_page(pr=pr, max_attempts=max_attempts, model=model, state=state, error=err))


async def _steward_action(request: Request) -> JSONResponse:
    body = await _read_json(request)
    prefs = _prefs()
    repo = service.get_repo_root()
    action = str(body.get("action") or "")
    if action not in ("", "steward_once"):
        return JSONResponse({"error": f"Unknown action: {action!r}"}, status_code=400)
    pr = str(body.get("pr") or (body.get("_params") or {}).get("pr") or "").strip()
    max_attempts = int(prefs.get("steward_max_attempts") or 3)
    model = str(body.get("model") or prefs.get("default_model") or "").strip()
    try:
        res = await asyncio.to_thread(service.run_steward_once, repo, pr=(pr or None), model=(model or None), max_attempts=max_attempts, confirm=_truthy(body.get("confirm")))
        state = None
        try:
            state = await asyncio.to_thread(service.inspect_steward, repo, pr=(pr or None), max_attempts=max_attempts)
        except Exception:
            pass
        return JSONResponse({**build_steward_page(pr=pr, max_attempts=max_attempts, model=model, state=state, events=res.get("events") or [], revert_sha=res.get("revert_sha", ""), notice=f"Completed Steward cycle ({len(res.get('events') or [])} event(s))"), "message": "Steward cycle completed"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def _policy_get(request: Request) -> JSONResponse:
    prefs = _prefs()
    repo = service.get_repo_root()
    pr = request.query_params.get("pr", "").strip()
    policy_path = request.query_params.get("policy_path", "").strip() or str(prefs.get("policy_path") or "")
    ledger = await asyncio.to_thread(service.load_ledger)
    report, err = None, ""
    if pr:
        try:
            report = await asyncio.to_thread(service.evaluate_pr_policy, repo, pr=pr, policy_path=(policy_path or None))
        except Exception as exc:
            err = str(exc)
    return JSONResponse(build_policy_page(pr=pr, policy_path=policy_path, report=report, ledger=ledger, error=err))


async def _policy_action(request: Request) -> JSONResponse:
    body = await _read_json(request)
    prefs = _prefs()
    repo = service.get_repo_root()
    pr = str(body.get("pr") or (body.get("_params") or {}).get("pr") or "").strip()
    policy_path = str(body.get("policy_path") or prefs.get("policy_path") or "").strip()
    try:
        report = await asyncio.to_thread(service.evaluate_pr_policy, repo, pr=(pr or None), policy_path=(policy_path or None))
        ledger = await asyncio.to_thread(service.load_ledger)
        return JSONResponse({**build_policy_page(pr=pr, policy_path=policy_path, report=report, ledger=ledger), "message": f"Policy evaluated: {report.get('summary', '')}"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# ── Plugin descriptor ────────────────────────────────────────────────────────


class OpenShipPlugin:
    """Native PraisonAIUI plugin shipped directly by ``praisonai-code``."""

    name = "openship"
    version = __version__
    sdk = 1

    def pages(self) -> List[PageSpec]:
        return [
            PageSpec(id="openship", title="Overview", kind="blocks", icon="ship", nav_icon="ship", group="OpenShip", order=220, description="OpenShip PR queue, pipeline stepper, and review analytics", page_type="overview"),
            PageSpec(id="openship-review", title="Self-Review", kind="blocks", icon="scan-search", nav_icon="scan-search", group="OpenShip", order=221, description="Diff viewer and AI self-review on any LLM or local Ollama", page_type="editor"),
            PageSpec(id="openship-steward", title="PR Steward", kind="blocks", icon="wrench", nav_icon="wrench", group="OpenShip", order=222, description="Failing CI checks, conflicts, review threads, and 3-attempt circuit breaker", page_type="log"),
            PageSpec(id="openship-policy", title="PR Policy", kind="blocks", icon="shield-check", nav_icon="shield-check", group="OpenShip", order=223, description="Declarative .praisonai/approvals.yml evaluation and observe-mode audit", page_type="list"),
        ]

    def nav_groups(self) -> List[NavGroupSpec]:
        return [NavGroupSpec(name="OpenShip", order=220)]

    def settings(self) -> List[SettingsSectionSpec]:
        return [
            SettingsSectionSpec(
                id="defaults",
                title="OpenShip",
                description="Default model, review effort, circuit-breaker limit, and optional policy preview path.",
                fields=(
                    SettingsField(key="default_model", label="Default LLM model", default="", description="e.g. gpt-4o-mini or ollama/qwen3.5:9b"),
                    SettingsField(key="default_effort", label="Default review effort", type="select", default="high", options=("low", "medium", "high", "xhigh", "max")),
                    SettingsField(key="steward_max_attempts", label="Steward max attempts", type="number", default=3, description="Circuit-breaker cap per failing check or review thread"),
                    SettingsField(key="policy_path", label="Optional local policy preview path", default="", description="Repo-relative YAML path; blank reads origin/<base>:.praisonai/approvals.yml"),
                ),
            )
        ]

    def routes(self) -> List[Route]:
        return [
            Route("/pages/openship", _overview_get, methods=["GET"]),
            Route("/pages/openship/action", _overview_get, methods=["POST"]),
            Route("/pages/openship-review", _review_get, methods=["GET"]),
            Route("/pages/openship-review/action", _review_action, methods=["POST"]),
            Route("/pages/openship-steward", _steward_get, methods=["GET"]),
            Route("/pages/openship-steward/action", _steward_action, methods=["POST"]),
            Route("/pages/openship-policy", _policy_get, methods=["GET"]),
            Route("/pages/openship-policy/action", _policy_action, methods=["POST"]),
        ]

    def cli_commands(self):
        import typer

        cli = typer.Typer(help="OpenShip UI commands for PraisonAIUI", add_completion=False)

        @cli.command()
        def serve(
            repo: Optional[str] = typer.Option(None, "--repo", help="Git repository path (default: current directory)"),
            host: str = typer.Option("127.0.0.1", "--host", help="Bind address (loopback by default)"),
            port: int = typer.Option(8765, "--port", help="HTTP port"),
            with_chat: bool = typer.Option(False, "--with-chat/--no-chat", help="Include built-in Chat tab"),
        ) -> None:
            """Launch a focused PraisonAIUI app shell showing only OpenShip pages."""
            import uvicorn
            import praisonaiui as aiui
            from praisonaiagents.agent.launch_security import require_bind_token
            from praisonaiui.server import create_app

            token = require_bind_token(
                host,
                os.environ.get("GATEWAY_AUTH_TOKEN"),
                server="aiui openship serve",
                hint="Set GATEWAY_AUTH_TOKEN",
            )
            if token:
                os.environ.setdefault("AIUI_REQUIRE_TOKEN", "1")
            if repo:
                os.environ["OPENSHIP_REPO"] = str(Path(repo).expanduser().resolve())
            aiui.set_style("app")
            aiui.register_plugin(plugin)
            if with_chat:
                aiui.only_my_pages("chat")
            else:
                aiui.only_my_pages()
            app = create_app(config={"site": {"title": "OpenShip — PraisonAI"}})
            uvicorn.run(app, host=host, port=port)

        @cli.command()
        def status() -> None:
            """Print active repository and OpenShip ledger summary."""
            repo = service.get_repo_root()
            st = service.get_repo_status(repo)
            summary = service.summarize_ledger(service.load_ledger())
            typer.echo(f"repo={st.repo} branch={st.branch} gh_ready={st.gh_ready} reviews={summary['total_reviews']}")

        return cli


plugin = OpenShipPlugin()
