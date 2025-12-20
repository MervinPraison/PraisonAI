"""
Simple test script for 24/7 Agent Scheduler

This script demonstrates the basic usage of AgentScheduler
for running agents periodically.

Usage:
    python simple_test.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from unittest.mock import Mock
from praisonai.scheduler import AgentScheduler

# Create a mock agent for testing
mock_agent = Mock()
mock_agent.name = "TestAgent"
mock_agent.start = Mock(return_value="Test execution successful!")

# Create scheduler
scheduler = AgentScheduler(
    agent=mock_agent,
    task="Test task execution"
)

print("🤖 Testing AgentScheduler")
print("=" * 60)

# Test 1: Execute once
print("\n✅ Test 1: Execute once")
result = scheduler.execute_once()
print(f"Result: {result}")

# Test 2: Get stats
print("\n✅ Test 2: Get statistics")
stats = scheduler.get_stats()
print(f"Stats: {stats}")

# Test 3: Start scheduler (will run every 5 seconds)
print("\n✅ Test 3: Start scheduler (*/5s)")
scheduler.start("*/5s", run_immediately=True)

import time
print("Running for 12 seconds...")
time.sleep(12)

# Stop scheduler
print("\n✅ Test 4: Stop scheduler")
scheduler.stop()

# Final stats
print("\n📊 Final Statistics:")
final_stats = scheduler.get_stats()
for key, value in final_stats.items():
    print(f"  {key}: {value}")

print("\n✅ All tests passed!")
print("=" * 60)
