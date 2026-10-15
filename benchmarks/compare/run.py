"""Cross-framework benchmark orchestrator (stdlib only).

Syncs one uv venv per framework, starts the stub LLM, runs every probe in a
fresh process in seeded-random interleaved rounds, and writes
``results/<date>.json`` + ``results/latest.json``. See README.md for the
methodology.

    python benchmarks/compare/run.py [--frameworks all|a,b] [--scale 1] [--seed 0]
                                     [--scenarios s1,s2,s3,s4,s5,s6] [--frozen]
                                     [--python FW=/path/to/python]

Exit status is non-zero when any probe tried a non-loopback connection, and
with ``--strict`` also when a framework, probe or contract failed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import loc  # noqa: E402
import stats  # noqa: E402

BASELINE = "raw_openai"
SCENARIOS = ("s1", "s2", "s3", "s4", "s5", "s6")
TELEMETRY_OFF = {
    "DO_NOT_TRACK": "true", "PRAISONAI_TELEMETRY_DISABLED": "true",
    "CREWAI_TELEMETRY_OPT_OUT": "true", "CREWAI_DISABLE_TELEMETRY": "true",
    "OTEL_SDK_DISABLED": "true", "AGNO_TELEMETRY": "false", "ANONYMIZED_TELEMETRY": "false",
}
# Egress trap: anything that ignores the stub and honours proxies hits a closed port.
PROXY_TRAP = {k: "http://127.0.0.1:9" for k in
              ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")}
PROXY_TRAP.update(NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")

# key: (title, unit, superlative, lower_is_better)
METRICS = {
    "cold_import_ms": ("Cold import", "ms", "fastest", True),
    "first_response_ms": ("Cold time to first response", "ms", "fastest", True),
    "instantiate_us": ("Agent instantiation (one tool)", "μs", "fastest", True),
    "team3_run_ms": ("3-agent sequential run", "ms", "fastest", True),
    "handoff_overhead_ms": ("Per-agent hand-off overhead vs raw SDK", "ms", "lowest", True),
    "team3_build_ms": ("3-agent team build", "ms", "fastest", True),
    "team3_request_bytes": ("Request bytes per 3-agent run", "B", "fewest", True),
    "memory_kib_per_agent": ("Memory per agent (tracemalloc)", "KiB", "lowest", True),
    "memory_rss_kib_per_agent": ("Memory per agent (RSS delta)", "KiB", "lowest", True),
    "loc_lines": ("Lines of code, 3-agent team", "lines", "fewest", True),
    "loc_tokens": ("Tokens of code, 3-agent team", "tokens", "fewest", True),
}


def log(msg: str) -> None:
    print(f"[bench] {msg}", file=sys.stderr, flush=True)


def scaled(base: int, scale: float, floor: int) -> int:
    return max(floor, round(base * scale))


# --------------------------------------------------------------------------- env

def sync_env(fw: str, frozen: bool) -> Path:
    project = HERE / "frameworks" / fw
    cmd = ["uv", "sync", "--project", str(project), "--python", "3.12", "--quiet"]
    # "praisonai" is a path dependency on this checkout, whose dependencies move
    # with main, so it always re-locks; every other framework honours --frozen.
    if frozen and fw != "praisonai":
        cmd.append("--frozen")
    subprocess.run(cmd, check=True)
    return project / ".venv" / "bin" / "python"


def pinned_cpus() -> list[int]:
    """Two CPUs this process may use (stub, probes), or [] to skip pinning."""
    if not (sys.platform.startswith("linux") and shutil.which("taskset")
            and hasattr(os, "sched_getaffinity")):
        return []
    cpus = sorted(os.sched_getaffinity(0))
    return cpus[:2] if len(cpus) >= 2 else []


def machine_info() -> dict:
    info = {"platform": platform.platform(), "machine": platform.machine(),
            "cores": os.cpu_count(), "runner_image": os.environ.get("ImageOS"),
            "runner_image_version": os.environ.get("ImageVersion")}
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                info["ram_gib"] = round(int(line.split()[1]) / 2**20, 1)
                break
    except OSError:
        for key, name in (("cpu", "machdep.cpu.brand_string"), ("ram_bytes", "hw.memsize")):
            try:
                info[key] = subprocess.run(["sysctl", "-n", name], capture_output=True,
                                           text=True).stdout.strip()
            except OSError:
                pass
    gov = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if gov.exists():
        info["cpu_governor"] = gov.read_text().strip()
    return info


def _out(cmd) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO).stdout.strip() or None
    except OSError:
        return None


# ------------------------------------------------------------------------ runner

class Runner:
    def __init__(self, args, pythons: dict[str, Path], stub_url: str, workdir: str):
        self.args = args
        self.pythons = pythons
        self.stub_url = stub_url
        self.workdir = workdir
        self.egress: list[dict] = []
        self.egress_log = Path(workdir) / ".egress.log"
        cpus = pinned_cpus()
        self.pin = ["taskset", "-c", str(cpus[1])] if cpus else []
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("PYTHON", "OPENAI_", "VIRTUAL_ENV"))}
        env.update(TELEMETRY_OFF, **PROXY_TRAP)
        env.update(BENCH_STUB_URL=stub_url, OPENAI_BASE_URL=stub_url + "/v1",
                   OPENAI_API_KEY="sk-stub", PYTHONHASHSEED="0",
                   BENCH_EGRESS_LOG=str(self.egress_log))
        self.env = env

    def reset_stub(self) -> None:
        import urllib.request
        urllib.request.urlopen(urllib.request.Request(
            self.stub_url + "/_reset", data=b"{}", method="POST"), timeout=10).read()

    def probe(self, fw: str, script: str, *args: str, flags=()) -> dict:
        """Run one probe in a fresh interpreter; return its JSON or {"error": ...}."""
        cmd = [*self.pin, str(self.pythons[fw]), *flags, str(HERE / "probes" / script), *args]
        t0 = time.perf_counter()
        try:
            p = subprocess.run(cmd, cwd=self.workdir, env=self.env, capture_output=True,
                               text=True, timeout=self.args.timeout)
        except subprocess.TimeoutExpired:
            return {"error": f"timeout after {self.args.timeout}s"}
        finally:
            # Read from the guard's log, not the probe's output, so a crash or
            # timeout cannot hide a blocked connection.
            if self.egress_log.exists():
                self.egress.append({"framework": fw, "probe": script,
                                    "connections": self.egress_log.read_text().splitlines()})
                self.egress_log.unlink()
        wall_ms = (time.perf_counter() - t0) * 1e3
        lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
        try:
            out = json.loads(lines[-1])
        except (IndexError, ValueError):
            tail = (p.stderr or p.stdout).strip().splitlines()[-5:]
            return {"error": f"exit {p.returncode}: " + " | ".join(tail), "stderr": p.stderr}
        out["wall_ms"] = wall_ms
        if flags and p.stderr:
            out["stderr"] = p.stderr
        return out

    def rounds(self, fws, n):
        rng = random.Random(f"{self.args.seed}:{n}:{','.join(fws)}")
        for r in range(n):
            yield r, rng.sample(list(fws), len(fws))


def scenario(kind: str, fw: str) -> Path | None:
    path = HERE / "scenarios" / kind / f"{fw}.py"
    return path if path.exists() else None


def run_s1(rn: Runner, fws, n: int, raw: dict) -> dict:
    imports = tomllib.loads((HERE / "scenarios" / "imports.toml").read_text())["imports"]
    fws = [fw for fw in fws if fw in imports]
    samples = {fw: [] for fw in fws}
    modules = {fw: [] for fw in fws}
    errors = {}
    for r, order in rn.rounds(fws, n + 1):
        for fw in order:
            if fw in errors:
                continue
            out = rn.probe(fw, "cold_import.py", imports[fw])
            if "error" in out:
                errors[fw] = out["error"]
            elif r:  # the first sample of every framework is discarded
                samples[fw].append(out["ms"])
                modules[fw].append(out["modules"])
    importtime = {}
    for fw in fws:
        if fw in errors:
            continue
        out = rn.probe(fw, "cold_import.py", imports[fw], flags=("-X", "importtime"))
        importtime[fw] = _importtime_top(out.get("stderr", ""), 20)
    raw["s1_importtime_top20"] = importtime
    return {"samples": samples, "errors": errors,
            "extra": {fw: {"modules": stats.median(m)} for fw, m in modules.items() if m},
            "statements": {fw: imports[fw] for fw in fws}}


def _importtime_top(stderr: str, k: int) -> list:
    rows = []
    for line in stderr.splitlines():
        if line.startswith("import time:") and "|" in line:
            parts = [p.strip() for p in line[len("import time:"):].split("|")]
            if parts[0].isdigit():
                rows.append({"cumulative_us": int(parts[1]), "module": parts[2]})
    return sorted(rows, key=lambda r: -r["cumulative_us"])[:k]


def run_s2(rn: Runner, fws, n: int) -> dict:
    fws = [fw for fw in fws if scenario("agent1", fw)]
    samples, errors = {fw: [] for fw in fws}, {}
    for r, order in rn.rounds(fws, n + 1):
        for fw in order:
            if fw in errors:
                continue
            rn.reset_stub()
            out = rn.probe(fw, "first_response.py", str(scenario("agent1", fw)))
            if "error" in out:
                errors[fw] = out["error"]
            elif not out.get("ok"):
                errors[fw] = f"contract failed: reply nonce missing ({out.get('requests')} requests)"
            elif r:
                samples[fw].append(out["ms"])
    return {"samples": samples, "errors": errors}


def run_s3(rn: Runner, fws, procs: int, iters: int, raw: dict) -> tuple[dict, dict]:
    fws = [fw for fw in fws if fw != BASELINE and scenario("agent1", fw)]
    samples, errors, legacy = {fw: [] for fw in fws}, {}, {}
    raw_samples = raw.setdefault("s3_instantiate_us", {})
    for _, order in rn.rounds(fws, procs):
        for fw in order:
            if fw in errors:
                continue
            out = rn.probe(fw, "instantiate.py", str(scenario("agent1", fw)),
                           "--iterations", str(iters))
            if "error" in out:
                errors[fw] = out["error"]
                continue
            samples[fw].append(out["median_us"])
            raw_samples.setdefault(fw, []).append(out["samples_us"])
            if fw.startswith("praisonai"):
                old = rn.probe(fw, "instantiate.py", str(scenario("agent1", fw)),
                               "--fn", "build_legacy", "--iterations", str(iters))
                if "error" not in old:
                    legacy.setdefault(fw, []).append(old["median_us"])
    return {"samples": samples, "errors": errors}, {"samples": legacy, "errors": {}}


def run_s4(rn: Runner, fws, procs: int, runs: int, raw: dict) -> dict:
    fws = [fw for fw in fws if scenario("team3", fw)]
    acc = {fw: {"run_ms": [], "build_ms": [], "request_bytes": [], "failed_runs": 0,
                "failures": []} for fw in fws}
    errors = {}
    for _, order in rn.rounds(fws, procs):
        for fw in order:
            if fw in errors:
                continue
            out = rn.probe(fw, "team3.py", str(scenario("team3", fw)), "--runs", str(runs))
            if "error" in out:
                errors[fw] = out["error"]
                continue
            for key in ("run_ms", "build_ms", "request_bytes"):
                acc[fw][key].extend(out[key])
            acc[fw]["failed_runs"] += out["contract_failed_runs"]
            acc[fw]["failures"].extend(out["contract_failures"])
    raw["s4_team3"] = acc
    contract = {}
    for fw in fws:
        if fw in errors:
            contract[fw] = {"passed": False, "error": errors[fw]}
        else:
            a = acc[fw]
            contract[fw] = {"passed": a["failed_runs"] == 0 and bool(a["run_ms"]),
                            "runs": len(a["run_ms"]), "failed_runs": a["failed_runs"],
                            "failures": a["failures"][:3]}
    return {"acc": acc, "errors": errors, "contract": contract}


def run_s5(rn: Runner, fws, procs: int, k: int) -> tuple[dict, dict]:
    fws = [fw for fw in fws if fw != BASELINE and scenario("agent1", fw)]
    res = {mode: ({fw: [] for fw in fws}, {}) for mode in ("tracemalloc", "rss")}
    for _, order in rn.rounds(fws, procs):
        for fw in order:
            for mode, (samples, errors) in res.items():
                if fw in errors:
                    continue
                out = rn.probe(fw, "memory.py", str(scenario("agent1", fw)), "--k", str(k),
                               "--mode", mode)
                if "error" in out:
                    errors[fw] = out["error"]
                else:
                    samples[fw].append(out["kib_per_agent"])
    return tuple({"samples": res[m][0], "errors": res[m][1], "k": k}
                 for m in ("tracemalloc", "rss"))


def run_s6(fws, contract: dict) -> dict:
    ruff = shutil.which("ruff")
    if not ruff:
        # Unformatted counts depend on how each file happens to be wrapped.
        return {"counts": {}, "formatted": False,
                "errors": {fw: "ruff not installed: not counted" for fw in fws
                           if scenario("team3", fw)}}
    tmp = Path(tempfile.mkdtemp(prefix="bench-loc-"))
    samples, errors = {}, {}
    for fw in fws:
        src = scenario("team3", fw)
        if not src:
            continue
        if not contract.get(fw, {}).get("passed"):
            errors[fw] = "contract failed: not counted"
            continue
        dst = tmp / f"{fw}.py"
        shutil.copy(src, dst)
        samples[fw] = dst
    if samples:
        subprocess.run([ruff, "format", "--quiet", "--line-length", "88", *map(str, samples.values())],
                       check=True)
    counts = {fw: loc.count(p.read_text()) for fw, p in samples.items()}
    shutil.rmtree(tmp, ignore_errors=True)
    return {"counts": counts, "errors": errors, "formatted": True}


# ------------------------------------------------------------------------ results

def metric(key: str, summaries: dict, errors: dict, **extra) -> dict:
    title, unit, superlative, lower = METRICS[key]
    # A framework that failed part-way is neither ranked nor published.
    summaries = {fw: s for fw, s in summaries.items() if fw not in errors}
    ranked = {fw: s for fw, s in summaries.items() if fw != BASELINE}
    out = {"title": title, "unit": unit, "superlative": superlative,
           "lower_is_better": lower, "summary": summaries,
           "ranking": stats.rank(ranked, lower), "errors": errors}
    if BASELINE in summaries:
        out["baseline"] = BASELINE
    out.update(extra)
    return out


def summarize_all(samples: dict, seed: int) -> dict:
    return {fw: stats.summarize(xs, seed) for fw, xs in samples.items() if xs}


def build_results(args, fws, info, s1, s2, s3, s3_legacy, s4, s5, s6, egress) -> dict:
    seed = args.seed
    metrics = {}
    if s1:
        sums = summarize_all(s1["samples"], seed)
        for fw, extra in s1["extra"].items():
            if fw in sums:
                sums[fw].update(extra)
        metrics["cold_import_ms"] = metric("cold_import_ms", sums, s1["errors"],
                                           statements=s1["statements"])
    if s2:
        metrics["first_response_ms"] = metric("first_response_ms",
                                              summarize_all(s2["samples"], seed), s2["errors"])
    if s3:
        metrics["instantiate_us"] = metric(
            "instantiate_us", summarize_all(s3["samples"], seed), s3["errors"],
            note="median of per-process medians; tool wrapped outside the timed region",
            legacy_praisonai={fw: stats.summarize(xs, seed)
                              for fw, xs in s3_legacy["samples"].items() if xs})
    if s4:
        passed = [fw for fw, c in s4["contract"].items() if c["passed"]]
        errs = {fw: "contract failed" if "error" not in c else c["error"]
                for fw, c in s4["contract"].items() if not c["passed"]}
        acc = s4["acc"]
        for key, field in (("team3_run_ms", "run_ms"), ("team3_build_ms", "build_ms"),
                           ("team3_request_bytes", "request_bytes")):
            metrics[key] = metric(key, summarize_all({fw: acc[fw][field] for fw in passed}, seed),
                                  errs)
        if BASELINE in passed:
            base = acc[BASELINE]["run_ms"]
            over = {fw: stats.diff_summary(acc[fw]["run_ms"], base, 1 / 3, seed)
                    for fw in passed if fw != BASELINE}
            metrics["handoff_overhead_ms"] = metric(
                "handoff_overhead_ms", over, errs,
                note="(median(framework) - median(raw_openai)) / 3")
    if s5:
        tm, rss = s5
        metrics["memory_kib_per_agent"] = metric(
            "memory_kib_per_agent", summarize_all(tm["samples"], seed), tm["errors"], k=tm["k"])
        metrics["memory_rss_kib_per_agent"] = metric(
            "memory_rss_kib_per_agent", summarize_all(rss["samples"], seed), rss["errors"],
            k=rss["k"])
    if s6:
        for key, field in (("loc_lines", "lines"), ("loc_tokens", "tokens")):
            sums = {fw: {"median": c[field], "n": 1, "ci95": [c[field], c[field]]}
                    for fw, c in s6["counts"].items()}
            metrics[key] = metric(key, sums, s6["errors"], formatted=s6["formatted"])
    server = os.environ.get("GITHUB_SERVER_URL")
    run_url = (f"{server}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
               if server and os.environ.get("GITHUB_RUN_ID") else None)
    return {
        "schema": 1,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": _out(["git", "rev-parse", "HEAD"]),
        "run_url": run_url,
        "seed": seed, "scale": args.scale,
        "workdir": "git" if args.git_workdir else "non-git",
        "uv": _out(["uv", "--version"]),
        "stub_version": _stub_version(),
        "machine": machine_info(),
        "frameworks": info,
        "contract": s4["contract"] if s4 else {},
        "egress_violations": egress,
        "metrics": metrics,
    }


def _stub_version() -> str:
    for line in (HERE / "stub" / "server.py").read_text().splitlines():
        if line.startswith("STUB_VERSION"):
            return line.split("=", 1)[1].strip().strip('"')
    return "?"


def markdown_summary(res: dict) -> str:
    lines = [f"## Cross-framework benchmark ({res['generated']})", ""]
    if res["egress_violations"]:
        lines += ["**Egress violations:** " + json.dumps(res["egress_violations"]), ""]
    for key, m in res["metrics"].items():
        lines += [f"### {m['title']} ({m['unit']})", "",
                  "| Rank | Framework | Median | p95 | 95% CI | × best |", "|---|---|---|---|---|---|"]
        for e in m["ranking"]["order"]:
            s = m["summary"][e["framework"]]
            ratio = f"{e['ratio_to_best']:.2f}×" if e["ratio_to_best"] else "—"
            ci = e["ci95"] or [s["median"]] * 2
            lines.append(f"| {e['rank']} | {e['framework']} | {s['median']:.4g} | "
                         f"{s.get('p95', s['median']):.4g} | {ci[0]:.4g}–{ci[1]:.4g} | {ratio} |")
        if m.get("baseline") in m["summary"]:
            lines.append(f"| — | {m['baseline']} (baseline) | {m['summary'][m['baseline']]['median']:.4g} | | | |")
        for fw, err in m["errors"].items():
            lines.append(f"| — | {fw} | {err[:80]} | | | |")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- main

def start_stub(latency_ms: float):
    cpus = pinned_cpus()
    pin = ["taskset", "-c", str(cpus[0])] if cpus else []
    proc = subprocess.Popen([*pin, sys.executable, str(HERE / "stub" / "server.py"),
                             "--latency-ms", str(latency_ms)],
                            stdout=subprocess.PIPE, text=True)
    line = proc.stdout.readline()
    if not line.startswith("READY "):
        proc.kill()
        raise RuntimeError(f"stub failed to start: {line!r}")
    return proc, f"http://127.0.0.1:{int(line.split()[1])}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cross-framework benchmark harness")
    p.add_argument("--frameworks", default="all")
    p.add_argument("--scenarios", default=",".join(SCENARIOS))
    p.add_argument("--scale", type=float, default=1.0, help="multiplies every sample count")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--frozen", action="store_true", help="uv sync --frozen (use committed locks)")
    p.add_argument("--python", action="append", default=[], metavar="FW=PATH",
                   help="use this interpreter instead of syncing the framework's venv")
    p.add_argument("--timeout", type=int, default=300, help="per-probe timeout (s)")
    p.add_argument("--latency-ms", type=float, default=0.0, help="stub latency per request")
    p.add_argument("--git-workdir", action="store_true",
                   help="run probes inside a git repo (canonical run is non-git)")
    p.add_argument("--strict", action="store_true",
                   help="also fail when a framework, probe or contract fails (PR smoke run)")
    p.add_argument("--out", default=str(HERE / "results"))
    p.add_argument("--raw", help="write raw samples here (default: <out>/raw/<date>.json)")
    args = p.parse_args(argv)

    all_fws = sorted(d.name for d in (HERE / "frameworks").iterdir() if d.is_dir())
    fws = all_fws if args.frameworks == "all" else args.frameworks.split(",")
    unknown = set(fws) - set(all_fws)
    if unknown:
        p.error(f"unknown frameworks: {sorted(unknown)}")
    wanted = set(args.scenarios.split(","))
    overrides = dict(item.split("=", 1) for item in args.python)

    pythons, info = {}, {}
    for fw in fws:
        try:
            pythons[fw] = Path(overrides[fw]) if fw in overrides else sync_env(fw, args.frozen)
            info[fw] = json.loads(subprocess.run(
                [str(pythons[fw]), str(HERE / "probes" / "env_info.py")],
                capture_output=True, text=True, check=True).stdout)
        except (subprocess.CalledProcessError, OSError, ValueError) as e:
            log(f"{fw}: environment failed: {e}")
            info[fw] = {"error": f"environment failed: {e}"}
            pythons.pop(fw, None)
    fws = [fw for fw in fws if fw in pythons]

    workdir = tempfile.mkdtemp(prefix="bench-wd-")
    if args.git_workdir:
        subprocess.run(["git", "init", "-q", workdir], check=True)
    stub, url = start_stub(args.latency_ms)
    raw: dict = {}
    s1 = s2 = s3 = s3_legacy = s4 = s5 = s6 = None
    try:
        rn = Runner(args, pythons, url, workdir)
        sc = args.scale
        if "s1" in wanted:
            log("S1 cold import")
            s1 = run_s1(rn, fws, scaled(30, sc, 3), raw)
        if "s2" in wanted:
            log("S2 cold time to first response")
            s2 = run_s2(rn, fws, scaled(30, sc, 3))
        if "s3" in wanted:
            log("S3 instantiation")
            s3, s3_legacy = run_s3(rn, fws, scaled(5, sc, 2), scaled(1000, sc, 100), raw)
        if "s4" in wanted or "s6" in wanted:
            log("S4 3-agent sequential pipeline")
            s4 = run_s4(rn, fws, scaled(5, sc, 1), scaled(30, sc, 3), raw)
        if "s5" in wanted:
            log("S5 memory per agent")
            s5 = run_s5(rn, fws, scaled(5, sc, 2), scaled(200, min(sc, 1.0), 20))
        if "s6" in wanted:
            log("S6 lines of code")
            s6 = run_s6(fws, s4["contract"])
        egress = rn.egress
    finally:
        stub.terminate()
        shutil.rmtree(workdir, ignore_errors=True)

    res = build_results(args, fws, info, s1, s2, s3, s3_legacy, s4, s5, s6, egress)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    date = res["generated"][:10]
    for name in (f"{date}.json", "latest.json"):
        (out / name).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    raw_path = Path(args.raw) if args.raw else out / "raw" / f"{date}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(raw) + "\n")
    summary = markdown_summary(res)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary + "\n")
    if egress:
        log(f"FAIL: non-loopback connections attempted: {egress}")
        return 1
    if args.strict:
        failures = [f"{fw}: {i['error']}" for fw, i in info.items() if "error" in i]
        failures += [f"{key} {fw}: {err[:120]}"
                     for key, m in res["metrics"].items() for fw, err in m["errors"].items()]
        failures += [f"contract {fw}" for fw, c in res["contract"].items() if not c["passed"]]
        if failures:
            log("FAIL (--strict): " + "; ".join(failures))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
