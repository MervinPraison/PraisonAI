# Fix for display_generating Issue

## Problem
When `stream=false` but `verbose=true`, the system was still showing streaming-like visual behavior ("Generating... X.Xs") because the code was using `display_generating` function even when the user explicitly set `stream=false`.

## Root Cause
Two locations in `agent.py` were passing `display_generating` as `display_fn` when `stream=False` and `verbose=True`:

- **Line 1073**: `display_fn=display_generating if (not stream and self.verbose) else None`
- **Line 1172**: `display_fn=display_generating if (not stream and self.verbose) else None`

This conflated two different concepts:
- **Verbose**: Show detailed information  
- **Visual Progress**: Show animated progress indicators

## Solution
Changed both locations to:
```python
display_fn=None,  # Don't use display_generating when stream=False to avoid streaming-like behavior
```

## Expected Behavior After Fix

| Stream | Verbose | Visual Behavior |
|--------|---------|----------------|
| False  | False   | No display |
| False  | True    | **No streaming-like behavior (FIXED)** |
| True   | False   | Native streaming display |  
| True   | True    | Native streaming display |

## Files Modified
- `src/praisonai-agents/praisonaiagents/agent/agent.py` - Lines 1073 and 1172

## Verification
- Test script: `test_display_generating_fix.py` 
- All old problematic patterns removed
- New safe patterns implemented at both locations