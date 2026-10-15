#!/usr/bin/env python3
"""Generate dated proof points from cross-framework benchmark results.

Reads ``benchmarks/compare/results/latest.json`` (written by
``benchmarks/compare/run.py``) and produces:

- ``benchmarks/compare/results/proof_points.json`` — per metric, the full
  ranking, PraisonAI's rank and the label the publishing rules allow;
- ``benchmarks/compare/results/proof_points.md`` — full ranking tables;
- the content between ``<!-- proof-points:begin performance -->`` and
  ``<!-- proof-points:end performance -->`` in the three README copies;
- optionally a Mintlify snippet (``--docs-snippet``) for PraisonAIDocs.

``--check`` fails when a generated file or marker block is out of date, or when
a guarded section (README ``## ⚡ Performance``) contains a hand-typed number
with a unit outside a marker block. Stale results (older than 30 days) get a
badge on ``--write`` and a warning on ``--check``.

Usage:
    python scripts/proof_points.py [--results PATH] (--write | --check) [--docs-snippet PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BENCH = REPO / "benchmarks" / "compare"
sys.path.insert(0, str(BENCH))

import stats  # noqa: E402  (benchmarks/compare/stats.py, stdlib only)

RESULTS = BENCH / "results" / "latest.json"
OUT_JSON = BENCH / "results" / "proof_points.json"
OUT_MD = BENCH / "results" / "proof_points.md"
# src/praisonai-agents/README.md is a symlink to the root README; dedupe on resolve().
READMES = list(dict.fromkeys(p.resolve() for p in (
    REPO / "README.md", REPO / "src" / "praisonai" / "README.md",
    REPO / "src" / "praisonai-agents" / "README.md")))
GUARDED_HEADING = "## ⚡ Performance"
BLOCK = "performance"
BEGIN = f"<!-- proof-points:begin {BLOCK} -->"
END = f"<!-- proof-points:end {BLOCK} -->"
# READMEs also ship to PyPI, so links must be absolute.
BLOB = "https://github.com/MervinPraison/PraisonAI/blob/main/benchmarks/compare"
STALE_DAYS = 30
# Docs quote the released PraisonAI; main is the fallback (and is labelled).
QUOTED = ("praisonai_release", "praisonai")
BASELINE = "raw_openai"
# Metrics in the README summary; proof_points.md lists every metric.
HEADLINE = ("cold_import_ms", "first_response_ms", "instantiate_us", "handoff_overhead_ms",
            "memory_kib_per_agent", "loc_lines", "team3_request_bytes")
NAMES = {"praisonai": "PraisonAI (main)", "praisonai_release": "PraisonAI",
         "raw_openai": "raw openai SDK", "langgraph": "LangGraph", "crewai": "CrewAI",
         "agno": "Agno", "openai_agents": "OpenAI Agents SDK", "autogen": "AutoGen"}
DIST = {"praisonai": "praisonaiagents", "praisonai_release": "praisonaiagents",
        "raw_openai": "openai", "langgraph": "langgraph", "crewai": "crewai", "agno": "agno",
        "openai_agents": "openai-agents", "autogen": "autogen-agentchat"}
STRAY = re.compile(r"\d[\d,.]*\s*(?:μs|µs|us|ms|KiB|KB|MB|x faster|× faster)\b")


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def fmt(v) -> str:
    if v is None:
        return "—"
    if float(v).is_integer() and abs(v) < 1000:
        return str(int(v))
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def name(fw: str) -> str:
    return NAMES.get(fw, fw)


def version(res: dict, fw: str) -> str:
    return res["frameworks"].get(fw, {}).get("versions", {}).get(DIST.get(fw, fw), "?")


# ----------------------------------------------------------------- proof points

def build(res: dict) -> dict:
    quoted = next((fw for fw in QUOTED if fw in res["frameworks"]
                   and "error" not in res["frameworks"][fw]), None)
    drop = {fw for fw in QUOTED if fw != quoted}
    metrics = {}
    for key, m in res["metrics"].items():
        sums = {fw: s for fw, s in m["summary"].items() if fw not in drop and fw != BASELINE}
        ranking = stats.rank(sums, m["lower_is_better"])
        order = ranking["order"]
        entry = next((e for e in order if e["framework"] == quoted), None)
        label = None
        if entry and entry["rank"] == 1:
            label = m["superlative"] if ranking["leader"] == "clear" else "tied for first within noise"
        metrics[key] = {
            "title": m["title"], "unit": m["unit"],
            "ranking": [dict(e, version=version(res, e["framework"]),
                             p95=m["summary"][e["framework"]].get("p95"),
                             n=m["summary"][e["framework"]].get("n")) for e in order],
            "baseline": m["summary"].get(BASELINE),
            "failed": {fw: err for fw, err in m["errors"].items() if fw not in drop},
            "praisonai_rank": entry["rank"] if entry else None,
            "praisonai_value": entry["median"] if entry else None,
            "of": len(order), "label": label,
        }
    return {
        "generated": res["generated"], "source_run": res.get("run_url"),
        "commit": res.get("commit"), "machine": res.get("machine"),
        "quoted": quoted, "praisonai_version": version(res, quoted) if quoted else None,
        "metrics": metrics,
    }


def sentence(pp: dict, key: str) -> str:
    m = pp["metrics"][key]
    title = m["title"][0].lower() + m["title"][1:]
    if m["praisonai_rank"] is None:
        why = m["failed"].get(pp["quoted"], "not measured")
        return f"PraisonAI: {why} in {title}."
    text = f"PraisonAI ranks {ordinal(m['praisonai_rank'])} of {m['of']} in {title}"
    return text + (f": {m['label']}." if m["label"] else ".")


def provenance(pp: dict) -> str:
    mach = pp["machine"] or {}
    where = mach.get("runner_image") or mach.get("platform", "?")
    if mach.get("runner_image_version"):
        where += f" {mach['runner_image_version']}"
    run = f", [run]({pp['source_run']})" if pp.get("source_run") else ""
    who = "PraisonAI" if pp["quoted"] == "praisonai_release" else "PraisonAI main"
    return (f"{pp['generated'][:10]} · {who} {pp['praisonai_version']} · {where}, "
            f"{mach.get('cpu', '?')}{run}")


def stale_days(pp: dict | None, today: dt.date) -> int | None:
    if not pp:
        return None
    age = (today - dt.date.fromisoformat(pp["generated"][:10])).days
    return age if age > STALE_DAYS else None


def render_block(pp: dict | None, stale: int | None = None) -> str:
    if not pp:
        return ("_No published benchmark run yet. These numbers are generated by the "
                f"[cross-framework harness]({BLOB}) once its first weekly run is merged._")
    lines = []
    if stale:
        lines += [f"> ⚠️ **Stale:** these results are {stale} days old.", ""]
    lines += [f"_Generated by `scripts/proof_points.py` · {provenance(pp)}. "
              f"Same task in every framework against a local mock LLM; lower is better. "
              f"Full rankings, versions and 95% CIs: [proof_points.md]({BLOB}/results/proof_points.md)._",
              "", "| Metric | PraisonAI | Rank | Best |", "|---|---|---|---|"]
    for key in HEADLINE:
        m = pp["metrics"].get(key)
        if not m:
            continue
        best = m["ranking"][0] if m["ranking"] else None
        rank = (f"{ordinal(m['praisonai_rank'])} of {m['of']}" if m["praisonai_rank"]
                else "not ranked")
        if m["label"]:
            rank += f" · {m['label']}"
        best_txt = f"{name(best['framework'])} {fmt(best['median'])} {m['unit']}" if best else "—"
        lines.append(f"| {m['title']} | {fmt(m['praisonai_value'])} {m['unit']} | {rank} | {best_txt} |")
    return "\n".join(lines)


def render_md(pp: dict) -> str:
    out = ["# Proof points", "", f"_{provenance(pp)}. Generated by `scripts/proof_points.py`; "
           "do not edit by hand._", ""]
    for key, m in pp["metrics"].items():
        out += [f"## {m['title']} ({m['unit']})", "", sentence(pp, key), "",
                "| Rank | Framework | Version | Median | p95 | 95% CI | n | × best |",
                "|---|---|---|---|---|---|---|---|"]
        for e in m["ranking"]:
            ci = e["ci95"] or [e["median"], e["median"]]
            ratio = f"{e['ratio_to_best']:.2f}×" if e["ratio_to_best"] else "—"
            out.append(f"| {e['rank']} | {name(e['framework'])} | {e['version']} | {fmt(e['median'])} "
                       f"| {fmt(e['p95'])} | {fmt(ci[0])}–{fmt(ci[1])} | {e['n']} | {ratio} |")
        if m["baseline"]:
            out.append(f"| — | raw openai SDK (baseline) | | {fmt(m['baseline']['median'])} | | | | |")
        for fw, err in m["failed"].items():
            out.append(f"| — | {name(fw)} | | {err.splitlines()[0][:100]} | | | | |")
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------- markers and lint

def replace_block(text: str, content: str) -> str | None:
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < i:
        return None
    return text[:i + len(BEGIN)] + "\n" + content + "\n" + text[j:]


def stray_numbers(text: str) -> list[str]:
    """Numbers with units inside the guarded section but outside marker blocks."""
    start = text.find(GUARDED_HEADING)
    if start < 0:
        return []
    nxt = re.search(r"^## ", text[start + len(GUARDED_HEADING):], re.M)
    section = text[start:start + len(GUARDED_HEADING) + nxt.start()] if nxt else text[start:]
    section = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), "", section, flags=re.S)
    return STRAY.findall(section)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--results", type=Path, default=RESULTS)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    p.add_argument("--docs-snippet", type=Path, help="also write this Mintlify snippet (.mdx)")
    p.add_argument("--readme", type=Path, action="append", help=argparse.SUPPRESS)
    p.add_argument("--out-dir", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today(),
                   help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    readmes = args.readme or READMES
    out_json = args.out_dir / OUT_JSON.name if args.out_dir else OUT_JSON
    out_md = args.out_dir / OUT_MD.name if args.out_dir else OUT_MD

    pp = build(json.loads(args.results.read_text())) if args.results.exists() else None
    stale = stale_days(pp, args.today)
    files: dict[Path, str] = {}
    if pp:
        files[out_json] = json.dumps(pp, indent=1, ensure_ascii=False) + "\n"
        files[out_md] = render_md(pp) + "\n"
    if args.docs_snippet:
        files[args.docs_snippet] = render_block(pp, stale) + "\n"

    problems = []
    for readme in readmes:
        text = readme.read_text()
        fresh = replace_block(text, render_block(pp, stale))
        if fresh is None:
            problems.append(f"{readme}: missing {BEGIN} … {END} markers")
            continue
        files[readme] = fresh
        if args.check:
            # A block written before the results went stale is still up to date.
            if text not in (fresh, replace_block(text, render_block(pp))):
                problems.append(f"{readme}: proof-points block is out of date")
            stray = stray_numbers(text)
            if stray:
                problems.append(f"{readme}: hand-typed numbers in '{GUARDED_HEADING}' outside "
                                f"the proof-points block: {stray}")

    if args.write:
        for path, content in files.items():
            if not path.exists() or path.read_text() != content:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                print(f"wrote {path}")
    else:
        for path in (out_json, out_md):
            if path in files and (not path.exists() or path.read_text() != files[path]):
                problems.append(f"{path}: out of date")
        if stale:
            print(f"warning: benchmark results are {stale} days old", file=sys.stderr)
    for msg in problems:
        print(f"error: {msg}", file=sys.stderr)
    if problems:
        print("run: python scripts/proof_points.py --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
