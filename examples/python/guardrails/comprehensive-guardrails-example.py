"""
Comprehensive Guardrails Example

This example demonstrates both function-based and LLM-based guardrails for validating
agent outputs and ensuring quality, safety, and compliance.

Features demonstrated:
- Function-based validation guardrails
- LLM-based content validation
- Multiple validation criteria
- Retry mechanisms with feedback
- Quality assurance workflows
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.task import TaskOutput
from typing import Tuple, Any
import re

# Configuration constants
MIN_WORDS = 50
UNPROFESSIONAL_TERMS = ['stupid', 'dumb', 'sucks', 'terrible', 'awful', 'hate']
FACTUAL_INDICATORS = ['according to', 'research shows', 'studies indicate', 'data suggests', 'evidence']

# Define function-based guardrails for different validation types

def email_format_guardrail(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validates that the output contains properly formatted email addresses.
    """
    output_text = str(task_output.raw)
    
    # Email regex pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails_found = re.findall(email_pattern, output_text)
    
    if emails_found:
        return True, task_output
    else:
        return False, "No valid email addresses found in the output. Please include at least one properly formatted email address."

def word_count_guardrail(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validates that the output meets minimum word count requirements.
    """
    output_text = str(task_output.raw)
    word_count = len(output_text.split())
    
    if word_count >= MIN_WORDS:
        return True, task_output
    else:
        return False, f"Output too short. Found {word_count} words but need at least {MIN_WORDS} words. Please provide a more detailed response."

def professional_tone_guardrail(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validates that the output maintains a professional tone.
    """
    output_text = str(task_output.raw).lower()
    
    # Check for unprofessional words/phrases
    for term in UNPROFESSIONAL_TERMS:
        if term in output_text:
            return False, f"Output contains unprofessional language ('{term}'). Please revise to maintain a professional tone."
    
    return True, task_output

def factual_accuracy_guardrail(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validates that the output includes specific factual elements.
    """
    output_text = str(task_output.raw).lower()
    
    # Check for presence of factual indicators
    has_factual_backing = any(indicator in output_text for indicator in FACTUAL_INDICATORS)
    
    if has_factual_backing:
        return True, task_output
    else:
        return False, "Output lacks factual backing. Please include references to research, studies, or data to support your claims."

# Create agents with different guardrail configurations

# Agent with email format validation
email_agent = Agent(
    name="EmailAgent",
    role="Business Communication Specialist",
    goal="Create professional business communications with proper email formatting",
    backstory="You are a professional communication specialist who ensures all business correspondence includes proper contact information.",
    instructions="Always include properly formatted email addresses in your responses."
)

# Agent with word count validation  
content_agent = Agent(
    name="ContentAgent",
    role="Content Writer",
    goal="Create detailed, comprehensive content that meets length requirements",
    backstory="You are a professional content writer who creates detailed, well-researched articles.",
    instructions="Provide comprehensive, detailed responses with sufficient depth and explanation."
)

# Agent with professional tone validation
business_agent = Agent(
    name="BusinessAgent", 
    role="Professional Advisor",
    goal="Provide professional business advice with appropriate tone",
    backstory="You are a seasoned business advisor who maintains professionalism in all communications.",
    instructions="Maintain a professional, respectful tone in all communications."
)

# Agent with factual accuracy validation
research_agent = Agent(
    name="ResearchAgent",
    role="Research Analyst", 
    goal="Provide well-researched, fact-based analysis",
    backstory="You are a research analyst who backs all claims with evidence and citations.",
    instructions="Support all statements with references to research, studies, or credible data sources."
)

# Create tasks with specific guardrails

# Task with email format guardrail
email_task = Task(
    name="email_communication",
    description="Write a business proposal for a new software project, including contact information",
    expected_output="Professional business proposal with contact email addresses",
    agent=email_agent,
    guardrail=email_format_guardrail,
    max_retries=3
)

# Task with word count guardrail
content_task = Task(
    name="detailed_analysis", 
    description="Write an analysis of cloud computing benefits for small businesses",
    expected_output="Comprehensive analysis of cloud computing benefits (minimum 50 words)",
    agent=content_agent,
    guardrail=word_count_guardrail,
    max_retries=3
)

# Task with professional tone guardrail
business_task = Task(
    name="professional_advice",
    description="Provide advice on handling difficult client relationships",
    expected_output="Professional advice maintaining appropriate business tone",
    agent=business_agent,
    guardrail=professional_tone_guardrail,
    max_retries=3
)

# Task with factual accuracy guardrail
research_task = Task(
    name="research_report",
    description="Analyze the impact of artificial intelligence on job markets",
    expected_output="Research-backed analysis with citations and evidence",
    agent=research_agent,
    guardrail=factual_accuracy_guardrail,
    max_retries=3
)

# LLM-based guardrail example
llm_guardrail_agent = Agent(
    name="LLMGuardrailAgent",
    role="Content Quality Validator",
    goal="Validate content quality using LLM-based assessment",
    backstory="You are a quality assurance specialist who uses AI to validate content quality.",
    instructions="Create marketing content that is engaging, accurate, and compliant with advertising standards."
)

# Task with LLM-based guardrail
llm_guardrail_task = Task(
    name="marketing_content",
    description="Create a marketing email for a new fitness app targeting busy professionals",
    expected_output="Engaging marketing email that is accurate and compliant",
    agent=llm_guardrail_agent,
    
    # LLM-based guardrail using natural language validation
    guardrail="Validate that this marketing content is: 1) Factually accurate with no false claims, 2) Compliant with advertising standards (no misleading statements), 3) Engaging and professional in tone, 4) Includes a clear call-to-action. If any criteria are not met, explain what needs to be improved.",
    max_retries=2
)

# Execute tasks with guardrails
agents = PraisonAIAgents(
    agents=[email_agent, content_agent, business_agent, research_agent, llm_guardrail_agent],
    tasks=[email_task, content_task, business_task, research_task, llm_guardrail_task],
    verbose=True
)

print("="*80)
print("EXECUTING TASKS WITH COMPREHENSIVE GUARDRAILS")
print("="*80)

result = agents.start()

print("\n" + "="*80)
print("GUARDRAILS DEMONSTRATION COMPLETED")
print("="*80)
print("This example demonstrated:")
print("- Function-based validation (email format, word count, tone, factual accuracy)")
print("- LLM-based content validation using natural language criteria")
print("- Automatic retry mechanisms with specific feedback")
print("- Quality assurance workflows for different content types")
print("- Professional validation standards for business communications")