"""
RunPolicy — run-scoped guardrail for unattended (scheduled) agent runs.

Scheduled jobs execute **unattended**: there is no human present to approve
interactive tools or to notice a prompt-injection attempt smuggled in via
runtime-assembled skill/recipe content.  :class:`RunPolicy` lets a deployment
declare what an unattended run may do *before* the agent is handed the toolset
and prompt at run construction.

Lives in the **wrapper** layer (alongside the scheduler executor) because the
executor is the enforcement point — it is the only place that constructs the
run and therefore the only place that can scope the toolset and scan the
fully-assembled prompt.

Usage::

    from praisonai.scheduler.run_policy import RunPolicy
    from praisonai.scheduler.executor import ScheduledAgentExecutor

    executor = ScheduledAgentExecutor(
        runner=runner,
        agent_resolver=resolver,
        run_policy=RunPolicy(denied_toolsets={"cronjob", "shell"}),
    )
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

logger = logging.getLogger(__name__)


# Default deny-list for unattended runs.  Self-scheduling (``cronjob``) is
# denied so a scheduled run cannot silently spawn more scheduled runs, and
# interactive/approval tools are denied because no human is present to answer.
DEFAULT_DENIED_TOOLSETS: Set[str] = {
    "cronjob",
    "messaging-interactive",
}

# Conservative prompt-injection heuristics applied to the *assembled* prompt
# (user text plus any loaded skill/recipe content).  Intentionally cheap and
# dependency-free — a deployment that needs a stronger scanner can supply a
# guardrail plugin via ``scanner``.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"forget\s+(?:everything|all\s+previous|your\s+instructions)", re.I),
    re.compile(r"reveal\s+(?:your\s+)?(?:system\s+prompt|instructions)", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a\s+)?(?:different|new)\b", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
]


@dataclass
class PromptScanResult:
    """Outcome of scanning an assembled prompt.

    Attributes:
        ok: ``True`` if the prompt passed the scan.
        reason: Human-readable reason when ``ok`` is ``False``.
    """

    ok: bool = True
    reason: Optional[str] = None


@dataclass
class RunPolicy:
    """Declarable policy applied to an unattended scheduled run.

    Attributes:
        allowed_toolsets: If set, only tools whose name is in this set are
            kept; everything else is removed.  ``None`` means "allow all
            except ``denied_toolsets``".
        denied_toolsets: Tool names removed before the run.  Defaults to a
            conservative deny-list (self-scheduling + interactive tools).
        scan_assembled_prompt: Scan the final assembled prompt for
            injection patterns before it reaches the model.
        deliver_on_failure: On failure, deliver a compact failure summary to
            the job's delivery target (fail-closed delivery).
        audit_dir: Directory where full run output is persisted regardless of
            delivery outcome.  ``None`` disables the durable output audit.
        scanner: Optional callable ``(prompt: str) -> PromptScanResult`` that
            overrides the built-in heuristic scan (e.g. a guardrail plugin).
    """

    allowed_toolsets: Optional[Set[str]] = None
    denied_toolsets: Set[str] = field(
        default_factory=lambda: set(DEFAULT_DENIED_TOOLSETS)
    )
    scan_assembled_prompt: bool = True
    deliver_on_failure: bool = True
    audit_dir: Optional[str] = None
    scanner: Optional[Any] = None

    # ── toolset scoping ──────────────────────────────────────────────

    @staticmethod
    def _tool_name(tool: Any) -> str:
        """Best-effort name for a tool (matches Agent's own resolution).

        Resolves ``name``/``__name__`` first and only falls back to
        ``str(tool)`` as a last resort, so a tool with a failing custom
        ``__str__`` cannot break scheduling when a usable name exists.
        """
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            return name
        dunder = getattr(tool, "__name__", None)
        if isinstance(dunder, str) and dunder:
            return dunder
        return str(tool)

    def is_tool_allowed(self, tool: Any) -> bool:
        """Return ``True`` if ``tool`` may be used in an unattended run."""
        name = self._tool_name(tool)
        if name in self.denied_toolsets:
            return False
        if self.allowed_toolsets is not None and name not in self.allowed_toolsets:
            return False
        return True

    def filter_tools(self, tools: Optional[List[Any]]) -> List[Any]:
        """Return a copy of ``tools`` with denied/disallowed tools removed."""
        if not tools:
            return []
        kept: List[Any] = []
        removed: List[str] = []
        for tool in tools:
            if self.is_tool_allowed(tool):
                kept.append(tool)
            else:
                removed.append(self._tool_name(tool))
        if removed:
            logger.info(
                "RunPolicy removed %d tool(s) for unattended run: %s",
                len(removed),
                ", ".join(removed),
            )
        return kept

    # ── prompt scanning ──────────────────────────────────────────────

    def scan_prompt(self, prompt: str) -> PromptScanResult:
        """Scan an assembled prompt for injection patterns.

        Honours a user-supplied ``scanner`` callable when present, otherwise
        applies the built-in heuristics.  Returns ``ok=True`` when scanning is
        disabled.
        """
        if not self.scan_assembled_prompt:
            return PromptScanResult(ok=True)
        if not prompt:
            return PromptScanResult(ok=True)

        if self.scanner is not None:
            try:
                result = self.scanner(prompt)
            except Exception as e:  # pragma: no cover - defensive
                # Log the exception *type* only — the message could embed the
                # assembled prompt, so it stays out of the surfaced reason.
                logger.warning(
                    "RunPolicy scanner raised %s; failing closed",
                    e.__class__.__name__,
                )
                return PromptScanResult(ok=False, reason="scanner error")
            if isinstance(result, PromptScanResult):
                return result
            # Truthy => safe, falsy => blocked (lenient adapter).  Always carry
            # a reason on a block so downstream summaries are not "... None".
            ok = bool(result)
            return PromptScanResult(
                ok=ok,
                reason=None if ok else "scanner returned a blocking result",
            )

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(prompt):
                reason = f"assembled prompt matched injection pattern: {pattern.pattern!r}"
                logger.warning("RunPolicy blocked run: %s", reason)
                return PromptScanResult(ok=False, reason=reason)
        return PromptScanResult(ok=True)
