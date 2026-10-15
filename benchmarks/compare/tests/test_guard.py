import subprocess
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent.parent / "probes"

CODE = """
import socket, json, sys
from _guard import EGRESS, install_egress_guard
install_egress_guard()
out = {}
for host in ("192.0.2.1", "127.0.0.1"):
    s = socket.socket(); s.settimeout(0.2)
    try:
        s.connect((host, 9))
    except OSError as e:
        out[host] = "guard" in str(e)
    finally:
        s.close()
print(json.dumps({"blocked": out, "egress": EGRESS}))
"""


def test_egress_guard_blocks_non_loopback_only():
    import json

    p = subprocess.run([sys.executable, "-c", CODE], cwd=PROBES, capture_output=True, text=True,
                       env={"PYTHONPATH": str(PROBES)})
    out = json.loads(p.stdout)
    assert out["blocked"] == {"192.0.2.1": True, "127.0.0.1": False}
    assert out["egress"] == ["('192.0.2.1', 9)"]
