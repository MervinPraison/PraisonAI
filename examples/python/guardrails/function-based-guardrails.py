#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Simple validation function for email content
def validate_email_content(task_output):
    """Simple validation function for email content"""
    content = task_output.raw.lower()
    
    # Check for professional tone
    if any(word in content for word in ['hey', 'yo', 'dude', 'awesome']):
        return False, "Email contains unprofessional language"
    
    # Check for minimum length
    if len(content.split()) < 10:
        return False, "Email is too short - needs at least 10 words"
    
    # Check for greeting and closing
    if 'dear' not in content and 'hello' not in content:
        return False, "Email should include a proper greeting"
    
    return True, task_output

# Simple validation function for code quality
def validate_code_quality(task_output):
    """Simple validation function for code quality"""
    content = task_output.raw
    
    # Check for basic code structure
    if 'def ' not in content and 'class ' not in content:
        return False, "Code should contain functions or classes"
    
    # Check for comments
    if '#' not in content:
        return False, "Code should include comments for clarity"
    
    # Check minimum length
    if len(content.split('\n')) < 5:
        return False, "Code is too short - needs more implementation"
    
    return True, task_output

# Simple validation for business reports
def validate_business_report(task_output):
    """Simple validation function for business reports"""
    content = task_output.raw.lower()
    
    # Check for key business terms
    business_terms = ['analysis', 'recommendation', 'strategy', 'objective', 'conclusion']
    if not any(term in content for term in business_terms):
        return False, "Report should include key business terms"
    
    # Check for structure
    if 'executive summary' not in content and 'summary' not in content:
        return False, "Report should include an executive summary"
    
    # Check minimum length
    if len(content.split()) < 50:
        return False, "Report is too short - needs more detailed analysis"
    
    return True, task_output

# Create agents with function-based guardrails
email_agent = Agent(
    name="Email Writer",
    role="Professional Email Writer",
    goal="Write professional business emails",
    backstory="You are a professional email writer who creates formal business correspondence.",
    llm="gpt-4o-mini"
)

code_agent = Agent(
    name="Code Writer",
    role="Software Developer",
    goal="Write clean, well-documented code",
    backstory="You are a skilled programmer who writes clean, maintainable code with proper documentation.",
    llm="gpt-4o-mini"
)

business_agent = Agent(
    name="Business Analyst",
    role="Business Report Writer",
    goal="Create comprehensive business reports",
    backstory="You are a business analyst who creates detailed reports with clear recommendations.",
    llm="gpt-4o-mini"
)

# Create tasks with function-based guardrails
email_task = Task(
    name="write_professional_email",
    description="Write a professional email to a client about project completion",
    expected_output="A well-structured professional email",
    agent=email_agent,
    guardrail=validate_email_content,
    max_retries=3
)

code_task = Task(
    name="write_python_function",
    description="Write a Python function that calculates compound interest with proper documentation",
    expected_output="Clean Python code with comments and documentation",
    agent=code_agent,
    guardrail=validate_code_quality,
    max_retries=3
)

report_task = Task(
    name="write_business_report",
    description="Write a business report analyzing market trends for Q1 2024",
    expected_output="Professional business report with analysis and recommendations",
    agent=business_agent,
    guardrail=validate_business_report,
    max_retries=3
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[email_agent, code_agent, business_agent],
    tasks=[email_task, code_task, report_task],
    process="sequential",
    verbose=True
)

# Run the workflow
if __name__ == "__main__":
    print("🛡️ Function-based Guardrails Example")
    print("This example shows how to use custom validation functions as guardrails")
    print("=" * 80)
    
    print("\n🔍 Validation Functions:")
    print("• Email validation: Checks for professional tone, length, and structure")
    print("• Code validation: Ensures functions/classes, comments, and adequate length")
    print("• Business report validation: Checks for key terms and executive summary")
    
    print("\n⚙️ How it works:")
    print("1. Each task has a guardrail function that validates the output")
    print("2. If validation fails, the agent retries up to max_retries times")
    print("3. Validation functions return (True, output) or (False, error_message)")
    
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ Function-based Guardrails Complete")
    print("💡 All outputs were validated using custom validation functions")
    print("🔧 Guardrails ensure quality and consistency in agent outputs")