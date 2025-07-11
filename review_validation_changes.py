#!/usr/bin/env python3
"""Multi-agent review of validation feedback implementation"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents

def review_implementation():
    """Use multiple agents to review the validation feedback implementation"""
    
    # Code review agent
    code_reviewer = Agent(
        name="code_reviewer",
        role="Senior Software Engineer",
        goal="Review code changes for quality, correctness, and best practices",
        instructions="""You are an experienced software engineer reviewing code changes.
        Focus on:
        1. Code quality and readability
        2. Potential bugs or edge cases
        3. Performance implications
        4. Error handling
        5. Adherence to Python best practices""",
        llm="gpt-4o-mini",
        verbose=True
    )
    
    # Architecture reviewer
    architecture_reviewer = Agent(
        name="architecture_reviewer",
        role="Software Architect",
        goal="Review architectural decisions and design patterns",
        instructions="""You are a software architect reviewing system design.
        Focus on:
        1. Design patterns and architectural decisions
        2. Backward compatibility
        3. Extensibility and maintainability
        4. Integration with existing codebase
        5. Minimal invasive changes""",
        llm="gpt-4o-mini",
        verbose=True
    )
    
    # Security reviewer
    security_reviewer = Agent(
        name="security_reviewer",
        role="Security Engineer",
        goal="Review code for security implications",
        instructions="""You are a security engineer reviewing code changes.
        Focus on:
        1. Data validation and sanitization
        2. Information disclosure risks
        3. State management security
        4. Potential for infinite loops or DoS
        5. Safe error handling""",
        llm="gpt-4o-mini",
        verbose=True
    )
    
    # Test reviewer
    test_reviewer = Agent(
        name="test_reviewer",
        role="QA Engineer",
        goal="Review test coverage and edge cases",
        instructions="""You are a QA engineer reviewing test implementation.
        Focus on:
        1. Test coverage completeness
        2. Edge case handling
        3. Test maintainability
        4. Integration test scenarios
        5. Backward compatibility testing""",
        llm="gpt-4o-mini",
        verbose=True
    )
    
    # Summary of changes for review
    changes_summary = """
## Validation Feedback Implementation Review

### Changes Made:
1. **Task class (task.py)**:
   - Added `validation_feedback` field to store validation failure information
   - Field is initialized as None and cleared after use

2. **Process class (process.py)**:
   - Modified workflow routing logic to capture validation feedback
   - When decision task returns "invalid/retry/failed", stores:
     - Decision result
     - Validation response message
     - Rejected output from previous task
     - Validator task name
   - Updated `_build_task_context` to include validation feedback in retry context
   - Feedback is cleared after being added to context

3. **Test Implementation**:
   - Unit tests verify feedback storage and context building
   - Integration examples demonstrate real-world usage
   - Tests confirm backward compatibility

### Key Design Decisions:
- Minimal changes to existing codebase
- Backward compatible - no breaking changes
- Automatic cleanup of feedback after use
- Works for both sync and async workflows
"""
    
    # Create review tasks
    code_review_task = Task(
        name="code_review",
        description=f"""Review the following code changes for the validation feedback implementation:
        
{changes_summary}

Key files modified:
- task.py: Added validation_feedback field
- process.py: Added logic to capture and pass validation feedback
- New test files created

Evaluate code quality, potential bugs, and implementation correctness.""",
        expected_output="Detailed code review with findings and recommendations",
        agent=code_reviewer,
        is_start=True
    )
    
    architecture_review_task = Task(
        name="architecture_review",
        description=f"""Review the architectural approach for the validation feedback implementation:
        
{changes_summary}

Evaluate the design decisions, backward compatibility, and integration approach.""",
        expected_output="Architectural review with assessment of design choices",
        agent=architecture_reviewer,
        context=[code_review_task]
    )
    
    security_review_task = Task(
        name="security_review", 
        description=f"""Review the security implications of the validation feedback implementation:
        
{changes_summary}

Look for potential security issues, data leakage, or DoS vulnerabilities.""",
        expected_output="Security assessment with any identified risks",
        agent=security_reviewer,
        context=[code_review_task]
    )
    
    test_review_task = Task(
        name="test_review",
        description=f"""Review the test implementation and coverage:
        
{changes_summary}

Test files created:
- test_validation_feedback.py: Unit tests
- example_validation_feedback.py: Integration examples

Evaluate test coverage and edge case handling.""",
        expected_output="Test review with coverage assessment",
        agent=test_reviewer,
        context=[code_review_task]
    )
    
    final_summary_task = Task(
        name="final_summary",
        description="""Based on all reviews, provide a final summary of the validation feedback implementation.
        
        Include:
        1. Overall assessment
        2. Key strengths of the implementation
        3. Any concerns or recommendations
        4. Confirmation of backward compatibility
        5. Final recommendation (approve/needs changes)""",
        expected_output="Final consolidated review summary with recommendation",
        agent=architecture_reviewer,
        context=[code_review_task, architecture_review_task, security_review_task, test_review_task]
    )
    
    # Run the review
    review_agents = PraisonAIAgents(
        agents=[code_reviewer, architecture_reviewer, security_reviewer, test_reviewer],
        tasks=[code_review_task, architecture_review_task, security_review_task, test_review_task, final_summary_task],
        verbose=1,
        process="sequential"
    )
    
    print("=" * 70)
    print("STARTING MULTI-AGENT CODE REVIEW")
    print("=" * 70)
    
    result = review_agents.start()
    
    print("\n" + "=" * 70)
    print("REVIEW COMPLETE")
    print("=" * 70)
    
    return result

if __name__ == "__main__":
    review_implementation()