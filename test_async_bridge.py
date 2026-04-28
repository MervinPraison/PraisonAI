#!/usr/bin/env python3
"""Smoke test for async bridge daemon thread fix."""

import asyncio
import time
import threading
from src.praisonai.praisonai._async_bridge import run_sync, _BG

async def test_coro(value: int) -> int:
    """Simple test coroutine."""
    await asyncio.sleep(0.001)  # Brief sleep to exercise the async machinery
    return value * 2

def test_daemon_thread_fix():
    """Verify that daemon threads allow clean exit."""
    print("[smoke] === STEP 1: run_sync from sync context ===")
    result = run_sync(test_coro(21))
    assert result == 42, f"Expected 42, got {result}"
    print(f"        result={result}")

def test_runtime_error_guard():
    """Verify that run_sync raises RuntimeError when called from async context."""
    print("[smoke] === STEP 2: run_sync inside running loop ===")
    
    async def nested_call():
        try:
            run_sync(test_coro(1))
            return False  # Should not reach here
        except RuntimeError:
            return True  # Expected behavior
    
    result = run_sync(nested_call())
    assert result is True, "run_sync should raise RuntimeError from async context"
    print("        OK raised RuntimeError")

def test_thread_properties():
    """Verify the background thread is properly configured as daemon."""
    print("[smoke] === STEP 3: thread daemon property ===")
    # Force thread creation
    run_sync(test_coro(1))
    
    # Check thread properties
    assert _BG._thread is not None, "Background thread should exist"
    assert _BG._thread.daemon is True, "Background thread should be daemon"
    assert _BG._thread.is_alive(), "Background thread should be alive"
    print("        daemon=True ✓")

def main():
    """Run all smoke tests."""
    print("[smoke] === ASYNC BRIDGE SMOKE TEST ===")
    
    try:
        test_daemon_thread_fix()
        test_runtime_error_guard()
        test_thread_properties()
        
        print("[smoke] === ALL SMOKE STEPS PASSED ===")
        return True
    except Exception as e:
        print(f"[smoke] === FAILED: {e} ===")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)