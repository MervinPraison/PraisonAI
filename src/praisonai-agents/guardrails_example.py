#!/usr/bin/env python3
"""
Example demonstrating guardrails functionality in PraisonAI Agents.

This example shows both function-based and LLM-based guardrails
for validating task outputs.
"""

import sys
import os
from typing import Tuple, Any

from praisonaiagents import Agent, Task, TaskOutput


def email_validator(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Function-based guardrail to validate email content.
    
    Args:
        task_output: The task output to validate
        
    Returns:
        Tuple of (success, result_or_error)
    """
    content = task_output.raw.lower()
    
    # Check for required email components
    if "subject:" not in content:
        return False, "Email must include a subject line"
    
    if "dear" not in content and "hello" not in content:
        return False, "Email must include a proper greeting"
    
    if len(content) < 50:
        return False, "Email content is too short"
        
    if "error" in content or "problem" in content:
        return False, "Email should not mention errors or problems"
        
    return True, task_output


def main():
    """Run the guardrails example."""
    print("PraisonAI Agents - Guardrails Example")
    print("=====================================\n")
    
    # Create an agent
    agent = Agent(
        name="Email Assistant",
        role="Professional Email Writer",
        goal="Write clear, professional emails",
        backstory="I am an AI assistant specialized in writing professional emails"
    )
    
    print("1. Testing Function-based Guardrail")
    print("------------------------------------")
    
    # Create task with function-based guardrail
    task_with_function_guardrail = Task(
        description="Write a professional email to a client about project completion",
        expected_output="A well-formatted professional email",
        agent=agent,
        guardrail=email_validator,  # Function-based guardrail
        max_retries=2
    )
    
    print(f"Task created with function guardrail: {email_validator.__name__}")
    print(f"Max retries: {task_with_function_guardrail.max_retries}")
    
    # Simulate a task output that should pass
    good_output = TaskOutput(
        description="Email task",
        raw="""Subject: Project Completion Update

Dear Client,

I am pleased to inform you that your project has been completed successfully. 
All deliverables have been reviewed and are ready for your review. 
Please let me know if you have any questions.

Best regards,
Project Team""",
        agent="Email Assistant"
    )
    
    result = task_with_function_guardrail._process_guardrail(good_output)
    print(f"Good email result: {'PASSED' if result.success else 'FAILED'}")
    if not result.success:
        print(f"Error: {result.error}")
    
    # Simulate a task output that should fail
    bad_output = TaskOutput(
        description="Email task",
        raw="Hi there, there was an error with your project.",
        agent="Email Assistant"
    )
    
    result = task_with_function_guardrail._process_guardrail(bad_output)
    print(f"Bad email result: {'PASSED' if result.success else 'FAILED'}")
    if not result.success:
        print(f"Error: {result.error}")
    
    print("\n2. Testing String-based LLM Guardrail")
    print("-------------------------------------")
    
    # Create task with string-based guardrail
    task_with_llm_guardrail = Task(
        description="Write a marketing email for a new product launch",
        expected_output="Engaging marketing content",
        agent=agent,
        guardrail="Ensure the content is professional, engaging, includes a clear call-to-action, and is free of errors",
        max_retries=3
    )
    
    print("Task created with LLM-based guardrail")
    print("Guardrail description: 'Ensure the content is professional, engaging, includes a clear call-to-action, and is free of errors'")
    print(f"Max retries: {task_with_llm_guardrail.max_retries}")
    
    print("\n3. Backward Compatibility")
    print("-------------------------")
    
    # Create task without guardrail (backward compatible)
    task_without_guardrail = Task(
        description="Write a simple thank you note",
        expected_output="A brief thank you message",
        agent=agent
    )
    
    print("Task created without guardrail (backward compatible)")
    print(f"Guardrail function: {task_without_guardrail._guardrail_fn}")
    
    # Test that it doesn't break existing functionality
    simple_output = TaskOutput(
        description="Thank you task",
        raw="Thank you for your business!",
        agent="Email Assistant"
    )
    
    result = task_without_guardrail._process_guardrail(simple_output)
    print(f"No guardrail result: {'PASSED' if result.success else 'FAILED'}")
    
    print("\n✅ Guardrails example completed successfully!")
    print("\nKey Features Demonstrated:")
    print("- Function-based guardrails with custom validation logic")
    print("- String-based LLM guardrails using natural language")
    print("- Configurable retry mechanism")
    print("- Backward compatibility with existing tasks")
    print("- Integration with TaskOutput validation")


if __name__ == "__main__":
    main()