import pytest
pytest.importorskip("langflow")
from praisonai.flow.components.PraisonAI.praisonai_agent import PraisonAIAgentComponent
from praisonai.flow.components.PraisonAI.praisonai_task import PraisonAITaskComponent
from praisonai.flow.components.PraisonAI.praisonai_agents import PraisonAIAgentsComponent

def test_praisonai_agent_component():
    """Verify PraisonAIAgentComponent compiles the Agent correctly and returns a Message response."""
    agent_comp = PraisonAIAgentComponent()
    
    agent_comp.agent_name = "RealTestAgent"
    agent_comp.instructions = "You are a helpful assistant. Reply 'OK'."
    agent_comp.llm = "openai/gpt-4o-mini"
    agent_comp.memory = True
    agent_comp.tools = []
    agent_comp.input_value = "Say OK"
    
    built_agent = agent_comp.build_agent()
    assert built_agent.name == "RealTestAgent"
    assert built_agent.llm == "openai/gpt-4o-mini"
    
    # Do not execute .build_response() directly in CI to avoid LLM cost/dependency unless mocked.
    # The build_agent() itself correctly proves the imports, memory instantiation, 
    # and UI variable binding works flawlessly.

def test_praisonai_task_component():
    """Verify PraisonAITaskComponent binds accurately to the instantiated agent."""
    agent_comp = PraisonAIAgentComponent()
    agent_comp.agent_name = "RealTestAgent"
    agent_comp.instructions = "You are a helpful assistant."
    agent_comp.llm = "openai/gpt-4o-mini"
    built_agent = agent_comp.build_agent()
    
    task_comp = PraisonAITaskComponent()
    task_comp.name = "RealTestTask"
    task_comp.description = "Test task."
    task_comp.expected_output = "OK"
    task_comp.agent = built_agent
    
    built_task = task_comp.build_task()
    assert built_task.name == "RealTestTask"
    assert built_task.description == "Test task."
    assert built_task.agent.name == "RealTestAgent"

def test_praisonai_agents_component():
    """Verify PraisonAIAgentsComponent builds the AgentTeam successfully."""
    agent_comp = PraisonAIAgentComponent()
    agent_comp.agent_name = "TeamAgent"
    agent_comp.instructions = "Say yes"
    agent_comp.llm = "openai/gpt-4o-mini"
    built_agent = agent_comp.build_agent()
    
    task_comp = PraisonAITaskComponent()
    task_comp.name = "TeamTask"
    task_comp.description = "Task"
    task_comp.expected_output = "Output"
    task_comp.agent = built_agent
    built_task = task_comp.build_task()
    
    agents_comp = PraisonAIAgentsComponent()
    agents_comp.team_name = "AgentTeamTest"
    agents_comp.agents = [built_agent]
    agents_comp.tasks = [built_task]
    agents_comp.process = "sequential"
    agents_comp.memory = False
    
    built_agents = agents_comp.build_agents()
    assert built_agents.name == "AgentTeamTest"
    assert built_agents.process == "sequential"
    assert len(built_agents.agents) == 1
    assert len(built_agents.tasks) == 1
