import json

import proof_points as pp
import pytest

README = """# X

## ⚡ Performance

Intro without numbers.

<!-- proof-points:begin performance -->
<!-- proof-points:end performance -->

## Next

Outside the guarded section: 14 μs is fine here.
"""


def summary(median, lo, hi, n=10):
    return {"median": median, "p95": hi, "ci95": [lo, hi], "n": n}


def results(praison_import=(95.0, 94.0, 96.0), generated="2026-10-01T04:00:00+00:00"):
    fws = ["praisonai", "praisonai_release", "raw_openai", "agno", "crewai"]
    return {
        "generated": generated, "commit": "abc", "run_url": "https://example/run/1",
        "machine": {"runner_image": "ubuntu24", "cpu": "cpu"},
        "frameworks": {fw: {"versions": {pp.DIST[fw]: "1.0"}} for fw in fws},
        "metrics": {
            "cold_import_ms": {
                "title": "Cold import", "unit": "ms", "superlative": "fastest",
                "lower_is_better": True, "errors": {"crewai": "timeout after 300s"},
                "summary": {"praisonai": summary(90, 89, 91),
                            "praisonai_release": summary(*praison_import),
                            "raw_openai": summary(50, 49, 51), "agno": summary(368, 360, 376)}},
            "instantiate_us": {
                "title": "Agent instantiation (one tool)", "unit": "μs", "superlative": "fastest",
                "lower_is_better": True, "errors": {},
                "summary": {"praisonai_release": summary(37.2, 36, 38), "agno": summary(6.1, 6, 6.2)}},
        },
    }


@pytest.fixture
def repo(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(README)
    res = tmp_path / "latest.json"
    res.write_text(json.dumps(results()))
    base = ["--results", str(res), "--readme", str(readme), "--out-dir", str(tmp_path),
            "--today", "2026-10-02"]
    return tmp_path, readme, res, base


def test_build_ranks_released_praisonai_without_baseline():
    out = pp.build(results())
    m = out["metrics"]["cold_import_ms"]
    assert out["quoted"] == "praisonai_release"
    assert [e["framework"] for e in m["ranking"]] == ["praisonai_release", "agno"]
    assert (m["praisonai_rank"], m["of"], m["label"]) == (1, 2, "fastest")
    assert m["failed"] == {"crewai": "timeout after 300s"}


def test_no_superlative_when_praisonai_second():
    m = pp.build(results())["metrics"]["instantiate_us"]
    assert (m["praisonai_rank"], m["label"]) == (2, None)
    assert "ranks 2nd of 2" in pp.sentence(pp.build(results()), "instantiate_us")


def test_overlapping_ci_is_a_tie():
    out = pp.build(results(praison_import=(95.0, 90.0, 370.0)))
    assert out["metrics"]["cold_import_ms"]["label"] == "tied for first within noise"


def test_write_is_idempotent_and_check_passes(repo):
    tmp, readme, _, base = repo
    assert pp.main(base + ["--write"]) == 0
    first = readme.read_text()
    assert "1st of 2 · fastest" in first and "Agno 6.10 μs" in first
    assert (tmp / "proof_points.md").exists() and (tmp / "proof_points.json").exists()
    assert pp.main(base + ["--write"]) == 0
    assert readme.read_text() == first
    assert pp.main(base + ["--check"]) == 0


def test_check_detects_drift(repo):
    tmp, readme, res, base = repo
    pp.main(base + ["--write"])
    data = results()
    data["metrics"]["instantiate_us"]["summary"]["agno"] = summary(99, 98, 100)
    res.write_text(json.dumps(data))
    assert pp.main(base + ["--check"]) == 1


def test_stray_number_lint(repo):
    tmp, readme, _, base = repo
    pp.main(base + ["--write"])
    assert pp.stray_numbers(readme.read_text()) == []  # numbers inside markers are fine
    readme.write_text(readme.read_text().replace("Intro without numbers.", "Instantiates in 14 μs."))
    assert pp.stray_numbers(readme.read_text()) == ["14 μs"]
    assert pp.main(base + ["--check"]) == 1


def test_missing_markers_fail(repo):
    tmp, readme, _, base = repo
    readme.write_text("## ⚡ Performance\n")
    assert pp.main(base + ["--check"]) == 1


def test_placeholder_without_results(repo, tmp_path):
    _, readme, _, _ = repo
    args = ["--results", str(tmp_path / "missing.json"), "--readme", str(readme),
            "--out-dir", str(tmp_path)]
    assert pp.main(args + ["--write"]) == 0
    assert "No published benchmark run yet" in readme.read_text()
    assert pp.main(args + ["--check"]) == 0


def test_stale_badge_after_30_days(repo, capsys):
    tmp, readme, _, base = repo
    pp.main(base + ["--write"])
    late = base[:-1] + ["2026-11-15"]
    assert pp.main(late + ["--check"]) == 0  # an up-to-date block only warns
    assert "days old" in capsys.readouterr().err
    pp.main(late + ["--write"])
    assert "Stale:" in readme.read_text()
    assert pp.main(late + ["--check"]) == 0
