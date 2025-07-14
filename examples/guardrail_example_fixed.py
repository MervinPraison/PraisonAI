#!/usr/bin/env python3
"""
Fixed example demonstrating proper guardrail usage with PraisonAI Agents.
This addresses the issues reported in issue #875.
"""

from praisonaiagents import Agent, Task, GuardrailResult, PraisonAIAgents
from typing import Tuple, Any
import trafilatura

# Example 1: Using GuardrailResult return type (now supported!)
def validate_length_guardrailresult(output) -> GuardrailResult:
    """Ensure output is between 100-500 characters using GuardrailResult"""
    # Extract the raw text from the TaskOutput object
    text = output.raw if hasattr(output, 'raw') else str(output)
    length = len(text)
    
    if 100 <= length <= 500:
        return GuardrailResult(
            success=True,
            result=output,  # Pass through the original output
            error=""
        )
    else:
        return GuardrailResult(
            success=False,
            result=None,
            error=f"Output must be 100-500 chars, got {length}"
        )

# Example 2: Using Tuple[bool, Any] return type (original method)
def validate_length_tuple(output) -> Tuple[bool, Any]:
    """Ensure output is between 100-500 characters using tuple"""
    text = output.raw if hasattr(output, 'raw') else str(output)
    length = len(text)
    
    if 100 <= length <= 500:
        return True, output
    else:
        return False, f"Output must be 100-500 chars, got {length}"

# Tool function
def get_url_context(url):
    """Fetch and extract content from a URL"""
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return "Sorry, I couldn't fetch the content from that URL."

    extracted = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_links=True,
        output_format='json',
        with_metadata=True,
        url=url
    )

    if not extracted:
        return "Sorry, I couldn't extract readable content from that page."

    return extracted  # returns JSON string

# Create agent with FIXED tools parameter (must be a list!)
agent = Agent(
    name="Content Summarizer",
    role="Content Analysis Expert",
    goal="Summarize web content concisely",
    instructions="You are a helpful assistant that summarizes web content",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    self_reflect=False,
    verbose=True,
    tools=[get_url_context]  # FIX: tools must be a list, not a single function
)

# Create task with GuardrailResult guardrail
task_with_guardrailresult = Task(
    name="summarise article with GuardrailResult",
    description="get the context of this url: https://blog.google/technology/ai/dolphingemma/ and produce a summary below 500 characters",
    agent=agent,
    guardrail=validate_length_guardrailresult,  # Using GuardrailResult
    expected_output="summary of the article below 500 characters",
    max_retries=3  # Will retry up to 3 times if guardrail fails
)

# Alternative: Create task with tuple guardrail
task_with_tuple = Task(
    name="summarise article with tuple",
    description="get the context of this url: https://blog.google/technology/ai/dolphingemma/ and produce a summary below 500 characters",
    agent=agent,
    guardrail=validate_length_tuple,  # Using Tuple[bool, Any]
    expected_output="summary of the article below 500 characters",
    max_retries=3
)

# Example with string-based LLM guardrail
task_with_llm_guardrail = Task(
    name="summarise with LLM guardrail",
    description="get the context of this url: https://blog.google/technology/ai/dolphingemma/ and produce a summary",
    agent=agent,
    guardrail="Ensure the summary is professional, factual, and between 100-500 characters",
    expected_output="professional summary of the article"
)

# Run with GuardrailResult example
print("=== Running with GuardrailResult guardrail ===")
agents_gr = PraisonAIAgents(
    agents=[agent],
    tasks=[task_with_guardrailresult]
)

# Uncomment to run:
# result_gr = agents_gr.start()

# Run with Tuple example
print("\n=== Running with Tuple[bool, Any] guardrail ===")
agents_tuple = PraisonAIAgents(
    agents=[agent],
    tasks=[task_with_tuple]
)

# Uncomment to run:
# result_tuple = agents_tuple.start()

# Run with LLM guardrail example
print("\n=== Running with LLM-based guardrail ===")
agents_llm = PraisonAIAgents(
    agents=[agent],
    tasks=[task_with_llm_guardrail]
)

# Uncomment to run:
# result_llm = agents_llm.start()

print("""
Key fixes applied:
1. GuardrailResult is now accepted as a valid return type annotation
2. tools parameter must be a list: tools=[get_url_context] not tools=get_url_context
3. Both GuardrailResult and Tuple[bool, Any] return types are supported
4. String-based LLM guardrails are also supported

The guardrail will automatically retry (up to max_retries times) if validation fails.
""")