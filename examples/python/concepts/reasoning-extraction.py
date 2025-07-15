"""
Reasoning Extraction Example

This example demonstrates how to extract and utilize reasoning patterns in PraisonAI:
- Chain of Thought (CoT) reasoning
- Step-by-step problem decomposition
- Reasoning visualization
- Decision rationale extraction
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from typing import Dict, List, Tuple
from pydantic import BaseModel
import json

# Pydantic models for structured reasoning
class ReasoningStep(BaseModel):
    step_number: int
    description: str
    reasoning: str
    conclusion: str

class ChainOfThought(BaseModel):
    problem: str
    steps: List[ReasoningStep]
    final_answer: str
    confidence: float

# Tool for saving reasoning chains
def save_reasoning_chain(chain: ChainOfThought) -> str:
    """Save a chain of thought reasoning to analyze patterns."""
    filename = f"reasoning_{chain.problem[:20].replace(' ', '_')}.json"
    with open(filename, 'w') as f:
        json.dump(chain.model_dump(), f, indent=2)
    return f"Reasoning chain saved to {filename}"

# Example 1: Chain of Thought Agent
cot_agent = Agent(
    name="ChainOfThoughtAgent",
    role="Systematic reasoning specialist",
    goal="Solve problems using explicit chain of thought reasoning",
    backstory="You are a logic expert who breaks down complex problems into clear reasoning steps.",
    instructions="""When solving problems:
1. State the problem clearly
2. Break it down into logical steps
3. Show your reasoning for each step
4. Draw conclusions from each step
5. Arrive at the final answer
6. Assess your confidence level

Always make your thinking process explicit and transparent.""",
    self_reflect=True,
    min_reflect=2,
    max_reflect=3
)

# Example 2: Reasoning Extractor Agent
reasoning_extractor = Agent(
    name="ReasoningExtractor",
    role="Reasoning pattern analyzer",
    goal="Extract and analyze reasoning patterns from problem-solving processes",
    backstory="You specialize in understanding how problems are solved and extracting the underlying reasoning.",
    instructions="""Analyze the problem-solving process and extract:
1. Key reasoning steps
2. Decision points and rationale
3. Assumptions made
4. Logic patterns used
5. Potential alternative approaches""",
    tools=[save_reasoning_chain]
)

# Example 3: Multi-Step Reasoning Workflow
def demonstrate_reasoning_extraction():
    """Show how to extract reasoning from a complex problem-solving process."""
    
    # Step 1: Present a complex problem
    problem_task = Task(
        name="solve_problem",
        description="""Solve this problem step by step:
        
        A small tech startup has $50,000 budget for the next quarter.
        They need to decide between:
        1. Hiring 2 junior developers ($25,000 each)
        2. Hiring 1 senior developer ($40,000) + marketing budget ($10,000)
        3. Investing in AI tools ($30,000) + 1 junior developer ($20,000)
        
        Consider: current team size is 3, main challenge is product development speed,
        but they also lack market visibility.""",
        expected_output="Detailed solution with reasoning for each consideration",
        agent=cot_agent,
        output_pydantic=ChainOfThought
    )
    
    # Step 2: Extract reasoning patterns
    extract_task = Task(
        name="extract_reasoning",
        description="Extract and analyze the reasoning patterns used in solving the problem",
        expected_output="Structured analysis of reasoning patterns",
        agent=reasoning_extractor,
        context=[problem_task]
    )
    
    workflow = PraisonAIAgents(
        agents=[cot_agent, reasoning_extractor],
        tasks=[problem_task, extract_task],
        process="sequential",
        verbose=True
    )
    
    return workflow.start()

# Example 4: Socratic Reasoning Agent
socratic_agent = Agent(
    name="SocraticReasoner",
    role="Socratic method practitioner",
    goal="Guide reasoning through questions and answers",
    backstory="You use the Socratic method to help uncover reasoning through thoughtful questions.",
    instructions="""Use the Socratic method:
1. Ask clarifying questions
2. Challenge assumptions
3. Explore implications
4. Consider alternatives
5. Synthesize insights

Make the reasoning process interactive and exploratory."""
)

# Example 5: Reasoning Validator
reasoning_validator = Agent(
    name="ReasoningValidator",
    role="Logic and reasoning validator",
    goal="Validate reasoning chains for logical consistency",
    backstory="You are an expert at identifying logical fallacies and validating reasoning.",
    instructions="""Check reasoning for:
