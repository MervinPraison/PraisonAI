"""Unit tests for CLI backend flag and backends list command."""

import pytest
import sys
from unittest.mock import patch, MagicMock
from io import StringIO

def test_cli_backend_flag_choices():
    """Test that CLI backend flag includes registered backend choices."""
    from praisonai.cli.main import PraisonAI
    
    with patch('praisonai.cli_backends.list_cli_backends', return_value=['claude-code', 'test-backend']):
        praison = PraisonAI()
        
        # Parse help to check choices are included
        with patch('sys.argv', ['praisonai', '--help']):
            with pytest.raises(SystemExit):
                with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                    praison.parse_args()
                    help_output = mock_stdout.getvalue()
                    assert '--cli-backend' in help_output

def test_cli_backend_flag_with_prompt():
    """Test CLI backend flag with direct prompt."""
    from praisonai.cli.main import PraisonAI
    
    with patch('praisonai.cli_backends.list_cli_backends', return_value=['claude-code']):
        with patch('praisonai.cli_backends.resolve_cli_backend') as mock_resolve:
            mock_backend = MagicMock()
            mock_resolve.return_value = mock_backend
            
            praison = PraisonAI()
            
            # Mock agent creation and execution
            with patch.object(praison, 'handle_direct_prompt') as mock_handler:
                mock_handler.return_value = "test result"
                
                # Test with CLI backend flag
                with patch('sys.argv', ['praisonai', '--cli-backend', 'claude-code', 'Hello']):
                    args = praison.parse_args()
                    assert args.cli_backend == 'claude-code'
                    assert args.command == 'Hello'

def test_mutual_exclusion_cli_backend_external_agent():
    """Test mutual exclusion between --cli-backend and --external-agent."""
    from praisonai.cli.main import PraisonAI
    
    with patch('praisonai.cli_backends.list_cli_backends', return_value=['claude-code']):
        praison = PraisonAI()
        
        # Test that both flags trigger error
        with patch('sys.argv', ['praisonai', '--cli-backend', 'claude-code', '--external-agent', 'claude', 'Hello']):
            args = praison.parse_args()
            args.cli_backend = 'claude-code'
            args.external_agent = 'claude'
            
            # Mock the main method to check for mutual exclusion
            with patch('sys.exit') as mock_exit:
                with patch('builtins.print') as mock_print:
                    praison.args = args
                    praison.main()
                    
                    # Should exit with error
                    mock_exit.assert_called_once_with(1)
                    mock_print.assert_called_with("[red]Error: --cli-backend and --external-agent are mutually exclusive[/red]")

def test_backends_list_command():
    """Test 'praisonai backends list' command."""
    from praisonai.cli.main import PraisonAI
    
    with patch('praisonai.cli_backends.list_cli_backends', return_value=['claude-code', 'test-backend']):
        praison = PraisonAI()
        
        with patch('sys.argv', ['praisonai', 'backends', 'list']):
            args = praison.parse_args()
            assert args.command == 'backends'
            
            # Mock main method execution
            with patch('builtins.print') as mock_print:
                result = praison.main()
                
                # Should print each backend
                expected_calls = [
                    (('claude-code',),),
                    (('test-backend',),)
                ]
                mock_print.assert_has_calls(expected_calls)
                assert result == ""

def test_backends_command_no_subcommand():
    """Test 'praisonai backends' command without subcommand (defaults to list)."""
    from praisonai.cli.main import PraisonAI
    
    with patch('praisonai.cli_backends.list_cli_backends', return_value=['claude-code']):
        praison = PraisonAI()
        
        with patch('sys.argv', ['praisonai', 'backends']):
            args = praison.parse_args()
            assert args.command == 'backends'
            
            # Mock main method execution
            with patch('builtins.print') as mock_print:
                result = praison.main()
                
                # Should print backend
                mock_print.assert_called_with('claude-code')
                assert result == ""

def test_backends_command_unknown_subcommand():
    """Test 'praisonai backends unknown' with invalid subcommand."""
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    with patch('sys.argv', ['praisonai', 'backends', 'unknown']):
        args = praison.parse_args()
        assert args.command == 'backends'
        
        # Mock main method execution
        with patch('builtins.print') as mock_print:
            result = praison.main()
            
            # Should print error
            expected_calls = [
                (('[red]Unknown backends subcommand: unknown[/red]',),),
                (('Available subcommands: list',),)
            ]
            mock_print.assert_has_calls(expected_calls)
            assert result is None

def test_backends_command_import_error():
    """Test backends command when CLI backends not available."""
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    with patch('sys.argv', ['praisonai', 'backends', 'list']):
        args = praison.parse_args()
        assert args.command == 'backends'
        
        # Mock import error
        with patch('builtins.__import__', side_effect=ImportError("No module")):
            with patch('builtins.print') as mock_print:
                result = praison.main()
                
                # Should print error
                mock_print.assert_called_with("[red]CLI backends not available[/red]")
                assert result is None

def test_cli_backend_flag_no_choices_when_import_fails():
    """Test CLI backend flag when list_cli_backends import fails."""
    from praisonai.cli.main import PraisonAI
    
    with patch('praisonai.cli_backends.list_cli_backends', side_effect=ImportError("Not available")):
        praison = PraisonAI()
        
        # Should not crash during argument parsing
        with patch('sys.argv', ['praisonai', '--help']):
            with pytest.raises(SystemExit):
                with patch('sys.stdout', new_callable=StringIO):
                    praison.parse_args()