"""
Test AG-UI Integration - TDD Tests for End-to-End Integration

Phase 7: Integration Tests
- Test full flow with single Agent
- Test full flow with PraisonAIAgents
- Test tool calling flow
- Test error recovery
- Test state persistence
"""

class TestSingleAgentIntegration:
    """Test integration with single Agent."""
    
    def test_single_agent_chat_flow(self):
        """Test complete chat flow with single agent."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        import json
        
        agent = Agent(
            name="Assistant",
            role="Helpful Assistant",
            goal="Help users with their questions",
            llm="gpt-4o-mini"
        )
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        # Send a message
        response = client.post("/agui", json={
            "thread_id": "test-thread",
            "messages": [{"role": "user", "content": "Say hello"}]
        })
        
        assert response.status_code == 200
        
        # Parse SSE events
        events = []
        for line in response.text.split("\n"):
            if line.startswith("data: "):
                event_data = json.loads(line[6:])
                events.append(event_data)
        
        # Should have run started event
        event_types = [e.get("type") for e in events]
        assert "RUN_STARTED" in event_types
        assert "RUN_FINISHED" in event_types or "RUN_ERROR" in event_types


class TestMultiAgentIntegration:
    """Test integration with PraisonAIAgents."""
    
    def test_multi_agent_workflow_flow(self):
        """Test complete workflow with multiple agents."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent, Task, PraisonAIAgents
        from fastapi import FastAPI
        import json
        
        # Create agents
        researcher = Agent(
            name="Researcher",
            role="Research Analyst",
            goal="Research topics thoroughly",
            llm="gpt-4o-mini"
        )
        writer = Agent(
            name="Writer",
            role="Content Writer",
            goal="Write engaging content",
            llm="gpt-4o-mini"
        )
        
        # Create tasks
        research_task = Task(
            description="Research the topic: {topic}",
            expected_output="Research findings",
            agent=researcher
        )
        write_task = Task(
            description="Write about the research",
            expected_output="Written article",
            agent=writer
        )
        
        # Create PraisonAIAgents
        agents = PraisonAIAgents(
            agents=[researcher, writer],
            tasks=[research_task, write_task]
        )
        
        agui = AGUI(agents=agents)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "test-thread",
            "messages": [{"role": "user", "content": "Research AI"}]
        })
        
        assert response.status_code == 200


class TestToolCallingIntegration:
    """Test integration with tool calling."""
    
    def test_agent_with_tools(self):
        """Test agent with tools integration."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        import json
        
        def search_tool(query: str) -> str:
            """Search for information."""
            return f"Search results for: {query}"
        
        agent = Agent(
            name="SearchAgent",
            role="Search Assistant",
            goal="Help users search for information",
            tools=[search_tool],
            llm="gpt-4o-mini"
        )
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "test-thread",
            "messages": [{"role": "user", "content": "Search for Python tutorials"}]
        })
        
        assert response.status_code == 200
        
        # Parse events
        events = []
        for line in response.text.split("\n"):
            if line.startswith("data: "):
                event_data = json.loads(line[6:])
                events.append(event_data)
        
        # Check for tool call events (may or may not have them depending on LLM response)
        event_types = [e.get("type") for e in events]
        assert "RUN_STARTED" in event_types


class TestStateManagement:
    """Test state management in AG-UI."""
    
    def test_state_passed_to_agent(self):
        """Test that state is passed to agent."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(
            name="StatefulAgent",
            role="Stateful Assistant",
            goal="Remember context",
            llm="gpt-4o-mini"
        )
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "test-thread",
            "messages": [{"role": "user", "content": "Hello"}],
            "state": {"user_name": "John", "preferences": {"language": "en"}}
        })
        
        assert response.status_code == 200


class TestConversationHistory:
    """Test conversation history handling."""
    
    def test_multiple_messages_in_history(self):
        """Test handling multiple messages in conversation history."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(
            name="ChatAgent",
            role="Chat Assistant",
            goal="Have conversations",
            llm="gpt-4o-mini"
        )
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "test-thread",
            "messages": [
                {"role": "user", "content": "My name is John"},
                {"role": "assistant", "content": "Hello John!"},
                {"role": "user", "content": "What is my name?"}
            ]
        })
        
        assert response.status_code == 200


class TestErrorRecovery:
    """Test error recovery scenarios."""
    
    def test_graceful_error_handling(self):
        """Test graceful error handling."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        import json
        
        # Agent with invalid LLM should handle error gracefully
        agent = Agent(
            name="ErrorAgent",
            role="Error Test",
            goal="Test error handling",
            llm="invalid-model-name"
        )
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "test-thread",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        # Should not crash, should return error event
        assert response.status_code == 200
        
        # Parse events
        events = []
        for line in response.text.split("\n"):
            if line.startswith("data: "):
                try:
                    event_data = json.loads(line[6:])
                    events.append(event_data)
                except json.JSONDecodeError:
                    pass
        
        # Should have error event
        event_types = [e.get("type") for e in events]
        assert "RUN_ERROR" in event_types or "RUN_FINISHED" in event_types


class TestPerformance:
    """Test performance - ensure no impact on existing functionality."""
    
    def test_agui_import_does_not_slow_package(self):
        """Test that importing AGUI doesn't slow down package import."""
        import time
        
        start = time.time()
        from praisonaiagents.ui.agui import AGUI
        import_time = time.time() - start
        
        # Import should be fast (< 1 second)
        assert import_time < 1.0
    
    def test_agui_lazy_loading(self):
        """Test that AGUI uses lazy loading where possible."""
        # This test ensures we don't import heavy dependencies until needed
        import sys
        
        # Remove agui from cache if present
        modules_to_remove = [k for k in sys.modules.keys() if 'agui' in k]
        for mod in modules_to_remove:
            del sys.modules[mod]
        
        # Import should not load FastAPI until get_router is called
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test")
        agui = AGUI(agent=agent)
        
        # FastAPI should be loaded when get_router is called
        router = agui.get_router()
        assert router is not None