1. Logical consistency
2. Valid premises
3. Sound conclusions
4. Hidden assumptions
5. Potential biases"""
)

# Example 6: Advanced Reasoning Patterns
def advanced_reasoning_patterns():
    """Demonstrate different types of reasoning extraction."""
    
    # Deductive reasoning
    deductive_task = Task(
        name="deductive_reasoning",
        description="""Use deductive reasoning to solve:
        All successful startups have strong leadership.
        Company X is a successful startup.
        What can we conclude about Company X?""",
        expected_output="Deductive reasoning chain with clear premises and conclusion",
        agent=cot_agent
    )
    
    # Inductive reasoning
    inductive_task = Task(
        name="inductive_reasoning",
        description="""Use inductive reasoning based on these observations:
        - 5 observed AI companies grew 200% after implementing MLOps
        - 3 observed AI companies without MLOps grew only 50%
        What general conclusion might we draw?""",
        expected_output="Inductive reasoning with probability assessment",
        agent=cot_agent
    )
    
    # Abductive reasoning
    abductive_task = Task(
        name="abductive_reasoning",
        description="""Use abductive reasoning:
        The server is down and users can't access the app.
        What are the most likely explanations?""",
        expected_output="Abductive reasoning with ranked hypotheses",
        agent=cot_agent
    )
    
    # Validate all reasoning
    validation_task = Task(
        name="validate_reasoning",
        description="Validate all three reasoning approaches for logical soundness",
        expected_output="Validation report for each reasoning type",
        agent=reasoning_validator,
        context=[deductive_task, inductive_task, abductive_task]
    )
    
    workflow = PraisonAIAgents(
        agents=[cot_agent, reasoning_validator],
        tasks=[deductive_task, inductive_task, abductive_task, validation_task],
        process="sequential",
        verbose=True
    )
    
    return workflow.start()

# Example 7: Reasoning Patterns Library
class ReasoningPattern:
    """Base class for different reasoning patterns."""
    
    @staticmethod
    def analogical_reasoning(source: str, target: str) -> str:
        """Extract reasoning by analogy."""
        return f"If {source} works like X, then {target} might work like Y"
    
    @staticmethod
    def causal_reasoning(cause: str, effect: str) -> str:
        """Extract cause-effect reasoning."""
        return f"Because {cause}, therefore {effect}"
    
    @staticmethod
    def counterfactual_reasoning(fact: str, alternative: str) -> str:
        """Extract counterfactual reasoning."""
        return f"If {alternative} instead of {fact}, then what would change?"

# Specialized reasoning agent using patterns
pattern_reasoning_agent = Agent(
    name="PatternReasoner",
    role="Reasoning pattern specialist",
    goal="Apply specific reasoning patterns to solve problems",
    backstory="You are an expert in various reasoning patterns and their applications.",
    instructions="""Apply these reasoning patterns as appropriate:
1. Analogical: Find similar situations
2. Causal: Identify cause-effect relationships
3. Counterfactual: Explore what-if scenarios
4. Systems thinking: Consider interconnections
5. Probabilistic: Assess likelihoods""",
    self_reflect=True
)

# Example 8: Interactive Reasoning Extraction
def interactive_reasoning_demo():
    """Interactive demonstration of reasoning extraction."""
    
    print("=== Interactive Reasoning Extraction Demo ===\n")
    
    # Problem categories
    problems = {
        "logical": "If all cats have tails, and Fluffy is a cat, what can we conclude?",
        "mathematical": "A store offers 20% off, then an additional 15% off. What's the total discount?",
        "strategic": "Should a startup focus on growth or profitability in its second year?",
        "ethical": "Is it ethical to use AI for hiring decisions?"
    }
    
    for category, problem in problems.items():
        print(f"\n{category.upper()} REASONING:")
        print(f"Problem: {problem}")
        
        # Extract reasoning
        result = cot_agent.start(f"Solve this {category} problem with clear reasoning: {problem}")
        print(f"Reasoning: {result}")

if __name__ == "__main__":
    # Basic chain of thought demonstration
    print("=== Chain of Thought Reasoning ===")
    cot_result = cot_agent.start("""
    A company's revenue increased by 40% but profit decreased by 10%.
    What might this indicate about the company's situation?
    Show your reasoning step by step.
    """)
    print(cot_result)
    
    # Reasoning extraction workflow
    print("\n=== Reasoning Extraction Workflow ===")
    extraction_result = demonstrate_reasoning_extraction()
    print(f"Result: {extraction_result}")
    
    # Advanced reasoning patterns
    print("\n=== Advanced Reasoning Patterns ===")
    advanced_result = advanced_reasoning_patterns()
    print(f"Result: {advanced_result}")
    
    # Interactive demo
    interactive_reasoning_demo()
    
    # Summary
    print("\n=== Reasoning Extraction Benefits ===")
    print("1. Transparency: Makes decision-making process clear")
    print("2. Debugging: Helps identify where reasoning might be flawed")
    print("3. Learning: Extracts patterns for future use")
    print("4. Trust: Builds confidence through explainable AI")
    print("5. Improvement: Enables iterative refinement of reasoning")