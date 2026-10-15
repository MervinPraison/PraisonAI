"""S5 · memory per agent: build and retain K agents in a fresh process.

``--mode tracemalloc`` reports retained traced bytes / K; ``--mode rss`` runs
with tracing off and reports the resident-set delta / K.

usage: python memory.py <scenarios/agent1/<fw>.py> [--k 200] [--warmup 20] [--mode tracemalloc|rss]
"""

import argparse
import gc
import os
import sys

from _common import emit, install_egress_guard, load

install_egress_guard()
p = argparse.ArgumentParser()
p.add_argument("scenario")
p.add_argument("--k", type=int, default=200)
p.add_argument("--warmup", type=int, default=20)
p.add_argument("--mode", choices=["tracemalloc", "rss"], default="tracemalloc")
a = p.parse_args()


def rss_bytes():
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except OSError:  # macOS: peak RSS only; still monotone for this probe
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak if sys.platform == "darwin" else peak * 1024


mod = load(a.scenario)
tools = [mod.make_tool()]
for _ in range(a.warmup):
    mod.build(tools)
gc.collect()
if a.mode == "tracemalloc":
    import tracemalloc

    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    keep = [mod.build(tools) for _ in range(a.k)]
    gc.collect()
    after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
else:
    before = rss_bytes()
    keep = [mod.build(tools) for _ in range(a.k)]
    gc.collect()
    after = rss_bytes()
emit({"kib_per_agent": (after - before) / a.k / 1024, "k": len(keep), "mode": a.mode})
