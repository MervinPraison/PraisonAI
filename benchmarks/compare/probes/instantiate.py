"""S3 · instantiation: build one agent with one tool, many times, in one process.

The tool is wrapped by ``make_tool()`` outside the timed region, so every
framework times only agent construction.

usage: python instantiate.py <scenarios/agent1/<fw>.py> [--fn build] [--warmup 50] [--iterations 1000]
"""

import argparse
import time

from _common import emit, install_egress_guard, load, median

install_egress_guard()
p = argparse.ArgumentParser()
p.add_argument("scenario")
p.add_argument("--fn", default="build")
p.add_argument("--warmup", type=int, default=50)
p.add_argument("--iterations", type=int, default=1000)
a = p.parse_args()

mod = load(a.scenario)
fn = getattr(mod, a.fn)
tools = [mod.make_tool()]
for _ in range(a.warmup):
    fn(tools)
samples = []
clock = time.perf_counter_ns
for _ in range(a.iterations):
    t0 = clock()
    fn(tools)
    samples.append((clock() - t0) / 1e3)
emit({"median_us": median(samples), "samples_us": samples})
