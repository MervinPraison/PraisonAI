"""Shared helpers for probes. Probes run inside each framework's venv, so this
module is stdlib only and is imported before any framework code."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.request

from _guard import EGRESS, install_egress_guard  # noqa: F401


def stub_url() -> str:
    return os.environ["BENCH_STUB_URL"].rstrip("/")


def stub_reset() -> None:
    req = urllib.request.Request(stub_url() + "/_reset", data=b"{}", method="POST")
    urllib.request.urlopen(req, timeout=10).read()


def stub_stats() -> dict:
    with urllib.request.urlopen(stub_url() + "/_stats", timeout=10) as r:
        return json.loads(r.read())


def load(path: str):
    """Import a scenario file by path."""
    spec = importlib.util.spec_from_file_location("scenario", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def emit(obj: dict) -> None:
    """Write the probe result as the last stdout line."""
    obj["egress"] = EGRESS
    sys.stdout.write("\n" + json.dumps(obj) + "\n")
    sys.stdout.flush()


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
