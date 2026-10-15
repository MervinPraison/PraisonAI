"""Egress guard: block and record every non-loopback socket connection.

Imports nothing heavy at module level so cold-import probes stay cold.
"""

import sys

EGRESS = []


def _is_loopback(host):
    if host in ("localhost", "", None):
        return True
    import ipaddress

    try:
        return ipaddress.ip_address(str(host).split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _audit(event, args):
    if event != "socket.connect":
        return
    import socket

    sock, address = args
    if getattr(socket, "AF_UNIX", None) is not None and sock.family == socket.AF_UNIX:
        return
    host = address[0] if isinstance(address, tuple) else address
    if not _is_loopback(host):
        EGRESS.append(str(address))
        raise OSError(f"benchmark egress guard: blocked connection to {address!r}")


def install_egress_guard():
    sys.addaudithook(_audit)
