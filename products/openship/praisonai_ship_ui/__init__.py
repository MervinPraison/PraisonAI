"""OpenShip UI plugin for PraisonAIUI (entry point ``praisonaiui.plugins``).

Pure-Python ``kind="blocks"`` plugin: zero custom JS build step, zero changes
to PraisonAIUI core, full light/dark/mobile support through built-in SDK
components, and automatic auth across every PraisonAIUI auth mode.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from praisonaiui.plugin_registry import (
    NavGroupSpec,
    PageSpec,
    SettingsField,
    SettingsSectionSpec,
    get_plugin_settings,
)

from . import pages as ui_pages
from . import service

__all__ = ["OpenShipPlugin", "plugin"]
__version__ = "0.2.0"

# Keeps last review result in memory so "Post Review Comment" can post it cleanly
_LAST_REVIEW: Dict[str, Dict[str, Any]] = {}


def _prefs() -> Dict[str, Any]:
    try:
        return get_plugin_settings("openship", "defaults")
    except Exception:
        return {
            "default_model": "",
            "default_effort": "high",
            "steward_max_attempts": 3,
            "policy_path": "",
        }


def _truthy(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    return str(val or "").strip().lower() in {"1", "true", "yes", "on"}


async def _read_json(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


# ── Overview routes ──────────────────────────────────────────────────────────


async def _overview_get(request: Request) -> JSONResponse:
    repo = service.get_repo_root()
    prefs = _prefs()
    status, (prs, prs_err), ledger = await asyncio.gather(
        asyncio.to_thread(service.get_repo_status, repo),
        asyncio.to_thread(service.list_prs, repo),
        asyncio.to_thread(service.load_ledger),
    )
    return JSONResponse(
        ui_pages.build_overview_page(
            repo_status=status,
            prs=prs,
            prs_error=prs_err,
            ledger=ledger,
            settings=prefs,
        )
    )


async def _overview_action(request: Request) -> JSONResponse:
    resp = await _overview_get(request)
    return resp


# ── Self-Review routes ───────────────────────────────────────────────────────


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
    cached = _LAST_REVIEW.get(pr or "local")
    return JSONResponse(
        ui_pages.build_review_page(
            pr=pr,
            effort=effort,
            model=model,
            review_result=cached,
            diff_text=diff_text,
            file_diffs=file_diffs,
            error=err,
        )
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
            return JSONResponse(
                {
                    **ui_pages.build_review_page(
                        pr=pr,
                        effort=effort,
                        model=model,
                        dry_run_plan=plan,
                        review_result=_LAST_REVIEW.get(pr or "local"),
                        diff_text=diff_text,
                        file_diffs=file_diffs,
                    ),
                    "message": "Dry-run plan ready",
                }
            )
        if action == "load_diff":
            diff_text, file_diffs, _ = await asyncio.to_thread(service.get_diff_bundle, repo, pr=(pr or None))
            return JSONResponse(
                {
                    **ui_pages.build_review_page(
                        pr=pr,
                        effort=effort,
                        model=model,
                        review_result=_LAST_REVIEW.get(pr or "local"),
                        diff_text=diff_text,
                        file_diffs=file_diffs,
                    ),
                    "message": f"Loaded {len(file_diffs)} changed file(s)",
                }
            )
        if action == "write_action" or (not action and "write_op" in body):
            confirm = _truthy(body.get("confirm"))
            write_op = str(body.get("write_op") or "ship_draft")
            if write_op == "post_comment":
                cached = _LAST_REVIEW.get(pr or "local") or {}
                msg = await asyncio.to_thread(
                    service.post_review_comment,
                    repo,
                    pr=pr,
                    findings=cached.get("findings") or [],
                    severity=str(cached.get("severity") or "none"),
                    confirm=confirm,
                )
                return JSONResponse(
                    {
                        **ui_pages.build_review_page(
                            pr=pr, effort=effort, model=model, review_result=cached, notice=msg
                        ),
                        "message": msg,
                    }
                )
            ship_res = await asyncio.to_thread(
                service.create_draft_pr,
                repo,
                effort=effort,
                model=(model or None),
                message=str(body.get("message") or "").strip() or None,
                confirm=confirm,
            )
            return JSONResponse(
                {
                    **ui_pages.build_review_page(
                        pr=pr,
                        effort=effort,
                        model=model,
                        ship_result=ship_res,
                        review_result={
                            "source": ship_res.get("pr_url", ""),
                            "severity": ship_res.get("severity", "none"),
                            "findings": ship_res.get("findings") or [],
                            "model": model or "default",
                        },
                    ),
                    "message": f"Opened draft PR: {ship_res.get('pr_url', '')}",
                }
            )
        if action in ("", "run_review"):
            res = await asyncio.to_thread(
                service.run_review, repo, pr=(pr or None), effort=effort, model=(model or None)
            )
            _LAST_REVIEW[pr or "local"] = res
            return JSONResponse(
                {
                    **ui_pages.build_review_page(
                        pr=pr,
                        effort=effort,
                        model=model,
                        review_result=res,
                        diff_text=res.get("diff", ""),
                        file_diffs=res.get("files") or [],
                    ),
                    "message": f"Self-review finished: {len(res['findings'])} finding(s)",
                }
            )
        return JSONResponse({"error": f"Unknown action: {action!r}"}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# ── Steward routes ───────────────────────────────────────────────────────────


async def _steward_get(request: Request) -> JSONResponse:
    prefs = _prefs()
    repo = service.get_repo_root()
    pr = request.query_params.get("pr", "").strip()
    max_attempts = int(prefs.get("steward_max_attempts") or 3)
    model = str(prefs.get("default_model") or "")
    state, err = None, ""
    if pr:
        try:
            state = await asyncio.to_thread(service.inspect_steward, repo, pr=pr, max_attempts=max_attempts)
        except Exception as exc:
            err = str(exc)
    else:
        try:
            state = await asyncio.to_thread(service.inspect_steward, repo, pr=None, max_attempts=max_attempts)
        except Exception:
            state = None
    return JSONResponse(
        ui_pages.build_steward_page(pr=pr, max_attempts=max_attempts, model=model, state=state, error=err)
    )


async def _steward_action(request: Request) -> JSONResponse:
    body = await _read_json(request)
    prefs = _prefs()
    repo = service.get_repo_root()
    action = str(body.get("action") or "")
    pr = str(body.get("pr") or (body.get("_params") or {}).get("pr") or "").strip()
    max_attempts = int(prefs.get("steward_max_attempts") or 3)
    model = str(body.get("model") or prefs.get("default_model") or "").strip()
    if action not in ("", "steward_once"):
        return JSONResponse({"error": f"Unknown action: {action!r}"}, status_code=400)
    try:
        res = await asyncio.to_thread(
            service.run_steward_once,
            repo,
            pr=(pr or None),
            model=(model or None),
            max_attempts=max_attempts,
            confirm=_truthy(body.get("confirm")),
        )
        state = None
        try:
            state = await asyncio.to_thread(service.inspect_steward, repo, pr=(pr or None), max_attempts=max_attempts)
        except Exception:
            pass
        return JSONResponse(
            {
                **ui_pages.build_steward_page(
                    pr=pr,
                    max_attempts=max_attempts,
                    model=model,
                    state=state,
                    events=res.get("events") or [],
                    revert_sha=res.get("revert_sha", ""),
                    notice=f"Completed Steward cycle ({len(res.get('events') or [])} event(s))",
                ),
                "message": "Steward cycle completed",
            }
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# ── Policy routes ────────────────────────────────────────────────────────────


async def _policy_get(request: Request) -> JSONResponse:
    prefs = _prefs()
    repo = service.get_repo_root()
    pr = request.query_params.get("pr", "").strip()
    policy_path = request.query_params.get("policy_path", "").strip() or str(prefs.get("policy_path") or "")
    ledger = await asyncio.to_thread(service.load_ledger)
    report, err = None, ""
    if pr:
        try:
            report = await asyncio.to_thread(
                service.evaluate_pr_policy, repo, pr=pr, policy_path=(policy_path or None)
            )
        except Exception as exc:
            err = str(exc)
    return JSONResponse(
        ui_pages.build_policy_page(pr=pr, policy_path=policy_path, report=report, ledger=ledger, error=err)
    )


async def _policy_action(request: Request) -> JSONResponse:
    body = await _read_json(request)
    prefs = _prefs()
    repo = service.get_repo_root()
    pr = str(body.get("pr") or (body.get("_params") or {}).get("pr") or "").strip()
    policy_path = str(body.get("policy_path") or prefs.get("policy_path") or "").strip()
    try:
        report = await asyncio.to_thread(
            service.evaluate_pr_policy, repo, pr=(pr or None), policy_path=(policy_path or None)
        )
        ledger = await asyncio.to_thread(service.load_ledger)
        return JSONResponse(
            {
                **ui_pages.build_policy_page(pr=pr, policy_path=policy_path, report=report, ledger=ledger),
                "message": f"Policy evaluated: {report.get('summary', '')}",
            }
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# ── Plugin descriptor ────────────────────────────────────────────────────────


class OpenShipPlugin:
    """First-class PraisonAIUI plugin for OpenShip (Claude Ship parity)."""

    name = "openship"
    version = __version__
    sdk = 1

    def pages(self) -> List[PageSpec]:
        return [
            PageSpec(
                id="openship",
                title="Overview",
                kind="blocks",
                icon="ship",
                nav_icon="ship",
                group="OpenShip",
                order=220,
                description="OpenShip PR queue, pipeline stepper, and review analytics",
                page_type="overview",
            ),
            PageSpec(
                id="openship-review",
                title="Self-Review",
                kind="blocks",
                icon="scan-search",
                nav_icon="scan-search",
                group="OpenShip",
                order=221,
                description="Diff viewer and AI self-review on any LLM or local Ollama",
                page_type="editor",
            ),
            PageSpec(
                id="openship-steward",
                title="PR Steward",
                kind="blocks",
                icon="wrench",
                nav_icon="wrench",
                group="OpenShip",
                order=222,
                description="Failing CI checks, conflicts, review threads, and 3-attempt circuit breaker",
                page_type="log",
            ),
            PageSpec(
                id="openship-policy",
                title="PR Policy",
                kind="blocks",
                icon="shield-check",
                nav_icon="shield-check",
                group="OpenShip",
                order=223,
                description="Declarative .praisonai/approvals.yml evaluation and observe-mode audit",
                page_type="list",
            ),
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
                    SettingsField(
                        key="default_model",
                        label="Default LLM model",
                        default="",
                        description="e.g. gpt-4o-mini or ollama/qwen3.5:9b (blank uses PraisonAI default)",
                    ),
                    SettingsField(
                        key="default_effort",
                        label="Default review effort",
                        type="select",
                        default="high",
                        options=("low", "medium", "high", "xhigh", "max"),
                    ),
                    SettingsField(
                        key="steward_max_attempts",
                        label="Steward max attempts",
                        type="number",
                        default=3,
                        description="Circuit-breaker cap per failing check or review thread",
                    ),
                    SettingsField(
                        key="policy_path",
                        label="Optional local policy preview path",
                        default="",
                        description="Repo-relative YAML path; leave blank to read origin/<base>:.praisonai/approvals.yml",
                    ),
                ),
            )
        ]

    def routes(self) -> List[Route]:
        return [
            Route("/pages/openship", _overview_get, methods=["GET"]),
            Route("/pages/openship/action", _overview_action, methods=["POST"]),
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
            from praisonaiui.server import create_app

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
