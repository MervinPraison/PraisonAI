"""Move a durable run between processes.

Durable execution is real and thorough -- ``agent/durable.py`` replays a run
from a journal -- but the journal is a local SQLite file, so a run could only
resume where it started. Pausing on a web worker, putting the state in a queue
and resuming it somewhere that shares no disk was not possible.

This exports a run's journal (its metadata and every event) as a plain dict,
and imports it into another journal:

    blob = export_run(journal, run_id)          # -> JSON-safe dict
    redis.set(key, export_run_json(journal, run_id))

    # elsewhere, no shared disk
    run_id = import_run(other_journal, blob)
    # resume as usual: the replay index is rebuilt from these events

Deliberately a JOURNAL export rather than a new state format: the journal is
already the single source of truth that ``DurableRunContext`` replays from, so
a second representation would be a second thing to keep correct.
"""

import json
from typing import Any, Dict, Optional

from .journal import JournalEvent, RunJournal

__all__ = [
    "PORTABLE_RUN_VERSION",
    "PortableRunError",
    "export_run",
    "export_run_json",
    "import_run",
    "import_run_json",
]

#: Bump when the exported SHAPE changes, so an old blob is refused with a clear
#: message rather than half-imported into a journal that cannot replay it.
PORTABLE_RUN_VERSION = 1


class PortableRunError(RuntimeError):
    """Raised when a run cannot be exported or imported."""


def export_run(journal: RunJournal, run_id: str) -> Dict[str, Any]:
    """Everything needed to resume ``run_id`` in another process."""
    meta = journal.run_meta(run_id)
    if meta is None:
        raise PortableRunError(
            f"No run {run_id!r} in this journal. Exporting a run that does not "
            f"exist would produce a blob that imports as an empty run."
        )
    events = journal.events(run_id)
    return {
        "version": PORTABLE_RUN_VERSION,
        "run": {
            "run_id": meta.run_id,
            "agent": meta.agent,
            "task": meta.task,
            "status": meta.status,
            "outcome": meta.outcome,
            "checkpoint_id": meta.checkpoint_id,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "metadata": meta.metadata or {},
        },
        "events": [
            {
                "seq": e.seq,
                "kind": e.kind,
                "payload": e.payload,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }


def export_run_json(journal: RunJournal, run_id: str) -> str:
    """``export_run`` as a JSON string, ready for a queue or a form field."""
    return json.dumps(export_run(journal, run_id), default=str)


def import_run(
    journal: RunJournal,
    blob: Dict[str, Any],
    *,
    run_id: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """Write an exported run into ``journal`` and return its run id.

    Refuses to import over an existing run unless ``overwrite=True``: silently
    merging two runs' events would produce a replay index that belongs to
    neither, and the failure would surface much later as a confusing resume.
    """
    if not isinstance(blob, dict):
        raise PortableRunError("Exported run must be a dict; got " + type(blob).__name__)

    version = blob.get("version")
    if version != PORTABLE_RUN_VERSION:
        raise PortableRunError(
            f"Exported run is version {version!r}, this build reads "
            f"{PORTABLE_RUN_VERSION}. Resume it with the version that wrote it."
        )

    run = blob.get("run") or {}
    target = run_id or run.get("run_id")
    if not target:
        raise PortableRunError("Exported run has no run_id and none was supplied.")

    if journal.run_meta(target) is not None and not overwrite:
        raise PortableRunError(
            f"Run {target!r} already exists in this journal. Importing would mix "
            f"two runs' events into one replay index. Pass run_id= to import "
            f"under a new id, or overwrite=True if replacing it is intended."
        )

    journal.open_run(
        target,
        agent=run.get("agent", "") or "",
        task=run.get("task", "") or "",
        checkpoint_id=run.get("checkpoint_id"),
        metadata=run.get("metadata") or {},
    )

    for event in blob.get("events") or []:
        journal.append(
            JournalEvent(
                run_id=target,
                seq=event["seq"],
                kind=event["kind"],
                payload=event.get("payload") or {},
                created_at=event.get("created_at", 0.0),
            )
        )
    return target


def import_run_json(
    journal: RunJournal,
    text: str,
    *,
    run_id: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """``import_run`` from a JSON string."""
    try:
        blob = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise PortableRunError(f"Exported run is not valid JSON: {exc}") from exc
    return import_run(journal, blob, run_id=run_id, overwrite=overwrite)
