"""CoT dataset helpers read only inside the working directory.

The write helpers are probed by ``test_path_containment_guard``; a read of a
non-JSON canary cannot show there, so the two readers are checked here.
"""

import json
import sys
import types

import pytest


@pytest.fixture
def gen(tmp_path, monkeypatch):
    from praisonaiagents.tools.train.data.generatecot import GenerateCOT

    ws, outside = tmp_path / "ws", tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    (outside / "answers.json").write_text(json.dumps({"secret-q": "secret-a"}))
    (outside / "data.csv").write_text("instruction,input,output\n")
    (ws / "answers.json").write_text(json.dumps({"q": "a"}))
    monkeypatch.chdir(ws)
    return GenerateCOT(), outside


@pytest.mark.parametrize("ref", ["absolute", "dotdot"])
def test_load_answers_refuses_outside(gen, ref):
    g, outside = gen
    path = str(outside / "answers.json") if ref == "absolute" else "../outside/answers.json"
    assert g.cot_load_answers(path) is False
    assert "secret-q" not in g.qa_pairs


def test_load_answers_inside_still_works(gen):
    g, _ = gen
    assert g.cot_load_answers("answers.json") is True and g.qa_pairs == {"q": "a"}


def test_upload_does_not_read_outside(gen, monkeypatch):
    g, outside = gen
    read = []
    pandas = types.SimpleNamespace(read_csv=lambda p: read.append(p) or [], read_json=lambda p: read.append(p) or [])
    datasets = types.SimpleNamespace(Dataset=types.SimpleNamespace(
        from_pandas=lambda d: types.SimpleNamespace(push_to_hub=lambda *a, **k: None)))
    monkeypatch.setitem(sys.modules, "pandas", pandas)
    monkeypatch.setitem(sys.modules, "datasets", datasets)
    assert g.cot_upload_to_huggingface("u", "d", str(outside / "data.csv")) is None
    assert read == []
