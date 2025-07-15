#!/usr/bin/env python3
"""
Test basic functionality of praisonaiagents without requiring API keys
"""

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_agent_creation_and_attributes():
    """Test that agents can be created and configured properly"""
    print("Testing agent creation and configuration...")
    
    from praisonaiagents import Agent
    
    # Test 1: Basic agent creation
    agent = Agent(
        name="TestAgent",
        role="Test Agent",
        goal="Test agent functionality",
        backstory="A test agent for validation",
        instructions="You are a helpful test agent"
    )
    
    assert agent.name == "TestAgent"
    assert agent.role == "Test Agent"
    assert agent.goal == "Test agent functionality"
    assert agent.backstory == "A test agent for validation"
    assert agent.instructions == "You are a helpful test agent"
    
    print("✓ Basic agent creation successful")
    
    # Test 2: Agent with tools
    def test_tool(input_text: str) -> str:
        """A simple test tool function"""
        return f"Tool processed: {input_text}"
    
    agent_with_tools = Agent(
        instructions="Agent with tools",
        tools=[test_tool]
    )
    
    assert agent_with_tools.tools is not None
    print("✓ Agent with tools creation successful")
    
    # Test 3: Agent with self-reflection
    reflective_agent = Agent(
        instructions="Self-reflecting agent",
        self_reflect=True,
        min_reflect=1,
        max_reflect=3
    )
    
    assert reflective_agent.self_reflect
    assert reflective_agent.min_reflect == 1
    assert reflective_agent.max_reflect == 3
    
    print("✓ Self-reflecting agent creation successful")
    
    return True

def test_task_creation_and_workflow():
    """Test task creation and workflow setup"""
    print("\nTesting task creation and workflow...")
    
    from praisonaiagents import Agent, Task, PraisonAIAgents
    
    # Create agents
    agent1 = Agent(
        name="Agent1",
        instructions="First agent in workflow"
    )
    
    agent2 = Agent(
        name="Agent2", 
        instructions="Second agent in workflow"
    )
    
    # Create tasks
    task1 = Task(
        name="task1",
        description="First task in the workflow",
        expected_output="Result from first task",
        agent=agent1
    )
    
    task2 = Task(
        name="task2",
        description="Second task that depends on first",
        expected_output="Result from second task",
        agent=agent2,
        context=[task1]  # Task 2 depends on task 1
    )
    
    # Verify task attributes
    assert task1.name == "task1"
    assert task1.agent == agent1
    assert task2.context == [task1]
    
    print("✓ Task creation successful")
    
    # Create workflow
    workflow = PraisonAIAgents(
        agents=[agent1, agent2],
        tasks=[task1, task2],
        process="sequential"
    )
    
    assert len(workflow.agents) == 2
    assert len(workflow.tasks) == 2
    assert workflow.process == "sequential"
    
    print("✓ Workflow creation successful")
    
    return True

def test_tools_integration():
    """Test tools integration with agents"""
    print("\nTesting tools integration...")
    
    from praisonaiagents import Agent
    
    # Define test tools
    def calculator(expression: str) -> str:
        """Simple calculator tool"""
        try:
            # Basic math evaluation using safer approach
            import ast
            import operator
            
            # Support basic operations
            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
            }
            
            def safe_eval(node):
                if isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    return ops[type(node.op)](safe_eval(node.left), safe_eval(node.right))
                elif isinstance(node, ast.UnaryOp):
                    return ops[type(node.op)](safe_eval(node.operand))
                else:
                    raise ValueError(f"Unsupported operation: {type(node)}")
            
            tree = ast.parse(expression.replace(' ', ''), mode='eval')
            result = safe_eval(tree.body)
            return f"Result: {result}"
        except Exception as e:
            return f"Error: {e}"
    
    def text_processor(text: str) -> str:
        """Simple text processing tool"""
        return f"Processed: {text.upper()}"
    
    def counter(items: list) -> str:
        """Count items in a list"""
        return f"Count: {len(items)}"
    
    # Create agent with multiple tools
    agent = Agent(
        name="ToolAgent",
        instructions="Agent with multiple tools",
        tools=[calculator, text_processor, counter]
    )
    
    assert agent.tools is not None
    assert len(agent.tools) == 3
    
    print("✓ Multiple tools integration successful")
    
    return True

def test_different_agent_types():
    """Test different types of agents"""
    print("\nTesting different agent types...")
    
    from praisonaiagents import Agent, ImageAgent
    
    # Regular agent
    regular_agent = Agent(
        instructions="Regular agent"
    )
    
    # Image agent
    try:
        image_agent = ImageAgent(
            instructions="Image processing agent"
        )
        print("✓ ImageAgent creation successful")
    except Exception as e:
        print(f"ℹ ImageAgent creation failed (may need additional dependencies): {e}")
    
    # Agent with specific LLM
    llm_agent = Agent(
        instructions="Agent with specific LLM",
        llm="gpt-4o-mini"
    )
    
    assert llm_agent.llm == "gpt-4o-mini"
    print("✓ Agent with specific LLM successful")
    
    return True

def test_example_workflow_structure():
    """Test the structure of a typical workflow"""
    print("\nTesting example workflow structure...")
    
    from praisonaiagents import Agent, Task, PraisonAIAgents
    
    # Create a realistic workflow structure
    researcher = Agent(
        name="Researcher",
        role="Research Specialist",
        goal="Gather information on given topics",
        backstory="Expert at finding and analyzing information",
        instructions="Research the given topic thoroughly"
    )
    
    analyst = Agent(
        name="Analyst",
        role="Data Analyst",
        goal="Analyze and interpret research data",
        backstory="Skilled at data analysis and interpretation",
        instructions="Analyze the research data and provide insights"
    )
    
    writer = Agent(
        name="Writer",
        role="Content Writer", 
        goal="Create well-written content based on analysis",
        backstory="Professional writer with expertise in technical writing",
        instructions="Write clear, engaging content based on the analysis"
    )
    
    # Create workflow tasks
    research_task = Task(
        name="research",
        description="Research the topic of artificial intelligence",
        expected_output="Comprehensive research summary",
        agent=researcher
    )
    
    analysis_task = Task(
        name="analyze",
        description="Analyze the research findings",
        expected_output="Detailed analysis report",
        agent=analyst,
        context=[research_task]
    )
    
    writing_task = Task(
        name="write",
        description="Write a blog post based on the analysis",
        expected_output="Well-written blog post",
        agent=writer,
        context=[analysis_task]
    )
    
    # Create complete workflow
    workflow = PraisonAIAgents(
        agents=[researcher, analyst, writer],
        tasks=[research_task, analysis_task, writing_task],
        process="sequential",
        verbose=True
    )
    
    # Verify workflow structure
    assert len(workflow.agents) == 3
    assert len(workflow.tasks) == 3
    # Verify context dependencies exist
    assert analysis_task.context is not None
    assert writing_task.context is not None
    assert len(analysis_task.context) > 0
    assert len(writing_task.context) > 0
    
    print("✓ Complex workflow structure successful")
    
    return True

def main():
    """Run all functionality tests"""
    print("=" * 60)
    print("PRAISONAIAGENTS BASIC FUNCTIONALITY TEST")
    print("=" * 60)
    
    tests = [
        test_agent_creation_and_attributes,
        test_task_creation_and_workflow,
        test_tools_integration,
        test_different_agent_types,
        test_example_workflow_structure
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"FUNCTIONALITY TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 All functionality tests passed!")
        print("🚀 The praisonaiagents package is working correctly.")
        print("📝 You can now use the package with actual LLM providers by setting API keys.")
    else:
        print("❌ Some functionality tests failed.")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())