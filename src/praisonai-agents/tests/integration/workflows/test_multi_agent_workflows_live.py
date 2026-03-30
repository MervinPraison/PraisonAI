"""
Live integration tests for multi-agent workflows.

These tests require:
- PRAISONAI_LIVE_TESTS=1 environment variable  
- OPENAI_API_KEY environment variable

Run with: PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/workflows/test_multi_agent_workflows_live.py -v
"""

import pytest


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.mark.live
class TestSequentialWorkflowLive:
    """Live tests for sequential multi-agent workflows."""
    
    def test_sequential_agent_workflow_real_llm(self, openai_api_key):
        """Test sequential workflow with real LLM calls."""
        from praisonaiagents import Agent, AgentTeam, Task
        
        # Create specialized agents
        researcher = Agent(
            name="Researcher",
            role="Research Specialist", 
            goal="Research topics thoroughly",
            instructions="You research topics and provide factual information.",
            llm="gpt-4o-mini"
        )
        
        writer = Agent(
            name="Writer",
            role="Content Writer",
            goal="Write engaging content",
            instructions="You write clear, engaging content based on research.",
            llm="gpt-4o-mini"
        )
        
        # Create tasks that require real LLM interaction
        research_task = Task(
            name="research_ai",
            description="Research the latest developments in AI for 2024",
            expected_output="A summary of recent AI developments",
            agent=researcher
        )
        
        writing_task = Task(
            name="write_summary", 
            description="Write a 2-sentence summary based on the research findings",
            expected_output="A concise 2-sentence summary",
            agent=writer
        )
        
        # Create sequential workflow
        team = AgentTeam(
            agents=[researcher, writer],
            tasks=[research_task, writing_task],
            process="sequential"
        )
        
        # Execute workflow with real LLM calls
        result = team.start()
        
        # Assertions
        assert result is not None
        assert len(str(result)) > 0
        
        # Should contain research and writing outputs
        result_str = str(result).lower()
        assert "ai" in result_str or "artificial" in result_str
        
        print(f"Sequential workflow result: {result}")


@pytest.mark.live
class TestHierarchicalWorkflowLive:
    """Live tests for hierarchical multi-agent workflows."""
    
    def test_hierarchical_agent_workflow_real_llm(self, openai_api_key):
        """Test hierarchical workflow with manager coordination."""
        from praisonaiagents import Agent, AgentTeam, Task
        
        # Manager agent
        manager = Agent(
            name="Manager",
            role="Project Manager",
            goal="Coordinate team tasks",
            instructions="You coordinate tasks between team members efficiently.",
            llm="gpt-4o-mini"
        )
        
        # Specialist agents  
        analyst = Agent(
            name="Analyst",
            role="Data Analyst", 
            goal="Analyze information",
            instructions="You analyze data and provide insights.",
            llm="gpt-4o-mini"
        )
        
        executor = Agent(
            name="Executor",
            role="Task Executor",
            goal="Execute specific tasks", 
            instructions="You execute tasks based on analysis.",
            llm="gpt-4o-mini"
        )
        
        # Hierarchical tasks
        analysis_task = Task(
            name="analyze_problem",
            description="Analyze this problem: How to improve team productivity?",
            expected_output="Analysis of productivity factors",
            agent=analyst
        )
        
        execution_task = Task(
            name="create_solution",
            description="Create a solution based on the analysis",
            expected_output="Actionable productivity improvement plan",
            agent=executor
        )
        
        management_task = Task(
            name="coordinate_work",
            description="Coordinate the analysis and execution phases",
            expected_output="Coordinated project completion",
            agent=manager
        )
        
        # Create hierarchical team
        team = AgentTeam(
            agents=[manager, analyst, executor],
            tasks=[management_task, analysis_task, execution_task],
            process="hierarchical"
        )
        
        # Execute with real coordination
        result = team.start()
        
        # Assertions
        assert result is not None
        assert len(str(result)) > 0
        
        # Should contain coordination evidence
        result_str = str(result).lower()
        assert "productivity" in result_str
        
        print(f"Hierarchical workflow result: {result}")


@pytest.mark.live
class TestParallelWorkflowLive:
    """Live tests for parallel multi-agent workflows."""
    
    def test_parallel_agent_workflow_real_llm(self, openai_api_key):
        """Test parallel workflow with concurrent execution."""
        from praisonaiagents import Agent, AgentTeam, Task
        
        # Create parallel agents
        agent1 = Agent(
            name="Agent1",
            role="Specialist 1",
            goal="Handle task 1",
            instructions="You handle mathematical calculations.",
            llm="gpt-4o-mini"
        )
        
        agent2 = Agent(
            name="Agent2", 
            role="Specialist 2",
            goal="Handle task 2",
            instructions="You handle creative writing.",
            llm="gpt-4o-mini"
        )
        
        agent3 = Agent(
            name="Agent3",
            role="Specialist 3",
            goal="Handle task 3", 
            instructions="You handle factual questions.",
            llm="gpt-4o-mini"
        )
        
        # Independent parallel tasks
        task1 = Task(
            name="math_task",
            description="Calculate the square root of 144",
            expected_output="Mathematical calculation result", 
            agent=agent1
        )
        
        task2 = Task(
            name="creative_task",
            description="Write a haiku about programming",
            expected_output="A creative haiku poem",
            agent=agent2
        )
        
        task3 = Task(
            name="fact_task", 
            description="What is the capital of Japan?",
            expected_output="Factual answer about Japan's capital",
            agent=agent3
        )
        
        # Create parallel team
        team = AgentTeam(
            agents=[agent1, agent2, agent3],
            tasks=[task1, task2, task3],
            process="parallel"
        )
        
        # Execute in parallel
        result = team.start()
        
        # Assertions
        assert result is not None
        assert len(str(result)) > 0
        
        # Should contain all parallel outputs
        result_str = str(result).lower()
        assert "12" in result_str  # sqrt(144) = 12
        assert ("haiku" in result_str or "programming" in result_str)
        assert ("tokyo" in result_str or "japan" in result_str)
        
        print(f"Parallel workflow result: {result}")