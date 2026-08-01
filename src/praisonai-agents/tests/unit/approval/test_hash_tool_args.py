"""
Regression tests for the shared tool-argument identity hash.

``hash_tool_args`` is the single source of truth for the tool-call identity
key shared by approval de-duplication (``ApprovalRegistry``) and doom-loop
detection (``DoomLoopDetector``). These tests pin the exact digest scheme so
the two safety subsystems cannot silently diverge.
"""

from __future__ import annotations

import hashlib
import json


def _expected(arguments) -> str:
    payload = json.dumps(arguments or {}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class TestHashToolArgs:
    def test_none_and_empty_are_equivalent(self):
        from praisonaiagents.approval.utils import hash_tool_args

        assert hash_tool_args(None) == hash_tool_args({})
        assert hash_tool_args(None) == _expected({})

    def test_key_order_is_canonical(self):
        from praisonaiagents.approval.utils import hash_tool_args

        assert hash_tool_args({"a": 1, "b": 2}) == hash_tool_args({"b": 2, "a": 1})

    def test_default_str_serialization(self):
        from praisonaiagents.approval.utils import hash_tool_args

        class Obj:
            def __str__(self) -> str:
                return "obj-repr"

        args = {"x": Obj()}
        assert hash_tool_args(args) == _expected(args)

    def test_unhashable_fallback(self):
        from praisonaiagents.approval.utils import hash_tool_args

        class Boom:
            def __str__(self) -> str:
                raise TypeError("cannot stringify")

        assert hash_tool_args({"x": Boom()}) == "unhashable"

    def test_digest_is_16_chars(self):
        from praisonaiagents.approval.utils import hash_tool_args

        assert len(hash_tool_args({"tool": "call"})) == 16


class TestIdentityParity:
    """The approval and doom-loop call sites must agree on identity."""

    def test_registry_and_doom_loop_share_identity(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.utils import hash_tool_args
        from praisonaiagents.permissions.doom_loop import DoomLoopDetector

        args = {"command": "git status", "flag": True}

        registry_key = ApprovalRegistry._approval_cache_key("execute_command", args)
        doom_hash = DoomLoopDetector()._hash_arguments(args)

        assert registry_key == f"execute_command:{doom_hash}"
        assert doom_hash == hash_tool_args(args)

    def test_reordered_args_yield_same_identity(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.permissions.doom_loop import DoomLoopDetector

        a = {"command": "ls", "path": "/tmp"}
        b = {"path": "/tmp", "command": "ls"}

        assert ApprovalRegistry._approval_cache_key(
            "execute_command", a
        ) == ApprovalRegistry._approval_cache_key("execute_command", b)
        assert DoomLoopDetector()._hash_arguments(a) == DoomLoopDetector()._hash_arguments(b)
