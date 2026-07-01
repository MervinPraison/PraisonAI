"""
Simple test script for 24/7 Agent Scheduler.

This script demonstrates the basic usage of AgentScheduler
for running agents periodically.

Usage:
    python simple_test.py
"""

import os
import sys
import time
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from praisonai.scheduler import AgentScheduler

# ---------------------------------------------------------------------
# Create a mock agent
#
# The scheduler now supports both asynchronous (astart) and synchronous
# (start) execution. This example exposes both methods so either dispatch
# path can be exercised.
# ---------------------------------------------------------------------

mock_agent = Mock(spec=["name", "start", "astart"])
mock_agent.name = "TestAgent"

mock_agent.astart = AsyncMock(
    return_value="Test execution successful!"
)
mock_agent.start = Mock(
    return_value="Test execution successful!"
)

# Create scheduler
scheduler = AgentScheduler(
    agent=mock_agent,
    task="Test task execution",
)

print("🤖 Testing AgentScheduler")
print("=" * 60)

# Execute once
print("\n✅ Test 1: Execute once")
result = scheduler.execute_once()
print(f"Result: {result}")

# Statistics
print("\n✅ Test 2: Get statistics")
stats = scheduler.get_stats()
print(f"Stats: {stats}")

# Periodic execution
print("\n✅ Test 3: Start scheduler (*/5s)")
scheduler.start("*/5s", run_immediately=True)

print("Running for 12 seconds...")
time.sleep(12)

# Stop scheduler
print("\n✅ Test 4: Stop scheduler")
scheduler.stop()

# Final statistics
print("\n📊 Final Statistics:")
for key, value in scheduler.get_stats().items():
    print(f"  {key}: {value}")

print("\n✅ All tests passed!")
print("=" * 60)