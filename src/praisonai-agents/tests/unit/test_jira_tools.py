"""Unit tests for JIRA tools."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from praisonaiagents.tools.jira_tools import (
    jira_watch_issue,
    jira_watch_project, 
    jira_get_issue_info,
    jira_search_issues,
    _get_jira_connection
)


class TestJIRAConnection:
    """Test JIRA connection utility."""
    
    @patch('praisonaiagents.tools.jira_tools.JIRA')
    def test_connection_with_email_token(self, mock_jira):
        """Test JIRA connection with email and token."""
        _get_jira_connection(
            url="https://test.atlassian.net",
            email="test@example.com", 
            token="test_token"
        )
        mock_jira.assert_called_once_with(
            server="https://test.atlassian.net",
            basic_auth=("test@example.com", "test_token")
        )
    
    @patch('praisonaiagents.tools.jira_tools.JIRA')
    def test_connection_with_username_token(self, mock_jira):
        """Test JIRA connection with username and token."""
        _get_jira_connection(
            url="https://test.atlassian.net",
            username="test_user",
            token="test_token"
        )
        mock_jira.assert_called_once_with(
            server="https://test.atlassian.net", 
            basic_auth=("test_user", "test_token")
        )
    
    def test_connection_missing_auth(self):
        """Test JIRA connection fails with missing auth."""
        with pytest.raises(ValueError, match="JIRA authentication required"):
            _get_jira_connection(url="https://test.atlassian.net")
    
    def test_connection_missing_url(self):
        """Test JIRA connection fails with missing URL."""
        with pytest.raises(ValueError, match="JIRA URL is required"):
            _get_jira_connection(url="", email="test@example.com", token="token")


class TestJIRAGetIssueInfo:
    """Test getting JIRA issue information."""
    
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_get_issue_info_success(self, mock_connection):
        """Test successfully getting issue info."""
        # Mock JIRA connection and issue
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        mock_issue = Mock()
        mock_issue.key = "PROJ-123"
        mock_issue.fields.summary = "Test issue"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee.displayName = "John Doe"
        mock_issue.fields.reporter.displayName = "Jane Smith"
        mock_issue.fields.created = "2024-01-01T10:00:00"
        mock_issue.fields.updated = "2024-01-02T15:30:00"
        mock_issue.fields.description = "Test description"
        
        mock_jira.issue.return_value = mock_issue
        mock_jira.comments.return_value = []
        
        result = jira_get_issue_info(
            issue_key="PROJ-123",
            url="https://test.atlassian.net",
            email="test@example.com",
            token="test_token"
        )
        
        assert "PROJ-123" in result
        assert "Test issue" in result
        assert "Open" in result
        assert "High" in result
        assert "John Doe" in result
    
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_get_issue_info_error(self, mock_connection):
        """Test error handling in get issue info."""
        mock_connection.side_effect = Exception("Connection failed")
        
        result = jira_get_issue_info(
            issue_key="PROJ-123",
            url="https://test.atlassian.net", 
            email="test@example.com",
            token="test_token"
        )
        
        assert "Error getting JIRA issue PROJ-123" in result


class TestJIRASearchIssues:
    """Test searching JIRA issues."""
    
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_search_issues_success(self, mock_connection):
        """Test successfully searching issues."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        # Mock search results
        mock_issue1 = Mock()
        mock_issue1.key = "PROJ-123"
        mock_issue1.fields.summary = "First issue"
        mock_issue1.fields.status.name = "Open"
        mock_issue1.fields.assignee.displayName = "John Doe"
        mock_issue1.fields.updated = "2024-01-01T10:00:00"
        
        mock_issue2 = Mock()
        mock_issue2.key = "PROJ-124"
        mock_issue2.fields.summary = "Second issue"
        mock_issue2.fields.status.name = "Closed"
        mock_issue2.fields.assignee = None
        mock_issue2.fields.updated = "2024-01-02T15:30:00"
        
        mock_jira.search_issues.return_value = [mock_issue1, mock_issue2]
        
        result = jira_search_issues(
            jql="project = PROJ",
            url="https://test.atlassian.net",
            email="test@example.com",
            token="test_token"
        )
        
        assert "Found 2 issues" in result
        assert "PROJ-123" in result
        assert "PROJ-124" in result
        assert "First issue" in result
        assert "Second issue" in result
        assert "Unassigned" in result
    
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_search_issues_no_results(self, mock_connection):
        """Test search with no results."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        mock_jira.search_issues.return_value = []
        
        result = jira_search_issues(
            jql="project = NONEXISTENT",
            url="https://test.atlassian.net",
            email="test@example.com",
            token="test_token"
        )
        
        assert "No issues found" in result


class TestJIRAWatchIssue:
    """Test JIRA issue watching functionality."""
    
    @patch('praisonaiagents.tools.jira_tools.time.sleep')
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_watch_issue_no_changes(self, mock_connection, mock_sleep):
        """Test watching an issue with no changes."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        mock_issue = Mock()
        mock_issue.fields.updated = "2024-01-01T10:00:00"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.summary = "Test issue"
        mock_issue.fields.assignee.displayName = "John Doe"
        mock_issue.fields.priority.name = "High"
        mock_issue.changelog = None
        
        mock_jira.issue.return_value = mock_issue
        mock_jira.comments.return_value = []
        
        result = jira_watch_issue(
            issue_key="PROJ-123",
            url="https://test.atlassian.net",
            check_interval=1,
            max_checks=1,
            email="test@example.com", 
            token="test_token"
        )
        
        assert "no changes detected" in result
        assert "PROJ-123" in result
    
    @patch('praisonaiagents.tools.jira_tools.time.sleep')
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')  
    def test_watch_issue_with_changes(self, mock_connection, mock_sleep):
        """Test watching an issue with changes detected."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        # First call - initial state
        mock_issue1 = Mock()
        mock_issue1.fields.updated = "2024-01-01T10:00:00"
        mock_issue1.fields.status.name = "Open"
        mock_issue1.fields.summary = "Test issue"
        mock_issue1.fields.assignee.displayName = "John Doe"
        mock_issue1.fields.priority.name = "High"
        mock_issue1.changelog = None
        
        # Second call - updated state
        mock_issue2 = Mock()
        mock_issue2.fields.updated = "2024-01-01T11:00:00"  # Changed
        mock_issue2.fields.status.name = "In Progress"  # Changed
        mock_issue2.fields.summary = "Test issue"
        mock_issue2.fields.assignee.displayName = "Jane Smith"  # Changed
        mock_issue2.fields.priority.name = "High"
        mock_issue2.changelog = Mock()
        mock_issue2.changelog.histories = []
        
        mock_jira.issue.side_effect = [mock_issue1, mock_issue2]
        mock_jira.comments.return_value = []
        
        result = jira_watch_issue(
            issue_key="PROJ-123", 
            url="https://test.atlassian.net",
            check_interval=1,
            max_checks=1,
            email="test@example.com",
            token="test_token"
        )
        
        assert "1 changes detected" in result
        assert "In Progress" in result
        assert "Jane Smith" in result


class TestJIRAWatchProject:
    """Test JIRA project watching functionality."""
    
    @patch('praisonaiagents.tools.jira_tools.time.sleep')
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_watch_project_no_changes(self, mock_connection, mock_sleep):
        """Test watching a project with no changes."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        # Mock initial and subsequent search results (same)
        mock_issue = Mock()
        mock_issue.key = "PROJ-123"
        mock_jira.search_issues.return_value = [mock_issue]
        
        result = jira_watch_project(
            project_key="PROJ",
            url="https://test.atlassian.net",
            check_interval=1,
            max_checks=1,
            email="test@example.com",
            token="test_token"
        )
        
        assert "no changes detected" in result
        assert "PROJ" in result


def test_jira_tools_import():
    """Test that JIRA tools can be imported from the tools package."""
    from praisonaiagents.tools import (
        jira_watch_issue,
        jira_watch_project, 
        jira_get_issue_info,
        jira_search_issues,
        jira_tools
    )
    
    # Verify functions exist
    assert callable(jira_watch_issue)
    assert callable(jira_watch_project)
    assert callable(jira_get_issue_info)  
    assert callable(jira_search_issues)
    assert callable(jira_tools)
    
    # Verify jira_tools returns a list of tools
    tools = jira_tools()
    assert isinstance(tools, list)
    assert len(tools) == 4