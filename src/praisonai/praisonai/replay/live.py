"""Watch an agent, team or flow run live: a page with a Run button (PraisonAI Replay).

    from praisonai.replay import watch
    watch(flow)                     # opens the browser; each Run is recorded and drawn live

    from praisonai.replay import replay_app
    app.mount("/replay", replay_app(flow))   # inside your own FastAPI/Starlette app

The page is aiui's Replay view without the dashboard around it
(``praisonaiui.features.replay.create_replay_app``). Requires ``pip install "praisonai[ui]"``.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable, Optional

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_INSTALL_HINT = 'PraisonAI Replay needs PraisonAI UI: pip install -U "praisonai[ui]"'


def _runner(target: Any) -> Optional[Callable[[str, str], None]]:
    """``run(input, run_id)`` that records *target* under ``run_id``, live."""
    if target is None:
        return None
    from .recorder import record
    from .yaml_run import is_yaml_path, run_yaml_recorded

    if isinstance(target, (str, Path)):
        if not is_yaml_path(str(target)):
            raise ValueError(f"not a YAML file: {target}")
        path = str(target)

        def run_yaml(_text: str, run_id: str) -> None:
            run_yaml_recorded(path, run_id=run_id, live=True)

        return run_yaml

    start = getattr(target, "start", None)
    call = start if callable(start) else target
    if not callable(call):
        raise TypeError("target must be an Agent, AgentTeam, AgentFlow, a YAML path or a callable(input)")

    # An AgentTeam skips tasks it already completed; each Run starts them afresh.
    reset = getattr(target, "_reset_task_state_for_item", None)

    def run(text: str, run_id: str) -> None:
        if callable(reset):
            reset()
        with record(run_id, live=True):
            call(text)

    return run


def _title(target: Any) -> str:
    if isinstance(target, (str, Path)):
        return f"PraisonAI Replay: {Path(target).name}"
    name = getattr(target, "name", None) or getattr(target, "__name__", None)
    return f"PraisonAI Replay: {name}" if isinstance(name, str) and name else "PraisonAI Replay"


def replay_app(target: Any = None, *, input: str = "", placeholder: str = "", title: Optional[str] = None):
    """The Replay page as an ASGI app; with *target*, it has a Run button.

    Args:
        target: An Agent, AgentTeam or AgentFlow (``.start(input)`` is called), a
            YAML file (run as written; no input box), or any ``callable(input)``.
            ``None`` gives a read-only view of recorded runs.
        input: Text the input box starts with.
        placeholder: Placeholder for the input box.
        title: Page title (default: from the target's name).

    Each Run is recorded with :func:`praisonai.replay.record` under a new run id
    and the page follows it live. One run at a time. The same *target* object is
    reused: a team's tasks start afresh each run, an Agent keeps its chat history.

    Open ``<mount>/`` for the run list, or ``<mount>/?run=<run_id>`` for one run
    (handy in an ``<iframe>``).
    """
    try:
        from praisonaiui.features.replay import create_replay_app
    except ImportError as e:  # aiui missing or older than the embeddable app
        raise ImportError(_INSTALL_HINT) from e
    is_yaml = isinstance(target, (str, Path))
    return create_replay_app(
        _runner(target),
        title=title or _title(target),
        input=None if is_yaml else input,
        placeholder=placeholder,
    )


def watch(
    target: Any = None,
    *,
    input: str = "",
    placeholder: str = "",
    title: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 8090,
    open_browser: bool = True,
) -> None:
    """Serve :func:`replay_app` and open it in the browser (blocks until Ctrl+C).

    Example::

        from praisonai.replay import watch
        watch(flow, input="Write about solar sails")
    """
    import uvicorn

    app = replay_app(target, input=input, placeholder=placeholder, title=title)
    if host not in _LOOPBACK_HOSTS:
        print(
            f"WARNING: serving on {host} lets anyone who can reach it read your runs"
            + (" and start new ones." if target is not None else ".")
        )
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/"
    print(f"PraisonAI Replay: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
