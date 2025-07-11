#!/usr/bin/env python3
"""Example demonstrating validation feedback in workflow retry logic"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents

# This example shows how validation feedback is now passed to retry tasks

print("""
==========================================
Validation Feedback Feature Demonstration
==========================================

This example shows how the workflow retry logic now includes validation feedback.

Before: When validation failed, the retry task would start fresh without knowing why it failed.
After: The retry task receives detailed feedback about what went wrong.

Example Scenario:
1. A data collection task produces output
2. A validation task checks if the output meets criteria
3. If validation fails, the data collection task is retried WITH feedback about why it failed

The retry task will see:
- Previous attempt failed validation with reason: invalid
- Validation feedback: [specific reason for failure]
- Rejected output: [the output that failed validation]
- Please try again with a different approach based on this feedback.

This enables context-dependent tasks to improve on retry instead of repeating the same mistakes.
==========================================

Implementation Details:
1. Added 'validation_feedback' field to Task class
2. When routing from decision task to retry task, capture validation details
3. Include feedback in task context when building retry task description
4. Clear feedback after use to prevent persistence

The solution is minimal and backward compatible - existing workflows continue to work unchanged.
""")

# Example workflow structure (without actual execution)
print("\nExample Workflow Structure:")
print("""
collect_task = Task(
    name="collect_data",
    description="Collect data from source",
    is_start=True,
    next_tasks=["validate_data"]
)

validate_task = Task(
    name="validate_data", 
    task_type="decision",
    description="Validate if data meets criteria",
    condition={
        "valid": [],  # End workflow
        "invalid": ["collect_data"]  # Retry with feedback
    }
)

# When validation returns "invalid":
# 1. The workflow captures the validation output
# 2. Stores it in collect_task.validation_feedback
# 3. On retry, collect_data task sees the feedback in its context
# 4. Agent can adjust approach based on specific failure reason
""")