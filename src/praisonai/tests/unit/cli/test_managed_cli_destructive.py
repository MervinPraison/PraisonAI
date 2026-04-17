"""Unit tests for managed CLI destructive operations (delete commands)."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner

from praisonai.cli.commands.managed import app, sessions_app, agents_app, envs_app


class TestManagedCLIDestructive:
    """Test suite for managed CLI delete operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.mock_client = Mock()

    @patch('praisonai.cli.commands.managed._get_client')
    def test_sessions_delete_with_confirmation(self, mock_get_client):
        """Test sessions delete with user confirmation."""
        mock_get_client.return_value = self.mock_client
        
        # Test with user confirmation (yes)
        result = self.runner.invoke(
            sessions_app, 
            ['delete', 'sesn_01test123'],
            input='y\n'
        )
        
        assert result.exit_code == 0
        assert "Delete session sesn_01test123?" in result.stdout
        assert "Deleted session: sesn_01test123" in result.stdout
        self.mock_client.beta.sessions.delete.assert_called_once_with('sesn_01test123')

    @patch('praisonai.cli.commands.managed._get_client')
    def test_sessions_delete_with_no_confirmation(self, mock_get_client):
        """Test sessions delete with user refusing confirmation."""
        mock_get_client.return_value = self.mock_client
        
        # Test with user confirmation (no)
        result = self.runner.invoke(
            sessions_app, 
            ['delete', 'sesn_01test123'],
            input='n\n'
        )
        
        assert result.exit_code == 0
        assert "Delete session sesn_01test123?" in result.stdout
        assert "Cancelled." in result.stdout
        self.mock_client.beta.sessions.delete.assert_not_called()

    @patch('praisonai.cli.commands.managed._get_client')
    def test_sessions_delete_with_yes_flag(self, mock_get_client):
        """Test sessions delete with --yes flag to skip confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            sessions_app, 
            ['delete', 'sesn_01test123', '--yes']
        )
        
        assert result.exit_code == 0
        assert "Delete session sesn_01test123?" not in result.stdout
        assert "Deleted session: sesn_01test123" in result.stdout
        self.mock_client.beta.sessions.delete.assert_called_once_with('sesn_01test123')

    @patch('praisonai.cli.commands.managed._get_client')
    def test_sessions_delete_with_y_flag(self, mock_get_client):
        """Test sessions delete with -y flag to skip confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            sessions_app, 
            ['delete', 'sesn_01test123', '-y']
        )
        
        assert result.exit_code == 0
        assert "Delete session sesn_01test123?" not in result.stdout
        assert "Deleted session: sesn_01test123" in result.stdout
        self.mock_client.beta.sessions.delete.assert_called_once_with('sesn_01test123')

    @patch('praisonai.cli.commands.managed._get_client')
    def test_sessions_delete_error_handling(self, mock_get_client):
        """Test sessions delete error handling."""
        mock_get_client.return_value = self.mock_client
        self.mock_client.beta.sessions.delete.side_effect = Exception("API Error")
        
        result = self.runner.invoke(
            sessions_app, 
            ['delete', 'sesn_01test123', '--yes']
        )
        
        assert result.exit_code == 1
        assert "Error deleting session: API Error" in result.stdout

    @patch('praisonai.cli.commands.managed._get_client')
    def test_agents_delete_with_confirmation(self, mock_get_client):
        """Test agents delete with user confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            agents_app, 
            ['delete', 'agent_01test123'],
            input='y\n'
        )
        
        assert result.exit_code == 0
        assert "Delete agent agent_01test123?" in result.stdout
        assert "Deleted agent: agent_01test123" in result.stdout
        self.mock_client.beta.agents.delete.assert_called_once_with('agent_01test123')

    @patch('praisonai.cli.commands.managed._get_client')
    def test_agents_delete_with_no_confirmation(self, mock_get_client):
        """Test agents delete with user refusing confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            agents_app, 
            ['delete', 'agent_01test123'],
            input='n\n'
        )
        
        assert result.exit_code == 0
        assert "Delete agent agent_01test123?" in result.stdout
        assert "Cancelled." in result.stdout
        self.mock_client.beta.agents.delete.assert_not_called()

    @patch('praisonai.cli.commands.managed._get_client')
    def test_agents_delete_with_yes_flag(self, mock_get_client):
        """Test agents delete with --yes flag to skip confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            agents_app, 
            ['delete', 'agent_01test123', '--yes']
        )
        
        assert result.exit_code == 0
        assert "Delete agent agent_01test123?" not in result.stdout
        assert "Deleted agent: agent_01test123" in result.stdout
        self.mock_client.beta.agents.delete.assert_called_once_with('agent_01test123')

    @patch('praisonai.cli.commands.managed._get_client')
    def test_agents_delete_error_handling(self, mock_get_client):
        """Test agents delete error handling."""
        mock_get_client.return_value = self.mock_client
        self.mock_client.beta.agents.delete.side_effect = Exception("API Error")
        
        result = self.runner.invoke(
            agents_app, 
            ['delete', 'agent_01test123', '--yes']
        )
        
        assert result.exit_code == 1
        assert "Error deleting agent: API Error" in result.stdout

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_packages(self, mock_get_client):
        """Test environments update with packages."""
        mock_get_client.return_value = self.mock_client
        mock_updated_env = Mock()
        mock_updated_env.id = 'env_01test123'
        self.mock_client.beta.environments.update.return_value = mock_updated_env
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123', '--packages', 'pandas,numpy,requests']
        )
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        self.mock_client.beta.environments.update.assert_called_once_with(
            'env_01test123',
            packages={"pip": ["pandas", "numpy", "requests"]}
        )

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_networking(self, mock_get_client):
        """Test environments update with networking."""
        mock_get_client.return_value = self.mock_client
        mock_updated_env = Mock()
        mock_updated_env.id = 'env_01test123'
        self.mock_client.beta.environments.update.return_value = mock_updated_env
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123', '--networking', 'limited']
        )
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        self.mock_client.beta.environments.update.assert_called_once_with(
            'env_01test123',
            networking={"type": "limited"}
        )

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_both_packages_and_networking(self, mock_get_client):
        """Test environments update with both packages and networking."""
        mock_get_client.return_value = self.mock_client
        mock_updated_env = Mock()
        mock_updated_env.id = 'env_01test123'
        self.mock_client.beta.environments.update.return_value = mock_updated_env
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123', '--packages', 'pandas,numpy', '--networking', 'unrestricted']
        )
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        self.mock_client.beta.environments.update.assert_called_once_with(
            'env_01test123',
            packages={"pip": ["pandas", "numpy"]},
            networking={"type": "unrestricted"}
        )

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_invalid_networking(self, mock_get_client):
        """Test environments update with invalid networking configuration."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123', '--networking', 'invalid']
        )
        
        assert result.exit_code == 1
        assert "Error: networking must be 'limited' or 'unrestricted'" in result.stdout
        self.mock_client.beta.environments.update.assert_not_called()

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_no_options(self, mock_get_client):
        """Test environments update with no options provided."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123']
        )
        
        assert result.exit_code == 0
        assert "Nothing to update. Pass --packages or --networking." in result.stdout
        self.mock_client.beta.environments.update.assert_not_called()

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_error_handling(self, mock_get_client):
        """Test environments update error handling."""
        mock_get_client.return_value = self.mock_client
        self.mock_client.beta.environments.update.side_effect = Exception("API Error")
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123', '--packages', 'pandas']
        )
        
        assert result.exit_code == 1
        assert "Error updating environment: API Error" in result.stdout

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_delete_with_confirmation(self, mock_get_client):
        """Test environments delete with user confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            envs_app, 
            ['delete', 'env_01test123'],
            input='y\n'
        )
        
        assert result.exit_code == 0
        assert "Delete environment env_01test123?" in result.stdout
        assert "Deleted environment: env_01test123" in result.stdout
        self.mock_client.beta.environments.delete.assert_called_once_with('env_01test123')

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_delete_with_no_confirmation(self, mock_get_client):
        """Test environments delete with user refusing confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            envs_app, 
            ['delete', 'env_01test123'],
            input='n\n'
        )
        
        assert result.exit_code == 0
        assert "Delete environment env_01test123?" in result.stdout
        assert "Cancelled." in result.stdout
        self.mock_client.beta.environments.delete.assert_not_called()

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_delete_with_yes_flag(self, mock_get_client):
        """Test environments delete with --yes flag to skip confirmation."""
        mock_get_client.return_value = self.mock_client
        
        result = self.runner.invoke(
            envs_app, 
            ['delete', 'env_01test123', '--yes']
        )
        
        assert result.exit_code == 0
        assert "Delete environment env_01test123?" not in result.stdout
        assert "Deleted environment: env_01test123" in result.stdout
        self.mock_client.beta.environments.delete.assert_called_once_with('env_01test123')

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_delete_error_handling(self, mock_get_client):
        """Test environments delete error handling."""
        mock_get_client.return_value = self.mock_client
        self.mock_client.beta.environments.delete.side_effect = Exception("API Error")
        
        result = self.runner.invoke(
            envs_app, 
            ['delete', 'env_01test123', '--yes']
        )
        
        assert result.exit_code == 1
        assert "Error deleting environment: API Error" in result.stdout

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_packages_whitespace_handling(self, mock_get_client):
        """Test environments update properly handles whitespace in packages list."""
        mock_get_client.return_value = self.mock_client
        mock_updated_env = Mock()
        mock_updated_env.id = 'env_01test123'
        self.mock_client.beta.environments.update.return_value = mock_updated_env
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123', '--packages', ' pandas , numpy , requests ']
        )
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        self.mock_client.beta.environments.update.assert_called_once_with(
            'env_01test123',
            packages={"pip": ["pandas", "numpy", "requests"]}
        )

    @patch('praisonai.cli.commands.managed._get_client')
    def test_envs_update_networking_case_insensitive(self, mock_get_client):
        """Test environments update handles networking case insensitively."""
        mock_get_client.return_value = self.mock_client
        mock_updated_env = Mock()
        mock_updated_env.id = 'env_01test123'
        self.mock_client.beta.environments.update.return_value = mock_updated_env
        
        result = self.runner.invoke(
            envs_app, 
            ['update', 'env_01test123', '--networking', 'LIMITED']
        )
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        self.mock_client.beta.environments.update.assert_called_once_with(
            'env_01test123',
            networking={"type": "limited"}
        )