"""S4 · per-agent hand-off overhead: a 3-agent sequential pipeline.

Each run builds a fresh team (timed separately), resets the stub, then times
only ``run()``. The stub's recording is checked against the contract after
every run.

usage: python team3.py <scenarios/team3/<fw>.py> [--warmup 3] [--runs 30]
"""

import argparse
import os
import sys
import time

from _common import emit, install_egress_guard, load, stub_reset, stub_stats

install_egress_guard()
p = argparse.ArgumentParser()
p.add_argument("scenario")
p.add_argument("--warmup", type=int, default=3)
p.add_argument("--runs", type=int, default=30)
a = p.parse_args()

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import contract  # noqa: E402  (benchmarks/compare/contract.py)

mod = load(a.scenario)
build_ms, run_ms, req_bytes, failures = [], [], [], []
for i in range(a.warmup + a.runs):
    t0 = time.perf_counter()
    team = mod.build()
    t1 = time.perf_counter()
    stub_reset()
    t2 = time.perf_counter()
    out = mod.run(team)
    t3 = time.perf_counter()
    stats = stub_stats()
    problems = contract.check(stats, out)
    if problems:
        failures.append({"run": i, "problems": problems})
    if i >= a.warmup:
        build_ms.append((t1 - t0) * 1e3)
        run_ms.append((t3 - t2) * 1e3)
        req_bytes.append(stats["bytes_total"])
emit({"run_ms": run_ms, "build_ms": build_ms, "request_bytes": req_bytes,
      "contract_failures": failures[:5], "contract_failed_runs": len(failures)})
