"""
AutoAgents Workflow Patterns Example

This example demonstrates the new workflow auto-generation features:
- Dynamic agent count based on task complexity
- Multiple workflow patterns (sequential, parallel, routing, orchestrator-workers, evaluator-optimizer)
- Pattern recommendation based on task keywords

Documentation: https://docs.praison.ai/features/autoagents
CLI Reference: https://docs.praison.ai/nocode/auto
"""

from praisonai.auto import AutoGenerator, WorkflowAutoGenerator
import os
import tempfile

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

print("=" * 60)
print("AutoAgents Workflow Patterns Demo")
print("=" * 60)

# =============================================================================
# Example 1: Dynamic Agent Count (Simple vs Complex Tasks)
# =============================================================================
print("\n📊 Example 1: Dynamic Agent Count")
print("-" * 40)

# Simple task - should create 1-2 agents
with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    simple_file = f.name

simple_generator = AutoGenerator(
    topic="Write a haiku about spring",
    agent_file=simple_file,
    framework="praisonai"
)

print("Simple task: 'Write a haiku about spring'")
result = simple_generator.generate()
print(f"Generated: {result}")

# Complex task - should create 3-4 agents
with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    complex_file = f.name

complex_generator = AutoGenerator(
    topic="Research AI trends, analyze market data, write a comprehensive report with executive summary",
    agent_file=complex_file,
    framework="praisonai"
)

print("\nComplex task: 'Research AI trends, analyze market data...'")
result = complex_generator.generate()
print(f"Generated: {result}")

# =============================================================================
# Example 2: Pattern Recommendation
# =============================================================================
print("\n🎯 Example 2: Pattern Recommendation")
print("-" * 40)

test_tasks = [
    ("Write a blog post", "sequential"),
    ("Research from multiple sources simultaneously", "parallel"),
    ("Classify and route customer requests", "routing"),
    ("Comprehensive analysis and break down the problem", "orchestrator-workers"),
    ("Refine and improve content quality", "evaluator-optimizer"),
]

for task, expected in test_tasks:
    generator = WorkflowAutoGenerator(topic=task)
    recommended = generator.recommend_pattern()
    status = "✅" if recommended == expected else "⚠️"
    print(f"{status} Task: '{task[:40]}...'")
    print(f"   Recommended: {recommended}")

# =============================================================================
# Example 3: Generate Workflow with Specific Pattern
# =============================================================================
print("\n🔄 Example 3: Generate Workflows with Patterns")
print("-" * 40)

patterns = ["sequential", "parallel", "orchestrator-workers", "evaluator-optimizer"]

for pattern in patterns:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        workflow_file = f.name
    
    generator = WorkflowAutoGenerator(
        topic="Create a market analysis report",
        workflow_file=workflow_file
    )
    
    print(f"\n📋 Pattern: {pattern}")
    result = generator.generate(pattern=pattern)
    print(f"   Generated: {result}")
    
    # Read and show structure
    import yaml
    with open(result, 'r') as f:
        data = yaml.safe_load(f)
    print(f"   Agents: {list(data.get('agents', {}).keys())}")
    print(f"   Steps: {len(data.get('steps', []))}")

# =============================================================================
# Example 4: CLI Usage (for reference)
# =============================================================================
print("\n💻 Example 4: CLI Commands (for reference)")
print("-" * 40)
print("""
# Auto-generate agents (dynamic count)
praisonai --auto "Write a haiku about spring"

# Auto-generate workflow with pattern
praisonai workflow auto "Research and write a report" --pattern sequential
praisonai workflow auto "Research from multiple sources" --pattern parallel
praisonai workflow auto "Comprehensive market analysis" --pattern orchestrator-workers
praisonai workflow auto "Refine content quality" --pattern evaluator-optimizer

# With output file
praisonai workflow auto "Customer support routing" --pattern routing --output support.yaml
""")

print("\n" + "=" * 60)
print("✅ AutoAgents Workflow Patterns Demo Complete!")
print("=" * 60)
print("\nDocumentation: https://docs.praison.ai/features/autoagents")
print("CLI Reference: https://docs.praison.ai/nocode/auto")
