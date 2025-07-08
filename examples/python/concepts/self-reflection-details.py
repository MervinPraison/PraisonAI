"""
Self-Reflection Details Example

This example demonstrates the self-reflection capabilities in PraisonAI agents:
- How self-reflection works
- Configuring reflection parameters
- Different reflection strategies
- Impact on output quality
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from typing import Dict, Any
import time

# Example 1: Basic Self-Reflection
basic_reflection_agent = Agent(
    name="BasicReflector",
    role="Content creator with self-improvement",
    goal="Create high-quality content through iterative reflection",
    backstory="You are a perfectionist writer who reviews and improves your work multiple times.",
    instructions="""When creating content:
1. Write your initial draft
2. Review it critically
3. Identify areas for improvement
4. Revise and enhance
5. Repeat until satisfied""",
    self_reflect=True,  # Enable self-reflection
    min_reflect=1,      # Minimum 1 reflection iteration
    max_reflect=3       # Maximum 3 reflection iterations
)

# Example 2: Advanced Reflection with Different Strategies
quality_focused_agent = Agent(
    name="QualityFocused",
    role="Quality-obsessed analyst",
    goal="Produce extremely high-quality analysis through deep reflection",
    backstory="You never settle for mediocre work and always strive for excellence.",
    instructions="""Your reflection process should focus on:
- Accuracy and correctness
- Completeness of analysis
- Clarity of presentation
- Logical flow
- Supporting evidence""",
    self_reflect=True,
    min_reflect=3,  # Higher minimum for quality
    max_reflect=5   # Allow more iterations
)

efficiency_balanced_agent = Agent(
    name="EfficiencyBalanced",
    role="Balanced performer",
    goal="Achieve good quality with reasonable reflection time",
    backstory="You balance quality with efficiency, knowing when good enough is sufficient.",
    instructions="Create good content with 1-2 rounds of improvement.",
    self_reflect=True,
    min_reflect=1,
    max_reflect=2  # Limit iterations for efficiency
)

# Example 3: No Reflection for Comparison
no_reflection_agent = Agent(
    name="NoReflection",
    role="Quick responder",
    goal="Provide immediate responses without reflection",
    backstory="You provide quick, first-draft responses.",
    instructions="Respond immediately with your first thought.",
    self_reflect=False  # Disable reflection
)

# Demonstration function to show reflection in action
def demonstrate_reflection_levels():
    """Show how different reflection settings affect output quality."""
    
    test_prompt = """Write a compelling product description for an innovative smart water bottle that:
