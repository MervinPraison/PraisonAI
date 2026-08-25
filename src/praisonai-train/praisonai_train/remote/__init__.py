"""Remote SSH training for ``praisonai-train``.

The CLI in ``praisonai_train.cli.commands.remote`` is a thin Typer wrapper over
:class:`~praisonai_train.remote.runner.RemoteRunner`, which does the actual work
of preflighting a GPU host, shipping a job to it, starting it detached, tailing
its log, fetching artifacts back and stopping it — all over plain ``ssh``/``scp``
with no third-party dependency.
"""
from praisonai_train.remote.runner import (
    RemoteError,
    RemoteHost,
    RemotePreflight,
    RemoteRun,
    RemoteRunner,
)

__all__ = [
    "RemoteError",
    "RemoteHost",
    "RemotePreflight",
    "RemoteRun",
    "RemoteRunner",
]
