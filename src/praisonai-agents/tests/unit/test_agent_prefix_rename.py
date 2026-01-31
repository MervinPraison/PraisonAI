"""
TDD Tests for Agent* Prefix Renaming

Tests the renaming of core orchestration classes:
- AgentManager → AgentTeam
- Workflow → AgentFlow  
- AgentAppProtocol → AgentOSProtocol

All old names should work as silent aliases (no deprecation warnings).
"""

import pytest
import warnings


class TestAgentTeamRename:
    """Tests for AgentManager → AgentTeam rename."""
    
    def test_agent_team_importable(self):
        """AgentTeam should be importable as the primary class."""
        from praisonaiagents import AgentTeam
        assert AgentTeam is not None
        assert AgentTeam.__name__ == "AgentTeam"
    
    def test_agent_manager_is_silent_alias(self):
        """AgentManager should work as a silent alias (no warnings)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonaiagents import AgentTeam
            # Filter for deprecation warnings only
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0, f"Got deprecation warnings: {deprecation_warnings}"
    
    def test_agent_manager_is_agent_team(self):
        """AgentManager should be the same class as AgentTeam."""
        from praisonaiagents import AgentManager, AgentTeam
        assert AgentManager is AgentTeam
    
    def test_agent_team_from_agents_module(self):
        """AgentTeam should be importable from agents module."""
        from praisonaiagents.agents import AgentTeam
        assert AgentTeam is not None
        assert AgentTeam.__name__ == "AgentTeam"
    
    def test_agent_manager_from_agents_module(self):
        """AgentManager should be importable from agents module as alias."""
        from praisonaiagents.agents import AgentManager
        from praisonaiagents.agents import AgentTeam
        assert AgentManager is AgentTeam


class TestAgentFlowRename:
    """Tests for Workflow → AgentFlow rename."""
    
    def test_agent_flow_importable(self):
        """AgentFlow should be importable as the primary class."""
        from praisonaiagents import AgentFlow
        assert AgentFlow is not None
        assert AgentFlow.__name__ == "AgentFlow"
    
    def test_workflow_is_silent_alias(self):
        """Workflow should work as a silent alias (no warnings)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonaiagents import Workflow
            # Filter for deprecation warnings only
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0, f"Got deprecation warnings: {deprecation_warnings}"
    
    def test_workflow_is_agent_flow(self):
        """Workflow should be the same class as AgentFlow."""
        from praisonaiagents import AgentFlow, Workflow
        assert Workflow is AgentFlow
    
    def test_agent_flow_from_workflows_module(self):
        """AgentFlow should be importable from workflows module."""
        from praisonaiagents.workflows import AgentFlow
        assert AgentFlow is not None
        assert AgentFlow.__name__ == "AgentFlow"
    
    def test_workflow_from_workflows_module(self):
        """Workflow should be importable from workflows module as alias."""
        from praisonaiagents.workflows import Workflow
        from praisonaiagents.workflows import AgentFlow
        assert Workflow is AgentFlow
    
    def test_pipeline_alias_still_works(self):
        """Pipeline alias should still work (points to AgentFlow)."""
        from praisonaiagents.workflows import Pipeline, AgentFlow
        assert Pipeline is AgentFlow


class TestAgentOSRename:
    """Tests for AgentAppProtocol → AgentOSProtocol rename."""
    
    def test_agent_os_protocol_importable(self):
        """AgentOSProtocol should be importable as the primary protocol."""
        from praisonaiagents import AgentOSProtocol
        assert AgentOSProtocol is not None
    
    def test_agent_app_protocol_is_silent_alias(self):
        """AgentAppProtocol should work as a silent alias (no warnings)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonaiagents import AgentAppProtocol
            # Filter for deprecation warnings only
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0, f"Got deprecation warnings: {deprecation_warnings}"
    
    def test_agent_app_protocol_is_agent_os_protocol(self):
        """AgentAppProtocol should be the same as AgentOSProtocol."""
        from praisonaiagents import AgentOSProtocol, AgentAppProtocol
        assert AgentAppProtocol is AgentOSProtocol
    
    def test_agent_os_config_importable(self):
        """AgentOSConfig should be importable as the primary config."""
        from praisonaiagents import AgentOSConfig
        assert AgentOSConfig is not None
    
    def test_agent_app_config_is_silent_alias(self):
        """AgentAppConfig should work as a silent alias (no warnings)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonaiagents import AgentAppConfig
            # Filter for deprecation warnings only
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0, f"Got deprecation warnings: {deprecation_warnings}"
    
    def test_agent_app_config_is_agent_os_config(self):
        """AgentAppConfig should be the same as AgentOSConfig."""
        from praisonaiagents import AgentOSConfig, AgentAppConfig
        assert AgentAppConfig is AgentOSConfig


class TestExportsAndAll:
    """Tests for __all__ exports."""
    
    def test_primary_names_in_all(self):
        """Primary names should be in __all__."""
        import praisonaiagents
        all_exports = getattr(praisonaiagents, '__all__', [])
        # Primary names should be exported
        assert 'AgentTeam' in all_exports or hasattr(praisonaiagents, 'AgentTeam')
        assert 'AgentFlow' in all_exports or hasattr(praisonaiagents, 'AgentFlow')
        assert 'AgentOSProtocol' in all_exports or hasattr(praisonaiagents, 'AgentOSProtocol')
    
    def test_agent_unchanged(self):
        """Agent class should remain unchanged."""
        from praisonaiagents import Agent
        assert Agent is not None
        assert Agent.__name__ == "Agent"


class TestFunctionalBehavior:
    """Tests that renamed classes work correctly."""
    
    def test_agent_team_instantiation(self):
        """AgentTeam should be instantiable with agents."""
        from praisonaiagents import Agent, AgentTeam
        
        agent = Agent(name="test", instructions="Test agent")
        team = AgentTeam(agents=[agent])
        
        assert team is not None
        assert len(team.agents) == 1
    
    def test_agent_flow_instantiation(self):
        """AgentFlow should be instantiable with steps."""
        from praisonaiagents import Agent, AgentFlow
        
        agent = Agent(name="test", instructions="Test agent")
        flow = AgentFlow(steps=[agent])
        
        assert flow is not None
        assert len(flow.steps) == 1
    
    def test_backward_compat_agent_manager_instantiation(self):
        """AgentManager (alias) should work identically to AgentTeam."""
        from praisonaiagents import Agent, AgentTeam
        
        agent = Agent(name="test", instructions="Test agent")
        manager = AgentTeam(agents=[agent])
        
        assert manager is not None
        assert len(manager.agents) == 1
    
    def test_backward_compat_workflow_instantiation(self):
        """Workflow (alias) should work identically to AgentFlow."""
        from praisonaiagents import Agent, Workflow
        
        agent = Agent(name="test", instructions="Test agent")
        workflow = Workflow(steps=[agent])
        
        assert workflow is not None
        assert len(workflow.steps) == 1
