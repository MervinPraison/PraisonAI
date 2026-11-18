import datetime
import json
import pathlib
import uuid

from praisonai.db.adapter import PraisonAIDB


def test_serialize_tool_call_handles_non_json_native_args():
    when = datetime.datetime(2026, 1, 2, 3, 4, 5)
    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    out = PraisonAIDB._serialize_tool_call(
        "t",
        {"when": when, "path": pathlib.Path("/tmp/x"), "id": uid, "raw": b"ab"},
        {"ok": True},
    )
    data = json.loads(out)
    assert data["tool"] == "t"
    assert data["args"]["when"] == str(when)
    assert data["args"]["path"] == str(pathlib.Path("/tmp/x"))
    assert data["args"]["id"] == str(uid)
    assert data["result"] == str({"ok": True})


def test_serialize_tool_call_json_native_args_unchanged():
    out = PraisonAIDB._serialize_tool_call("t", {"a": 1, "b": [1, "x"]}, "r")
    assert json.loads(out) == {"tool": "t", "args": {"a": 1, "b": [1, "x"]}, "result": "r"}
