# Issue #878 Duplicate Callback Reproduction Guide

## Overview
This guide documents the reproduction of the duplicate callback issue reported in #878, where `register_display_callback('interaction', callback_function)` gets triggered twice for a single task execution.

## Root Cause Analysis

The duplicate callback issue occurs due to two separate callback execution paths in the codebase:

### Primary Issue Location: `llm.py`
1. **Direct callback execution**: `execute_sync_callback()` is called directly (lines 851-857, 885-891, etc.)
2. **Display function callback**: `display_interaction()` is called when `verbose=True` (line 896, etc.)

### Secondary Issue Location: `main.py`
- `display_interaction()` function (lines 164-190) also executes sync callbacks internally

### When the Bug Occurs
The bug manifests when **both** of these conditions are true:
- A sync callback is registered using `register_display_callback('interaction', callback_fn, is_async=False)`
- `verbose=True` is used in LLM calls

This causes the callback to be executed twice:
1. Once from the direct `execute_sync_callback()` call in `llm.py`
2. Once again when `display_interaction()` executes callbacks in `main.py`

## Reproduction Scripts

### 1. `reproduce_issue_878.py`
Full reproduction script that matches the user's original bug report:
- Creates agent and task exactly as described by the user
- Uses the same callback structure from the user's example
- Logs callback invocations to file and console
- Tests both full agent execution and direct LLM calls

**Expected Result**: Shows duplicate callback execution (2 calls instead of 1)

### 2. `reproduce_issue_878_simple.py`
Isolated test script that focuses on the LLM layer:
- Tests different LLM configurations (streaming, non-streaming, self-reflection)
- **Key Test**: Compares `verbose=False` vs `verbose=True` to isolate the duplicate issue
- Provides detailed call stack analysis to show where callbacks originate
- More precise diagnostic information about the root cause

**Expected Result**: `verbose=True` triggers 2 callbacks, `verbose=False` triggers 1 callback

## Key Findings

### Test Results Pattern
- **Non-verbose mode** (`verbose=False`): 1 callback per LLM response ✅
- **Verbose mode** (`verbose=True`): 2 callbacks per LLM response ❌

### Call Stack Analysis
When running the reproduction scripts, you should see callback invocations coming from:
1. `llm.py` via `execute_sync_callback()` 
2. `main.py` via `display_interaction()` → sync callback execution

## Usage Instructions

### Running the Full Reproduction
```bash
python reproduce_issue_878.py
```
This will:
- Test the exact scenario from the user's bug report
- Create a `callback_log.txt` file with detailed logs
- Show both full agent test and direct LLM isolation test

### Running the Simplified Analysis
```bash
python reproduce_issue_878_simple.py
```
This will:
- Run multiple focused tests on the LLM layer
- Show the key `verbose=True` vs `verbose=False` comparison
- Provide call stack analysis of where duplicates originate
- Give a detailed summary of findings

## Expected Output

If the duplicate callback issue exists, you should see output like:
```
🔔 CALLBACK #1: message='Say the number 1...', response='1...'
🔔 CALLBACK #2: message='Say the number 1...', response='1...'

❌ FAIL: Duplicate callback detected! Callback invoked twice (this is the bug)
```

If the issue is fixed, you should see:
```
🔔 CALLBACK #1: message='Say the number 1...', response='1...'

✅ PASS: Callback invoked exactly once (expected behavior)
```

## Technical Details

### Files Involved
- `src/praisonai-agents/praisonaiagents/main.py`: Callback registration and execution
- `src/praisonai-agents/praisonaiagents/llm/llm.py`: LLM response handling with callbacks
- `src/praisonai-agents/praisonaiagents/agents/agents.py`: Agent orchestration

### Callback Flow
1. User registers callback: `register_display_callback('interaction', callback_fn, is_async=False)`
2. LLM processes request and calls `execute_sync_callback()` directly
3. If `verbose=True`, LLM also calls `display_interaction()`
4. `display_interaction()` executes the same callback again → **Duplicate!**

## Recommendation

The fix should ensure that callbacks are only executed once per LLM response, regardless of the verbose setting. This could be achieved by:
1. Removing direct `execute_sync_callback()` calls from `llm.py` 
2. OR preventing `display_interaction()` from executing callbacks if they've already been executed
3. OR introducing a callback execution tracking mechanism to prevent duplicates