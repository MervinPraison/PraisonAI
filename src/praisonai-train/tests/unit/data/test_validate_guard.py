"""Tests for the ``validate`` command's zero-kept guard and atomic --out write.

These mirror the ``dedup``/``generate`` sibling guarantees: a run that keeps no
rows must (a) exit non-zero and (b) leave any existing ``--out`` file intact
rather than truncating it to 0 bytes — the loss reported in issue #4315.
"""
import json

import pytest
from typer.testing import CliRunner

from praisonai_train.cli.commands.train import app
from praisonai_train.cli.commands import data as data_cmd  # noqa: F401  (registers cmds)

runner = CliRunner()


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


# English rows that fail the Tamil script-purity default -> everything dropped.
_ENGLISH = [{"instruction": f"q{i}", "input": "",
             "output": "Entirely english output text here"} for i in range(5)]
# Tamil rows that survive the default filter.
_TAMIL = [{"instruction": f"கே{i}", "input": "",
           "output": "ஒரு முழுமையான தமிழ் பதில் இங்கே உள்ளது."} for i in range(5)]


def test_validate_zero_kept_exits_nonzero(tmp_path):
    src = tmp_path / "english.jsonl"
    _write_jsonl(src, _ENGLISH)
    out = tmp_path / "clean.jsonl"
    result = runner.invoke(app, ["validate", str(src), "--out", str(out)])
    assert result.exit_code == 1
    # No 0-byte file is left behind when nothing was kept.
    assert not out.exists()


def test_validate_zero_kept_leaves_existing_out_intact(tmp_path):
    # --out aliases an existing corpus; a zero-kept run must not destroy it.
    corpus = tmp_path / "corpus.jsonl"
    _write_jsonl(corpus, _TAMIL)          # existing good corpus
    before = corpus.read_bytes()

    src = tmp_path / "english.jsonl"
    _write_jsonl(src, _ENGLISH)
    result = runner.invoke(app, ["validate", str(src), "--out", str(corpus)])
    assert result.exit_code == 1
    assert corpus.read_bytes() == before  # untouched, not truncated


def test_validate_keeps_rows_and_writes(tmp_path):
    src = tmp_path / "tamil.jsonl"
    _write_jsonl(src, _TAMIL)
    out = tmp_path / "clean.jsonl"
    result = runner.invoke(app, ["validate", str(src), "--out", str(out)])
    assert result.exit_code == 0
    lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 1
