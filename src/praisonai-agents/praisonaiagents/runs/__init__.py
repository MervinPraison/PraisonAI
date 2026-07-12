"""
Durable, recoverable run-ledger module for PraisonAI Agents.

Provides a first-class ledger so long-running / async agent runs survive a
gateway restart: every run is recorded with a stable ``run_id``, a
:class:`RunStatus`, a progress summary and a terminal outcome. On restart,
orphaned runs are reconciled so the gateway can notify the originating user.

Layering:
- Thin protocol + data shapes (:mod:`~praisonaiagents.runs.protocols`) are
  always available and carry no heavy imports.
- A zero-dependency SQLite default store
  (:class:`~praisonaiagents.runs.sqlite_ledger.SQLiteRunLedger`) is lazily
  loaded so importing this package stays cheap.

Usage::

    from praisonaiagents.runs import SQLiteRunLedger, RunRecord, RunStatus

    ledger = SQLiteRunLedger()                       # ~/.praisonai/runs/ledger.db
    ledger.upsert(RunRecord(run_id="r1", channel="#ops",
                            status=RunStatus.RUNNING))
    # ...gateway restarts...
    for lost in ledger.recover_orphans():            # reconcile on boot
        notify_origin(lost)
"""

from .protocols import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    RunLedgerProtocol,
    RunRecord,
    RunStatus,
)

__all__ = [
    "RunStatus",
    "RunRecord",
    "RunLedgerProtocol",
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "SQLiteRunLedger",
]


def __getattr__(name: str):
    """Lazy load heavier components to keep import cost minimal."""
    if name == "SQLiteRunLedger":
        from .sqlite_ledger import SQLiteRunLedger

        return SQLiteRunLedger
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
