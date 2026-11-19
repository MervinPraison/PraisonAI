"""The Python screen must follow the ways code reaches a blocked module or call.

Static screening is a safety net, not isolation (SECURITY.md). But it must not
miss the standard spellings: the alias check covered `import os as x` while
`__import__('os').system(...)`, `importlib.import_module(...)` and
`getattr(__builtins__, 'eval')` passed untouched under the default policy.
"""
import pytest

from praisonaiagents.sandbox.config import SandboxConfig, SecurityPolicy
from praisonai_sandbox.subprocess import SubprocessSandbox


def _check(code, **fields):
    policy = SecurityPolicy(**{"allow_network": True, "allow_subprocess": True, **fields})
    sandbox = SubprocessSandbox(SandboxConfig(security_policy=policy))
    return sandbox._validate_code_against_policy(code, "python", policy)


@pytest.mark.parametrize("code", [
    "__import__('os').system('echo hi')",
    "__import__('subprocess').run(['id'])",
    "import importlib\nimportlib.import_module('subprocess')",
    "from importlib import import_module\nimport_module('subprocess')",
    "import importlib\nname = 'sub' + 'process'\nimportlib.import_module(name)",
    "getattr(__builtins__, 'eval')('1')",
    "import os\ngetattr(os, 'system')('id')",
    "getattr(__import__('os'), 'system')('id')",
    "globals()['__builtins__']",
    "().__class__.__base__.__subclasses__()",
    "e = eval\ne('1')",
    "import os.path\nos.system('id')",
    "import posix\nposix.system('id')",
    "from posix import system\nsystem('id')",
    "import builtins\nbuiltins.exec('1')",
])
def test_default_policy_refuses(code):
    assert _check(code) is not None


@pytest.mark.parametrize("code", [
    "import json\nprint(json.dumps({'a': 1}))",
    "print('subprocess and eval are just words here')",
    "import os\nprint(os.path.join('a', 'b'))",
    "x = __import__('json')\nprint(x.dumps(1))",
    "subprocess = 3\nprint(subprocess)",
])
def test_default_policy_allows_ordinary_code(code):
    assert _check(code) is None


def test_allowed_imports_is_an_allowlist():
    assert _check("import json", allowed_imports=["json"]) is None
    assert _check("import socket", allowed_imports=["json"]) is not None
    assert _check("__import__('socket')", allowed_imports=["json"]) is not None


@pytest.mark.parametrize("code", [
    "import os\nos.fork()",
    "import os\nos.execv('/bin/sh', ['sh'])",
    "import os\nos.posix_spawn('/bin/sh', ['sh'], {})",
    "import multiprocessing",
    "import asyncio\nasyncio.create_subprocess_exec('id')",
])
def test_allow_subprocess_false_screens_process_creation(code):
    assert _check(code, allow_subprocess=False, blocked_imports=[]) is not None
    assert _check(code, allow_subprocess=True, blocked_imports=[]) is None


def test_blocked_paths_apply_to_path_literals():
    assert _check("open('/etc/hosts').read()", blocked_paths=["/etc/hosts"]) is not None
    assert _check("open('notes.txt', 'w')", blocked_paths=["/etc/hosts"]) is None
