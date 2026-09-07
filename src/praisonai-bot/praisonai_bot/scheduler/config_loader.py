"""Declarative gateway schedules (Issue #4913).

Bridges a ``schedules:`` block in gateway.yaml into the existing core
``ScheduleRunner`` store, so a recurring agent→channel delivery is a few lines
of YAML with no Python — reaching CLI+YAML+Python parity with every other
gateway capability.

The heavy machinery (models, runner/store, executor, delivery loop) already
lives in ``praisonaiagents.scheduler`` and ``praisonai_bot``; this module only
coerces each YAML entry into a core ``ScheduleJob`` + ``DeliveryTarget`` and
upserts it (idempotent on a stable id derived from the YAML key).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


def _stable_job_id(job_key: str) -> str:
    """Derive a stable, idempotent job id from a YAML schedule key.

    Deterministic so re-loading the same config upserts the same job rather
    than accumulating duplicates on every boot / hot-reload.
    """
    digest = hashlib.sha1(f"gateway-schedule:{job_key}".encode("utf-8")).hexdigest()
    return f"cfg-{digest[:12]}"


def _schedule_expr(spec: Dict[str, Any]) -> str:
    """Build a ``parse_schedule`` expression from a YAML schedule spec.

    Accepts exactly one of ``cron`` / ``every`` / ``at`` (validated upstream by
    ``ScheduleConfigSchema``). ``every`` accepts a bare interval like ``24h`` /
    ``30m`` / ``10s`` (mapped to the ``*/24h`` interval grammar) or a raw
    number of seconds.
    """
    if spec.get("cron"):
        return f"cron:{spec['cron']}"
    if spec.get("at"):
        return f"at:{spec['at']}"
    every = str(spec.get("every", "")).strip()
    # Bare intervals like "24h" become the "*/24h" interval grammar; a raw
    # integer (seconds) is passed through unchanged.
    if every and not every.startswith("*/") and not every.isdigit():
        return f"*/{every}"
    return every


def schedule_job_from_config(job_key: str, spec: Dict[str, Any]):
    """Coerce one ``schedules:`` entry into a core ``ScheduleJob``.

    Args:
        job_key: The YAML map key (e.g. ``"morning-brief"``) — used as the job
            name and to derive a stable, idempotent id.
        spec: The validated schedule spec dict.

    Returns:
        A ``praisonaiagents.scheduler.ScheduleJob`` ready to upsert.
    """
    from praisonaiagents.scheduler.models import DeliveryTarget, ScheduleJob
    from praisonaiagents.scheduler.parser import parse_schedule

    sched = parse_schedule(_schedule_expr(spec))

    delivery: Optional[DeliveryTarget] = None
    deliver = spec.get("deliver")
    if isinstance(deliver, dict) and deliver.get("channel"):
        delivery = DeliveryTarget(
            channel=deliver["channel"],
            channel_id=str(deliver.get("channel_id", "") or ""),
            thread_id=deliver.get("thread_id"),
            continuable=deliver.get("continuable", True),
        )

    return ScheduleJob(
        id=_stable_job_id(job_key),
        name=job_key,
        schedule=sched,
        message=spec.get("prompt", ""),
        agent_id=spec.get("agent") or None,
        delivery=delivery,
        pre_run=spec.get("pre_run"),
        enabled=spec.get("enabled", True),
    )


def load_schedules_into_store(config: Dict[str, Any], store) -> int:
    """Load a config's ``schedules:`` block into a schedule store (idempotent).

    Upserts each declared schedule onto its stable id, so declarative jobs are
    reconciled on every boot / hot-reload without duplicating and without
    disturbing jobs created in-chat via the agent-callable tool (those carry
    their own random ids). Best-effort: a single malformed entry is logged and
    skipped rather than aborting the whole gateway.

    Args:
        config: The loaded gateway config dict.
        store: A schedule store exposing ``get``/``add``/``update``.

    Returns:
        The number of schedules successfully loaded.
    """
    schedules = (config or {}).get("schedules") or {}
    if not isinstance(schedules, dict):
        return 0

    loaded = 0
    for job_key, spec in schedules.items():
        if not isinstance(spec, dict):
            logger.warning("Skipping malformed schedule %r (not a mapping)", job_key)
            continue
        try:
            job = schedule_job_from_config(job_key, spec)
        except Exception as e:
            logger.warning("Skipping invalid schedule %r: %s", job_key, e)
            continue
        try:
            existing = store.get(job.id) if hasattr(store, "get") else None
            if existing is not None:
                store.update(job)
            else:
                store.add(job)
            loaded += 1
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to load schedule %r into store: %s", job_key, e)

    if loaded:
        logger.info("Loaded %d declarative gateway schedule(s) from config", loaded)
    return loaded
