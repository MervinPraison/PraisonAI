#!/usr/bin/env python3
"""Test that our sys.stdin null check handles None properly."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.planning.approval import ApprovalCallback
from praisonaiagents.planning.plan import Plan

# Temporarily set stdin to None to simulate GUI/daemon environment
original_stdin = sys.stdin
sys.stdin = None

try:
    plan = Plan(
        name="test_plan",
        description="Test plan for null stdin"
    )
    
    callback = ApprovalCallback(auto_approve=False)
    
    # This should not crash with AttributeError
    result = callback(plan)
    assert result == True, "Plan should be auto-approved when stdin is None"
    
    print("✅ Null stdin check works correctly - no AttributeError")
    
finally:
    # Restore stdin
    sys.stdin = original_stdin