"""
Regression tests for the HOL Guard tool policy example.

Proves the `wrap_tool_call` middleware in
`examples/middleware/hol_guard_tool_policy.py` is fail-closed: the wrapped tool
executor is only reached when HOL Guard returns an explicit allow verdict.
Every other verdict/error path short-circuits with zero downstream execution.
"""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from praisonaiagents.hooks import ToolRequest


def _find_example_path():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "examples" / "middleware" / "hol_guard_tool_policy.py"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("hol_guard_tool_policy.py example not found")


_EXAMPLE_PATH = _find_example_path()


def _load_example():
    spec = importlib.util.spec_from_file_location(
        "hol_guard_tool_policy_example", _EXAMPLE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_request(command="echo hi", tool_name="run_shell"):
    return ToolRequest(tool_name=tool_name, arguments={"command": command})


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_explicit_allow_reaches_tool():
    module = _load_example()
    executed = []

    def call_next(req):
        executed.append(req)
        return "ran"

    with patch.object(module.shutil, "which", return_value="/usr/bin/hol-guard"), \
         patch.object(
             module.subprocess,
             "run",
             return_value=_FakeCompleted(0, json.dumps({"decision": "allow"})),
         ):
        result = module.hol_guard_tool_policy(_make_request(), call_next)

    assert result == "ran"
    assert len(executed) == 1


def test_block_verdict_does_not_execute():
    module = _load_example()
    executed = []

    def call_next(req):
        executed.append(req)
        return "ran"

    with patch.object(module.shutil, "which", return_value="/usr/bin/hol-guard"), \
         patch.object(
             module.subprocess,
             "run",
             return_value=_FakeCompleted(0, json.dumps({"decision": "block"})),
         ):
        result = module.hol_guard_tool_policy(_make_request("rm -rf /"), call_next)

    assert executed == []
    assert result.error is not None
    assert result.result is None


def test_missing_cli_fails_closed():
    module = _load_example()
    executed = []

    def call_next(req):
        executed.append(req)
        return "ran"

    with patch.object(module.shutil, "which", return_value=None):
        result = module.hol_guard_tool_policy(_make_request(), call_next)

    assert executed == []
    assert result.error is not None


def test_malformed_json_fails_closed():
    module = _load_example()
    executed = []

    def call_next(req):
        executed.append(req)
        return "ran"

    with patch.object(module.shutil, "which", return_value="/usr/bin/hol-guard"), \
         patch.object(
             module.subprocess,
             "run",
             return_value=_FakeCompleted(0, "not-json"),
         ):
        result = module.hol_guard_tool_policy(_make_request(), call_next)

    assert executed == []
    assert result.error is not None


def test_nonzero_exit_fails_closed():
    module = _load_example()
    executed = []

    def call_next(req):
        executed.append(req)
        return "ran"

    with patch.object(module.shutil, "which", return_value="/usr/bin/hol-guard"), \
         patch.object(
             module.subprocess,
             "run",
             return_value=_FakeCompleted(1, json.dumps({"decision": "allow"})),
         ):
        result = module.hol_guard_tool_policy(_make_request(), call_next)

    assert executed == []
    assert result.error is not None


def test_timeout_fails_closed():
    module = _load_example()
    executed = []

    def call_next(req):
        executed.append(req)
        return "ran"

    def _raise_timeout(*args, **kwargs):
        raise module.subprocess.TimeoutExpired(cmd="hol-guard", timeout=10)

    with patch.object(module.shutil, "which", return_value="/usr/bin/hol-guard"), \
         patch.object(module.subprocess, "run", side_effect=_raise_timeout):
        result = module.hol_guard_tool_policy(_make_request(), call_next)

    assert executed == []
    assert result.error is not None


def test_non_command_tool_passes_through_untouched():
    module = _load_example()
    executed = []

    def call_next(req):
        executed.append(req)
        return "ran"

    with patch.object(module.shutil, "which") as which_mock:
        result = module.hol_guard_tool_policy(
            _make_request(tool_name="get_weather"), call_next
        )

    which_mock.assert_not_called()
    assert result == "ran"
    assert len(executed) == 1