- Tracks hydration levels
- Reminds users to drink water
- Syncs with fitness apps
- Has a 24-hour battery life"""
    
    print("=== Testing Different Reflection Levels ===\n")
    
    # Test without reflection
    print("1. WITHOUT REFLECTION:")
    start_time = time.time()
    result_no_reflect = no_reflection_agent.start(test_prompt)
    time_no_reflect = time.time() - start_time
    print(f"Time: {time_no_reflect:.2f}s")
    print(f"Result: {result_no_reflect}\n")
    
    # Test with basic reflection
    print("2. BASIC REFLECTION (1-3 iterations):")
    start_time = time.time()
    result_basic = basic_reflection_agent.start(test_prompt)
    time_basic = time.time() - start_time
    print(f"Time: {time_basic:.2f}s")
    print(f"Result: {result_basic}\n")
    
    # Test with quality-focused reflection
    print("3. QUALITY-FOCUSED REFLECTION (3-5 iterations):")
    start_time = time.time()
    result_quality = quality_focused_agent.start(test_prompt)
    time_quality = time.time() - start_time
    print(f"Time: {time_quality:.2f}s")
    print(f"Result: {result_quality}\n")

# Example 4: Reflection in Multi-Agent Workflows
def reflection_workflow_example():
    """Demonstrate how reflection works in multi-agent scenarios."""
    
    # Initial creator with reflection
    creator_agent = Agent(
        name="Creator",
        role="Initial content creator",
        goal="Create first draft with self-improvement",
        backstory="You create initial drafts and refine them through reflection.",
        self_reflect=True,
        min_reflect=2,
        max_reflect=3
    )
    
    # Reviewer without reflection (provides feedback)
    reviewer_agent = Agent(
        name="Reviewer",
        role="Content reviewer",
        goal="Provide constructive feedback",
        backstory="You review content and provide specific improvement suggestions.",
        self_reflect=False  # No reflection needed for reviewing
    )
    
    # Final polisher with reflection
    polisher_agent = Agent(
        name="Polisher",
        role="Final content polisher",
        goal="Perfect the content based on feedback",
        backstory="You take feedback and create the final, polished version.",
        self_reflect=True,
        min_reflect=1,
        max_reflect=2
    )
    
    # Workflow tasks
    create_task = Task(
        name="create_content",
        description="Create a blog post about 'The Future of AI in Healthcare' (200 words)",
        expected_output="Initial blog post draft",
        agent=creator_agent
    )
    
    review_task = Task(
        name="review_content",
        description="Review the blog post and provide specific feedback for improvement",
        expected_output="Detailed feedback with specific suggestions",
        agent=reviewer_agent,
        context=[create_task]
    )
    
    polish_task = Task(
        name="polish_content",
        description="Create the final version incorporating all feedback",
        expected_output="Polished final blog post",
        agent=polisher_agent,
        context=[create_task, review_task]
    )
    
    workflow = PraisonAIAgents(
        agents=[creator_agent, reviewer_agent, polisher_agent],
        tasks=[create_task, review_task, polish_task],
        process="sequential",
        verbose=True
    )
    
    return workflow.start()

# Example 5: Custom Reflection Control
class ReflectionController:
    """Custom controller to demonstrate programmatic reflection control."""
    
    def __init__(self):
        self.iteration_count = 0
        self.quality_threshold = 0.8
    
    def should_continue_reflecting(self, current_output: str) -> bool:
        """Custom logic to determine if more reflection is needed."""
        self.iteration_count += 1
        
        # Simple quality check (in practice, this could be more sophisticated)
        quality_indicators = [
            len(current_output) > 100,
            '.' in current_output,
            any(word in current_output.lower() for word in ['innovative', 'comprehensive', 'detailed'])
        ]
        
        quality_score = sum(quality_indicators) / len(quality_indicators)
        
        return quality_score < self.quality_threshold and self.iteration_count < 5

# Agent with custom reflection behavior
custom_reflection_agent = Agent(
    name="CustomReflector",
    role="Adaptive content creator",
    goal="Create content with dynamic reflection based on quality",
    backstory="You adapt your reflection process based on content quality.",
    instructions="""Create content and reflect on it.
Continue improving until quality standards are met or maximum iterations reached.""",
    self_reflect=True,
    min_reflect=1,
    max_reflect=5
)

# Example 6: Reflection Impact Analysis
def analyze_reflection_impact():
    """Analyze and visualize the impact of reflection on output."""
    
    test_cases = [
        "Explain quantum computing in one sentence",
        "Write a haiku about artificial intelligence",
        "Create a tagline for a sustainable energy company"
    ]
    
    results = []
    
    for test in test_cases:
        print(f"\nTest Case: {test}")
        print("-" * 50)
        
        # Without reflection
        result_no = no_reflection_agent.start(test)
        
        # With reflection
        result_yes = quality_focused_agent.start(test)
        
        results.append({
            'test': test,
            'without_reflection': result_no,
            'with_reflection': result_yes,
            'improvement': len(result_yes) > len(result_no)  # Simple metric
        })
        
        print(f"Without Reflection: {result_no}")
        print(f"With Reflection: {result_yes}")
    
    return results

if __name__ == "__main__":
    # Demonstrate different reflection levels
    demonstrate_reflection_levels()
    
    # Show reflection in workflows
    print("\n=== Reflection in Multi-Agent Workflow ===")
    workflow_result = reflection_workflow_example()
    print(f"Workflow Result: {workflow_result}")
    
    # Analyze reflection impact
    print("\n=== Reflection Impact Analysis ===")
    impact_results = analyze_reflection_impact()
    
    # Summary
    print("\n=== Summary of Reflection Benefits ===")
    print("1. Improved Quality: Reflection iterations allow agents to refine their outputs")
    print("2. Error Correction: Agents can catch and fix mistakes through self-review")
    print("3. Completeness: Multiple passes ensure all requirements are addressed")
    print("4. Coherence: Reflection improves logical flow and consistency")
    print("5. Customization: Reflection parameters can be tuned for different use cases")