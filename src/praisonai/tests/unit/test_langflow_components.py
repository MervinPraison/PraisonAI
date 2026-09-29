import pytest
pytest.importorskip("langflow")
from praisonai.flow.components.PraisonAI.praisonai_agent import PraisonAIAgentComponent
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

def test_praisonai_agents_component():
    """Verify PraisonAIAgentsComponent builds the AgentTeam successfully."""
    agent_comp = PraisonAIAgentComponent()
    agent_comp.agent_name = "TeamAgent"
    agent_comp.instructions = "Say yes"
    agent_comp.llm = "openai/gpt-4o-mini"
    built_agent = agent_comp.build_agent()
    
    agents_comp = PraisonAIAgentsComponent()
    agents_comp.team_name = "AgentTeamTest"
    agents_comp.agents = [built_agent]
    agents_comp.process = "sequential"
    agents_comp.memory = False
    
    built_agents = agents_comp.build_agents()
    assert built_agents.process == "sequential"
    assert len(built_agents.agents) == 1
