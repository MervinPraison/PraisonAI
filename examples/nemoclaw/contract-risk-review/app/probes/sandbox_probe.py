"""Deterministic OpenShell sandbox probe (no LLM involved).

Prints one JSON document describing each egress / filesystem check, whether
the observed result matched the expectation, and an overall ``pass`` flag.
Exits 1 when any check does not match, so ``run.sh`` stops before the agents
run in a sandbox that is not locked down.

Usage: python probes/sandbox_probe.py > probe.json
"""

import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

CA_BUNDLE = os.environ.get("SSL_CERT_FILE", "/etc/openshell-tls/ca-bundle.pem")
INFERENCE_MODELS = os.environ.get("OPENAI_BASE_URL", "https://inference.local/v1").rstrip("/") + "/models"
TIMEOUT = 10


def _ssl_context():
    if os.path.isfile(CA_BUNDLE):
        return ssl.create_default_context(cafile=CA_BUNDLE)
    return ssl.create_default_context()


def _http(method, url, data=None, headers=None):
    """Return (status or None, detail). urllib honours HTTPS_PROXY from the env."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as resp:
            return resp.status, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return exc.code, f"HTTP {exc.code}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def check_pastebin_denied():
    status, detail = _http("POST", "https://pastebin.com/api/api_post.php", data=b"api_option=paste")
    return status is None or not 200 <= status < 300, detail


def check_raw_socket_denied():
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=TIMEOUT):
            return False, "connected to 1.1.1.1:443"
    except OSError as exc:
        return True, f"{type(exc).__name__}: {exc}"


def check_inference_allowed():
    key = os.environ.get("OPENAI_API_KEY", "")
    status, detail = _http("GET", INFERENCE_MODELS, headers={"Authorization": f"Bearer {key}"})
    return status is not None and 200 <= status < 300, detail


def check_etc_hosts_denied():
    try:
        with open("/etc/hosts", "a", encoding="utf-8") as f:
            f.write("")  # opening for append is the denied operation; write nothing
        return False, "opened /etc/hosts for append"
    except OSError as exc:
        return True, f"{type(exc).__name__}: {exc}"


def _check_write(path):
    try:
        Path(path).write_text("ok\n", encoding="utf-8")
        return True, f"wrote {path}"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


CHECKS = [
    ("pastebin_post", "denied", check_pastebin_denied),
    ("raw_socket_1.1.1.1_443", "denied", check_raw_socket_denied),
    ("inference_local_models", "2xx", check_inference_allowed),
    ("etc_hosts_append", "denied", check_etc_hosts_denied),
    ("write_workdir", "success", lambda: _check_write(Path.cwd() / "ok.txt")),
    ("write_tmp", "success", lambda: _check_write("/tmp/ok.txt")),
]


def main():
    results = []
    for name, expected, fn in CHECKS:
        ok, detail = fn()
        results.append({"check": name, "expected": expected, "pass": ok, "detail": detail})
    report = {"pass": all(r["pass"] for r in results), "checks": results}
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
