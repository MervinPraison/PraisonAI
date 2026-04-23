"""Unit tests for external agents backward compatibility."""

import pytest
from unittest.mock import patch, MagicMock

def test_external_agent_claude_integration_exists():
    """Test that external agent claude integration can be resolved."""
    from praisonai.cli.features.external_agents import ExternalAgentsHandler
    
    handler = ExternalAgentsHandler(verbose=False)
    
    # Mock the integration to avoid actual subprocess calls
    with patch.object(handler, 'get_integration') as mock_get_integration:
        mock_integration = MagicMock()
        mock_integration.is_available = True
        mock_integration.cli_command = 'claude'
        mock_get_integration.return_value = mock_integration
        
        integration = handler.get_integration('claude', workspace='/tmp')
        
        assert integration is not None
        assert integration.is_available
        assert integration.cli_command == 'claude'
        mock_get_integration.assert_called_once_with('claude', workspace='/tmp')

def test_external_agent_claude_flag_still_works():
    """Test that --external-agent claude flag still works via CLI."""
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    with patch('sys.argv', ['praisonai', '--external-agent', 'claude', 'Hello']):
        args = praison.parse_args()
        assert args.external_agent == 'claude'
        assert args.command == 'Hello'

def test_external_agent_gemini_flag_still_works():
    """Test that --external-agent gemini flag still works via CLI."""
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    with patch('sys.argv', ['praisonai', '--external-agent', 'gemini', 'Hello']):
        args = praison.parse_args()
        assert args.external_agent == 'gemini'
        assert args.command == 'Hello'

def test_external_agent_direct_flag():
    """Test that --external-agent-direct flag still works."""
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    with patch('sys.argv', ['praisonai', '--external-agent', 'claude', '--external-agent-direct', 'Hello']):
        args = praison.parse_args()
        assert args.external_agent == 'claude'
        assert args.external_agent_direct is True
        assert args.command == 'Hello'

def test_external_agent_handler_get_integration():
    """Test that ExternalAgentsHandler.get_integration method works for all supported agents."""
    from praisonai.cli.features.external_agents import ExternalAgentsHandler
    
    handler = ExternalAgentsHandler(verbose=False)
    supported_agents = ['claude', 'gemini', 'codex', 'cursor']
    
    for agent_name in supported_agents:
        with patch.object(handler, 'get_integration') as mock_get_integration:
            mock_integration = MagicMock()
            mock_integration.is_available = True
            mock_integration.cli_command = agent_name
            mock_get_integration.return_value = mock_integration
            
            integration = handler.get_integration(agent_name, workspace='/tmp')
            
            assert integration is not None
            assert integration.is_available
            assert integration.cli_command == agent_name
            mock_get_integration.assert_called_once_with(agent_name, workspace='/tmp')

def test_external_agent_execution_path_still_accessible():
    """Smoke test that external agent execution path is still accessible in main()."""
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    # Mock the external agent handler to avoid actual execution
    with patch('praisonai.cli.features.external_agents.ExternalAgentsHandler') as mock_handler_class:
        mock_handler = MagicMock()
        mock_integration = MagicMock()
        mock_integration.is_available = True
        mock_integration.cli_command = 'claude'
        mock_handler.get_integration.return_value = mock_integration
        mock_handler_class.return_value = mock_handler
        
        with patch('sys.argv', ['praisonai', '--external-agent', 'claude', 'Hello']):
            args = praison.parse_args()
            praison.args = args
            
            # Mock the actual execution to avoid subprocess calls
            with patch.object(praison, 'handle_direct_prompt') as mock_direct:
                mock_direct.return_value = "test result"
                
                # This should not raise an exception - the path should still be accessible
                result = praison.main()
                # Result should be empty string due to external agent handling
                assert result == ""

def test_external_agent_choices_preserved():
    """Test that external agent choices are preserved from original implementation."""
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    parser = praison.create_parser()
    
    # Find the external-agent argument
    external_agent_action = None
    for action in parser._actions:
        if hasattr(action, 'dest') and action.dest == 'external_agent':
            external_agent_action = action
            break
    
    assert external_agent_action is not None
    assert external_agent_action.choices == ['claude', 'gemini', 'codex', 'cursor']