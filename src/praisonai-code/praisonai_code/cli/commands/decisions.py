"""
System One / Jev decision model commands (Ollama /v1/systemone).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="System One typed decision models (Jev / Ollama)")


def _load_questions(path: Optional[Path]) -> dict[str, dict[str, Any]]:
    if path is None:
        from praisonaiagents.decisions.routing import default_ticket_triage_questions

        return default_ticket_triage_questions()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise typer.BadParameter("questions JSON must be an object")
    return data


@app.command("run")
def decisions_run(
    text: str = typer.Argument(..., help="Input state text (e.g. ticket body)"),
    model: str = typer.Option(
        os.environ.get("OLLAMA_DECISION_MODEL", "nimble"),
        "--model",
        "-m",
        help="Decision model (nimble, tev1, ...)",
    ),
    questions_file: Optional[Path] = typer.Option(
        None, "--questions", "-q", help="JSON file of System One questions"
    ),
    state_key: str = typer.Option("message", help="State field name for the input text"),
    api_base: Optional[str] = typer.Option(
        None, "--api-base", help="Ollama/TypeSafe base URL (default: OLLAMA_HOST / TYPESAFE_BASE_URL)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON response"),
):
    """
    Run a System One decision request (no chat LLM).

    Examples:
        praisonai decisions run "Charged twice, please refund"
        praisonai decisions run "App crashes on login" --model nimble --json
    """
    from praisonaiagents.decisions import system_one

    output = get_output_controller()
    questions = _load_questions(questions_file)
    try:
        result = system_one(
            state={state_key: text},
            questions=questions,
            model=model,
            api_base=api_base,
        )
    except RuntimeError as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=1) from exc

    if json_output:
        output.print(json.dumps(result.raw or {"model": result.model, "answers": result.answers}, indent=2))
        return

    output.print_info(f"model={result.model}")
    for name, ans in result.answers.items():
        output.print(f"  [bold]{name}[/bold]: {json.dumps(ans)}")


@app.command("triage")
def decisions_triage(
    text: str = typer.Argument(..., help="User message to triage"),
    model: str = typer.Option(
        os.environ.get("OLLAMA_DECISION_MODEL", "nimble"),
        "--model",
        "-m",
        help="Decision model",
    ),
    route: str = typer.Option(
        "team",
        "--route-question",
        help="Question name whose choice selects the chat route",
    ),
    billing_model: str = typer.Option("gpt-4o-mini", help="Chat LLM when route=billing"),
    technical_model: str = typer.Option("gpt-4o-mini", help="Chat LLM when route=technical"),
    other_model: str = typer.Option("gpt-4o-mini", help="Chat LLM when route=other"),
    skip_chat: bool = typer.Option(
        False, "--skip-chat", help="Only run decision model (no OpenAI/chat LLM call)"
    ),
    api_base: Optional[str] = typer.Option(None, "--api-base", help="Decision API base URL"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
):
    """
    Triage with a decision model, then optionally run a chat agent on the chosen route.

    Examples:
        praisonai decisions triage "Double charge, refund please" --skip-chat
        praisonai decisions triage "API 500 on webhook" --model nimble
    """
    from praisonaiagents.decisions.routing import (
        DecisionRoutePlan,
        default_ticket_triage_questions,
        triaged_start,
    )

    output = get_output_controller()
    plan = DecisionRoutePlan(
        route_question=route,
        decision_model=model,
        api_base=api_base,
        questions=default_ticket_triage_questions(),
        routes={
            "billing": billing_model,
            "technical": technical_model,
            "other": other_model,
        },
        fallback_route="other",
    )
    try:
        if skip_chat:
            from praisonaiagents.decisions.routing import triage_decision

            decision = triage_decision(text, questions=plan.questions, decision_model=model, api_base=api_base)
            payload = {"route": decision.choice(route), "answers": decision.answers, "model": decision.model}
            if json_output:
                output.print(json.dumps(payload, indent=2, default=str))
            else:
                output.print_info(json.dumps(payload, indent=2, default=str))
            return

        out = triaged_start(text, plan)
        payload = {
            "route": out["route"],
            "confidence": out["confidence"],
            "answers": out["decision"].answers,
            "response_preview": str(out["response"])[:500],
        }
        if json_output:
            output.print(json.dumps(payload, indent=2, default=str))
        else:
            output.print_info(f"route={out['route']} confidence={out['confidence']}")
            output.print(str(out["response"])[:2000])
    except RuntimeError as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        output.print_error(f"{type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc
