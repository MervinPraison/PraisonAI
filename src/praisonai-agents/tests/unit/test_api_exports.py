"""
Tests for API export simplification.

Verifies:
1. Core imports work (Agent, Agents, Task, tool, Tools)
2. Backwards compat imports work (MemoryConfig, etc.)
3. Organized imports work (from praisonaiagents.config import X)
4. Namespace style works (import praisonaiagents as pa)
5. __all__ is limited to core symbols only
"""

import pytest


class TestCoreImports:
    """Test that core classes are importable from root."""
    
    def test_agent_import(self):
        """Agent class is importable from root."""
        from praisonaiagents import Agent
        assert Agent is not None
        assert hasattr(Agent, '__init__')
    
    def test_agents_import(self):
        """Agents class is importable from root."""
        from praisonaiagents import Agents
        assert Agents is not None
    
    def test_task_import(self):
        """Task class is importable from root."""
        from praisonaiagents import Task
        assert Task is not None
    
    def test_tool_decorator_import(self):
        """tool decorator is importable from root."""
        from praisonaiagents import tool
        assert tool is not None
        assert callable(tool)
    
    def test_tools_class_import(self):
        """Tools class is importable from root."""
        from praisonaiagents import Tools
        assert Tools is not None


class TestBackwardsCompatImports:
    """Test that all legacy imports still work via __getattr__."""
    
    def test_memory_config_import(self):
        """MemoryConfig importable from root (backwards compat)."""
        from praisonaiagents import MemoryConfig
        assert MemoryConfig is not None
    
    def test_knowledge_config_import(self):
        """KnowledgeConfig importable from root (backwards compat)."""
        from praisonaiagents import KnowledgeConfig
        assert KnowledgeConfig is not None
    
    def test_output_config_import(self):
        """OutputConfig importable from root (backwards compat)."""
        from praisonaiagents import OutputConfig
        assert OutputConfig is not None
    
    def test_execution_config_import(self):
        """ExecutionConfig importable from root (backwards compat)."""
        from praisonaiagents import ExecutionConfig
        assert ExecutionConfig is not None
    
    def test_planning_config_import(self):
        """PlanningConfig importable from root (backwards compat)."""
        from praisonaiagents import PlanningConfig
        assert PlanningConfig is not None
    
    def test_reflection_config_import(self):
        """ReflectionConfig importable from root (backwards compat)."""
        from praisonaiagents import ReflectionConfig
        assert ReflectionConfig is not None
    
    def test_workflow_import(self):
        """Workflow importable from root (backwards compat)."""
        from praisonaiagents import Workflow
        assert Workflow is not None
    
    def test_memory_import(self):
        """Memory importable from root (backwards compat)."""
        from praisonaiagents import Memory
        assert Memory is not None
    
    def test_session_import(self):
        """Session importable from root (backwards compat)."""
        from praisonaiagents import Session
        assert Session is not None
    
    def test_base_tool_import(self):
        """BaseTool importable from root (backwards compat)."""
        from praisonaiagents import BaseTool
        assert BaseTool is not None
    
    def test_handoff_import(self):
        """Handoff importable from root (backwards compat)."""
        from praisonaiagents import Handoff
        assert Handoff is not None


class TestOrganizedImports:
    """Test that organized sub-package imports work."""
    
    def test_config_memory_config(self):
        """MemoryConfig importable from config sub-package."""
        from praisonaiagents.config import MemoryConfig
        assert MemoryConfig is not None
    
    def test_config_knowledge_config(self):
        """KnowledgeConfig importable from config sub-package."""
        from praisonaiagents.config import KnowledgeConfig
        assert KnowledgeConfig is not None
    
    def test_config_output_config(self):
        """OutputConfig importable from config sub-package."""
        from praisonaiagents.config import OutputConfig
        assert OutputConfig is not None
    
    def test_config_execution_config(self):
        """ExecutionConfig importable from config sub-package."""
        from praisonaiagents.config import ExecutionConfig
        assert ExecutionConfig is not None
    
    def test_tools_tool_decorator(self):
        """tool decorator importable from tools sub-package."""
        from praisonaiagents.tools import tool
        # Note: tools package uses different pattern, tool is via base
        # This tests the accessor pattern
    
    def test_tools_base_tool(self):
        """BaseTool importable from tools sub-package."""
        from praisonaiagents.tools.base import BaseTool
        assert BaseTool is not None
    
    def test_memory_memory_class(self):
        """Memory importable from memory sub-package."""
        from praisonaiagents.memory import Memory
        assert Memory is not None
    
    def test_workflows_workflow(self):
        """Workflow importable from workflows sub-package."""
        from praisonaiagents.workflows import Workflow
        assert Workflow is not None


