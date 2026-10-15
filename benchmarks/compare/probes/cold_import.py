"""S1 · cold import: time one import statement in a fresh interpreter.

usage: python cold_import.py "<import statement>"
"""

import sys
import time

base_modules = len(sys.modules)
from _guard import EGRESS, install_egress_guard  # noqa: E402

install_egress_guard()
stmt = sys.argv[1]
t0 = time.perf_counter()
exec(stmt, {})
elapsed_ms = (time.perf_counter() - t0) * 1e3
modules = len(sys.modules)

import json  # noqa: E402

sys.stdout.write("\n" + json.dumps({
    "ms": elapsed_ms, "modules": modules, "modules_added": modules - base_modules,
    "egress": EGRESS}) + "\n")
