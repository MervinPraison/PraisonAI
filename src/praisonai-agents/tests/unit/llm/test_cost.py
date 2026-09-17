"""
Tests for the centralized cost calculation module.

Tests verify:
1. Lazy loading of litellm
2. Cost tracking enable/disable via environment variables
3. Cost calculation with various response formats
"""

import os
import sys
from unittest.mock import patch, MagicMock


class TestCostModule:
    """Tests for praisonaiagents.llm._cost module."""
    
    def setup_method(self):
        """Reset module state before each test."""
        # Clear any cached litellm module (shared loader state)
        import praisonaiagents.llm._litellm_loader as loader_module
        loader_module._litellm_module = None
        loader_module._litellm_import_attempted = False
        
        # Clear environment variables
        os.environ.pop('PRAISONAI_TRACK_COST', None)
        os.environ.pop('PRAISONAI_SAVE_OUTPUT', None)
    
    def test_is_cost_tracking_disabled_by_default(self):
        """Cost tracking should be disabled by default."""
        from praisonaiagents.llm._cost import is_cost_tracking_enabled
        
        assert is_cost_tracking_enabled() is False
    
    def test_is_cost_tracking_enabled_with_env_var(self):
        """Cost tracking should be enabled with PRAISONAI_TRACK_COST=true."""
        os.environ['PRAISONAI_TRACK_COST'] = 'true'
        
        from praisonaiagents.llm._cost import is_cost_tracking_enabled
        
        assert is_cost_tracking_enabled() is True
    
    def test_is_cost_tracking_enabled_with_save_output(self):
        """Cost tracking should be enabled with PRAISONAI_SAVE_OUTPUT=true."""
        os.environ['PRAISONAI_SAVE_OUTPUT'] = 'true'
        
        from praisonaiagents.llm._cost import is_cost_tracking_enabled
        
        assert is_cost_tracking_enabled() is True
    
    def test_calculate_cost_returns_none_when_disabled(self):
        """calculate_cost should return None when tracking is disabled."""
        from praisonaiagents.llm._cost import calculate_cost
        
        # Create a mock response
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {'model': 'gpt-4o-mini'}
        
        result = calculate_cost(mock_response)
        
        assert result is None
    
    def test_calculate_cost_with_force_flag(self):
        """calculate_cost should work with force=True even when tracking disabled."""
        from praisonaiagents.llm._cost import calculate_cost
        
        # Mock litellm
        with patch('praisonaiagents.llm._cost._get_litellm') as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.completion_cost.return_value = 0.001
            mock_get_litellm.return_value = mock_litellm
            
            mock_response = {'model': 'gpt-4o-mini', 'usage': {'prompt_tokens': 10, 'completion_tokens': 20}}
            
            result = calculate_cost(mock_response, force=True)
            
            assert result == 0.001
            mock_litellm.completion_cost.assert_called_once()
    
    def test_calculate_cost_handles_pydantic_model(self):
        """calculate_cost should handle Pydantic models with model_dump."""
        os.environ['PRAISONAI_TRACK_COST'] = 'true'
        
        from praisonaiagents.llm._cost import calculate_cost
        
        with patch('praisonaiagents.llm._cost._get_litellm') as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.completion_cost.return_value = 0.002
            mock_get_litellm.return_value = mock_litellm
            
            # Create mock Pydantic-like response
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {'model': 'gpt-4o-mini'}
            
            result = calculate_cost(mock_response)
            
            assert result == 0.002
    
    def test_calculate_cost_handles_dict(self):
        """calculate_cost should handle dict responses."""
        os.environ['PRAISONAI_TRACK_COST'] = 'true'
        
        from praisonaiagents.llm._cost import calculate_cost
        
        with patch('praisonaiagents.llm._cost._get_litellm') as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.completion_cost.return_value = 0.003
            mock_get_litellm.return_value = mock_litellm
            
            result = calculate_cost({'model': 'gpt-4o-mini'})
            
            assert result == 0.003
    
    def test_calculate_cost_returns_none_on_error(self):
        """calculate_cost should return None on error."""
        os.environ['PRAISONAI_TRACK_COST'] = 'true'
        
        from praisonaiagents.llm._cost import calculate_cost
        
        with patch('praisonaiagents.llm._cost._get_litellm') as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.completion_cost.side_effect = Exception("API error")
            mock_get_litellm.return_value = mock_litellm
            
            result = calculate_cost({'model': 'gpt-4o-mini'})
            
            assert result is None
    
    def test_calculate_cost_returns_none_when_litellm_unavailable(self):
        """calculate_cost should return None when litellm is not installed."""
        os.environ['PRAISONAI_TRACK_COST'] = 'true'
        
        from praisonaiagents.llm._cost import calculate_cost
        
        with patch('praisonaiagents.llm._cost._get_litellm') as mock_get_litellm:
            mock_get_litellm.return_value = None
            
            result = calculate_cost({'model': 'gpt-4o-mini'})
            
            assert result is None
    
    def test_enable_cost_tracking(self):
        """enable_cost_tracking should set environment variable."""
        from praisonaiagents.llm._cost import enable_cost_tracking, is_cost_tracking_enabled
        
        assert is_cost_tracking_enabled() is False
        
        enable_cost_tracking()
        
        assert is_cost_tracking_enabled() is True
        assert os.environ.get('PRAISONAI_TRACK_COST') == 'true'
    
    def test_disable_cost_tracking(self):
        """disable_cost_tracking should remove environment variable."""
        from praisonaiagents.llm._cost import disable_cost_tracking, is_cost_tracking_enabled
        
        os.environ['PRAISONAI_TRACK_COST'] = 'true'
        assert is_cost_tracking_enabled() is True
        
        disable_cost_tracking()
        
        assert is_cost_tracking_enabled() is False
    
    def test_lazy_litellm_import(self):
        """_get_litellm should cache the import result."""
        import praisonaiagents.llm._cost as cost_module

        # Resolve the loader through the function _cost actually calls, not by
        # importing it afresh. Several teardowns in this suite delete every
        # module whose name contains "praison" or "litellm" -- which includes
        # praisonaiagents.llm._litellm_loader -- and restore only what they had
        # backed up. Anything imported after the backup comes back as a NEW
        # module object, so `import ... as loader_module` could hand back a
        # different object than the one get_litellm() reads its globals from:
        # the test set flags on one and asserted about the other.
        # __globals__, not sys.modules: looking the module up by NAME can
        # return a different object than the one this function closes over,
        # and the flag lives in the namespace the function actually mutates.
        loader_globals = cost_module.get_litellm.__globals__
        
        # Reset shared loader state -- and put it back afterwards. These are
        # module globals shared by everything that loads litellm lazily, so
        # leaving them reset changed later tests' behaviour and left this one
        # dependent on whether something had already populated them.
        _saved_module = loader_globals["_litellm_module"]
        _saved_attempted = loader_globals["_litellm_import_attempted"]
        loader_globals["_litellm_module"] = None
        loader_globals["_litellm_import_attempted"] = False

        try:
            # First call
            result1 = cost_module._get_litellm()

            # Second call should use cache
            result2 = cost_module._get_litellm()

            assert result1 is result2
            assert loader_globals["_litellm_import_attempted"] is True
        finally:
            loader_globals["_litellm_module"] = _saved_module
            loader_globals["_litellm_import_attempted"] = _saved_attempted

    def test_on_missing_fires_regardless_of_call_order(self):
        """on_missing must fire even if another caller attempted the import first.

        Regression for the shared-cache bug: when litellm is unavailable and a
        caller without on_missing (e.g. model_capabilities) loads first, a later
        caller passing on_missing (e.g. _cost) must still get its callback.
        """
        import builtins
        import praisonaiagents.llm._litellm_loader as loader_module

        # Reset shared loader state
        loader_module._litellm_module = None
        loader_module._litellm_import_attempted = False

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == 'litellm':
                raise ImportError("simulated missing litellm")
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=fake_import):
            # First caller, no on_missing (model_capabilities-style)
            assert loader_module.get_litellm() is None

            # Second caller passes on_missing; it must still fire on cached miss
            calls = []
            assert loader_module.get_litellm(on_missing=lambda: calls.append(1)) is None
            assert calls == [1]


class TestCostModuleIntegration:
    """Integration tests for cost module with Agent."""
    
    def setup_method(self):
        """Reset state before each test."""
        os.environ.pop('PRAISONAI_TRACK_COST', None)
        os.environ.pop('PRAISONAI_SAVE_OUTPUT', None)
    
    def test_agent_creation_does_not_import_litellm(self):
        """Creating an agent with output='silent' should not import litellm.

        The litellm modules removed to set this up are restored afterwards.
        They were not, and a torn-down litellm is not a neutral state: modules
        already imported keep references to the old objects while anything
        importing it afterwards gets a fresh, different one. That broke tool
        resolution in tests/unit/tools/test_mixed_tools_list_resolution.py --
        which passes alone and failed only once this file had run -- and left
        this test itself dependent on whether something else had imported
        litellm first.
        """
        removed = {name: mod for name, mod in sys.modules.items() if 'litellm' in name}
        for name in removed:
            del sys.modules[name]

        try:
            from praisonaiagents import Agent

            _agent = Agent(name='Test', llm='gpt-4o-mini', output='silent')

            # litellm should not be loaded
            assert 'litellm' not in sys.modules

            # Use _agent to avoid unused variable warning
            assert _agent is not None
        finally:
            sys.modules.update(removed)
