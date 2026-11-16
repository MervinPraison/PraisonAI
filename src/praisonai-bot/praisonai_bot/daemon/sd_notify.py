"""
Minimal, stdlib-only systemd notification protocol client (Issue #6123).

Lets the gateway tell systemd when it is actually serving (``READY=1``), that
its event loop is still progressing (``WATCHDOG=1``) and that it is draining
(``STOPPING=1``). Every call is a silent no-op when ``$NOTIFY_SOCKET`` is
absent (not under a ``Type=notify`` unit), so there is zero cost elsewhere.
"""

from __future__ import annotations

import os
import socket
from typing import Optional


def sd_notify(state: str) -> bool:
    """Send ``state`` to ``$NOTIFY_SOCKET``; return True if it was delivered.

    Fail-open and non-blocking: a full receive queue or any socket error is
    reported as False so notification can never stall or crash the gateway.
    """
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr or not hasattr(socket, "AF_UNIX"):
        return False
    if addr[0] == "@":  # abstract namespace socket
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.setblocking(False)
            sock.connect(addr)
            sock.send(state.encode())
        return True
    except OSError:
        return False


def watchdog_interval() -> Optional[float]:
    """Seconds between ``WATCHDOG=1`` pings, or None if systemd wants none.

    Mirrors ``sd_watchdog_enabled(3)``: honours ``$WATCHDOG_USEC`` (and
    ``$WATCHDOG_PID`` when set) and pings at half the deadline.
    """
    pid = os.environ.get("WATCHDOG_PID")
    if pid and pid != str(os.getpid()):
        return None
    try:
        usec = int(os.environ.get("WATCHDOG_USEC", "0"))
    except ValueError:
        return None
    return usec / 2_000_000 if usec > 0 else None
