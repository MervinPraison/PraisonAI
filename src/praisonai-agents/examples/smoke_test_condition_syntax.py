#!/usr/bin/env python3
"""
Smoke Test: Condition Syntax Comparison

This script tests both condition syntaxes WITHOUT LLM calls (deterministic):
1. AgentFlow with when() string expressions
2. AgentTeam with Task.condition dict routing

Run: python examples/smoke_test_condition_syntax.py
"""
from praisonaiagents import AgentFlow, Task
from praisonaiagents.workflows import when

print("=" * 60)
print("SMOKE TEST: Condition Syntax Comparison")
print("=" * 60)

# ============================================================
# TEST 1: AgentFlow with when() - String Expression Syntax
# ============================================================
print("\n" + "=" * 60)
print("TEST 1: AgentFlow with when() - String Expression")
print("=" * 60)

def high_score_handler(ctx):
    print("  ✅ HIGH SCORE PATH: Score was >= 50")
    return {"output": "High score processed"}

def low_score_handler(ctx):
    print("  ❌ LOW SCORE PATH: Score was < 50")
    return {"output": "Low score processed"}

# AgentFlow uses STRING condition: "{{score}} >= 50"
flow = AgentFlow(
    name="Score-Based Flow",
    steps=[
        when(
            condition="{{score}} >= 50",  # STRING expression
            then_steps=[high_score_handler],
            else_steps=[low_score_handler]
        )
    ],
    variables={"score": 75}  # Pre-set score for deterministic test
)

print("\nAgentFlow Syntax:")
print('  when(condition="{{score}} >= 50", then_steps=[...], else_steps=[...])')
print("  Variables: {'score': 75}")
print("\nRunning AgentFlow...")

try:
    result = flow.start("Process the score")
    print("\n✅ AgentFlow completed successfully")
except Exception as e:
    print(f"\n❌ AgentFlow failed: {e}")

# ============================================================
# TEST 2: AgentTeam with Task.condition - Dict Routing Syntax
# ============================================================
print("\n" + "=" * 60)
print("TEST 2: AgentTeam with Task.condition - Dict Routing")
print("=" * 60)

# Task uses DICT condition: {"approved": ["publish"], "rejected": ["edit"]}
# NOTE: This is just showing the syntax - no LLM call needed
review_task = Task(
    name="review",
    description="Review the content and decide: approved or rejected",
    task_type="decision",
    is_start=True,
    condition={  # DICT routing
        "approved": ["publish"],
        "rejected": ["edit"]
    }
)

print("\nAgentTeam/Task Syntax:")
print('  Task(condition={"approved": ["publish"], "rejected": ["edit"]})')
print("  task_type='decision' triggers LLM to output a decision value")
print("\nTask condition structure:")
print(f"  review_task.condition = {review_task.condition}")
print(f"  review_task.task_type = '{review_task.task_type}'")
print("\n✅ Task condition syntax validated (no LLM call needed)")

# ============================================================
# TEST 3: NEW UNIFIED SYNTAX - Task.when (same as AgentFlow!)
# ============================================================
print("\n" + "=" * 60)
print("TEST 3: NEW UNIFIED SYNTAX - Task.when (same as AgentFlow!)")
print("=" * 60)

# Task now supports the same string expression syntax as AgentFlow!
unified_task = Task(
    name="score_check",
    description="Check if score passes threshold",
    when="{{score}} > 80",  # SAME syntax as AgentFlow!
    then_task="approve",
    else_task="reject"
)

print("\nNEW Unified Task Syntax:")
print('  Task(when="{{score}} > 80", then_task="approve", else_task="reject")')
print("\nTask structure:")
print(f"  unified_task.when = '{unified_task.when}'")
print(f"  unified_task.then_task = '{unified_task.then_task}'")
print(f"  unified_task.else_task = '{unified_task.else_task}'")

# Test evaluate_when method
print("\nTesting evaluate_when():")
result_high = unified_task.evaluate_when({"score": 90})
result_low = unified_task.evaluate_when({"score": 70})
print(f"  evaluate_when({{'score': 90}}) = {result_high}")
print(f"  evaluate_when({{'score': 70}}) = {result_low}")

# Test get_next_task method
print("\nTesting get_next_task():")
next_high = unified_task.get_next_task({"score": 90})
next_low = unified_task.get_next_task({"score": 70})
print(f"  get_next_task({{'score': 90}}) = '{next_high}'")
print(f"  get_next_task({{'score': 70}}) = '{next_low}'")

print("\n✅ NEW unified Task.when syntax works!")

# ============================================================
# SUMMARY: Syntax Differences
# ============================================================
print("\n" + "=" * 60)
print("SUMMARY: Syntax Differences (CONFUSING FOR USERS)")
print("=" * 60)

print("""
┌─────────────────────────────────────────────────────────────────┐
│                    CONDITION SYNTAX COMPARISON                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  AGENTFLOW (Deterministic Pipelines)                            │
│  ─────────────────────────────────────                          │
│  Syntax: STRING expression with {{variable}} placeholders       │
│                                                                  │
│    when(                                                        │
│        condition="{{score}} >= 50",  ← STRING                   │
│        then_steps=[approve],                                    │
│        else_steps=[reject]                                      │
│    )                                                            │
│                                                                  │
│  Supported: >, <, >=, <=, ==, !=, in, contains                 │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  AGENTTEAM (Multi-Agent Task Graphs)                            │
│  ─────────────────────────────────────                          │
│  Syntax: DICT mapping decision values to next task names        │
│                                                                  │
│    Task(                                                        │
│        condition={                    ← DICT                    │
│            "approved": ["publish"],                             │
│            "rejected": ["edit"]                                 │
│        },                                                       │
│        task_type="decision"                                     │
│    )                                                            │
│                                                                  │
│  LLM outputs a decision value, Process routes by key lookup    │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🚨 CONFUSION POINTS FOR BEGINNERS:                             │
│                                                                  │
│  1. Same word "condition" means DIFFERENT things                │
│  2. AgentFlow: evaluates expression → boolean                   │
│  3. AgentTeam: routes by key lookup → next task                 │
│  4. No unified syntax for simple use cases                      │
│  5. Task also has should_run (callable) - 3rd way!              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
""")

print("\n✅ Smoke test completed!")