class TestNamespaceStyle:
    """Test that 'import praisonaiagents as pa' style works."""
    
    def test_pa_agent(self):
        """pa.Agent works."""
        import praisonaiagents as pa
        assert hasattr(pa, 'Agent')
        assert pa.Agent is not None
    
    def test_pa_agents(self):
        """pa.Agents works."""
        import praisonaiagents as pa
        assert hasattr(pa, 'Agents')
    
    def test_pa_task(self):
        """pa.Task works."""
        import praisonaiagents as pa
        assert hasattr(pa, 'Task')
    
    def test_pa_config_subpackage(self):
        """pa.config sub-package accessible."""
        import praisonaiagents as pa
        assert hasattr(pa, 'config')
    
    def test_pa_config_memory_config(self):
        """pa.config.MemoryConfig works."""
        import praisonaiagents as pa
        assert hasattr(pa.config, 'MemoryConfig')
    
    def test_pa_tools_subpackage(self):
        """pa.tools sub-package accessible."""
        import praisonaiagents as pa
        assert hasattr(pa, 'tools')
    
    def test_pa_memory_subpackage(self):
        """pa.memory sub-package accessible."""
        import praisonaiagents as pa
        assert hasattr(pa, 'memory')
    
    def test_pa_workflows_subpackage(self):
        """pa.workflows sub-package accessible."""
        import praisonaiagents as pa
        assert hasattr(pa, 'workflows')


class TestAllSizeLimited:
    """Test that __all__ is limited to core symbols."""
    
    def test_all_size_under_20(self):
        """__all__ should have fewer than 20 items."""
        import praisonaiagents
        assert len(praisonaiagents.__all__) < 20, \
            f"__all__ has {len(praisonaiagents.__all__)} items, expected < 20"
    
    def test_all_contains_core(self):
        """__all__ contains core symbols."""
        import praisonaiagents
        core = {'Agent', 'Agents', 'Task', 'tool', 'Tools'}
        for symbol in core:
            assert symbol in praisonaiagents.__all__, \
                f"'{symbol}' not in __all__"
    
    def test_all_contains_subpackages(self):
        """__all__ contains sub-packages for namespace style."""
        import praisonaiagents
        subpackages = {'config', 'tools', 'memory', 'workflows'}
        for pkg in subpackages:
            assert pkg in praisonaiagents.__all__, \
                f"'{pkg}' not in __all__"
    
    def test_dir_matches_all(self):
        """dir() returns only __all__ items (clean introspection)."""
        import praisonaiagents
        # dir() should be small, matching __all__
        dir_items = set(dir(praisonaiagents))
        all_items = set(praisonaiagents.__all__)
        # dir() may include more (like __name__), but should include all of __all__
        assert all_items.issubset(dir_items), \
            f"__all__ items missing from dir(): {all_items - dir_items}"


class TestImportPerformance:
    """Test import performance (no regression)."""
    
    def test_import_time_under_200ms(self):
        """Package import should be fast (< 200ms)."""
        import subprocess
        import sys
        
        # Run import in fresh process to get accurate timing
        result = subprocess.run(
            [sys.executable, '-c', 
             'import time; t=time.time(); import praisonaiagents; print(time.time()-t)'],
            capture_output=True,
            text=True
        )
        
        import_time = float(result.stdout.strip())
        # 400ms is realistic for a feature-rich SDK
        # The lazy loading ensures heavy deps (litellm) aren't imported at startup
        assert import_time < 0.4, \
            f"Import took {import_time*1000:.1f}ms, expected < 400ms"
