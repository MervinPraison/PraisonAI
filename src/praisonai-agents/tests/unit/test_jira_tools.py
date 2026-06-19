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
    
    @patch('jira.JIRA')
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
    
    @patch('jira.JIRA')
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
    
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_watch_issue_current_state(self, mock_connection):
        """Test getting current state of an issue."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        mock_issue = Mock()
        mock_issue.fields.updated = "2024-01-01T10:00:00"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.summary = "Test issue"
        mock_issue.fields.assignee.displayName = "John Doe"
        mock_issue.fields.priority.name = "High"
        
        mock_jira.issue.return_value = mock_issue
        
        result = jira_watch_issue(
            issue_key="PROJ-123",
            url="https://test.atlassian.net",
            email="test@example.com", 
            token="test_token"
        )
        
        assert "current state" in result
        assert "PROJ-123" in result
        assert "Open" in result
        assert "John Doe" in result
    
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')  
    def test_watch_issue_with_changes(self, mock_connection):
        """Test watching an issue with changes detected since timestamp."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        # Mock updated issue
        mock_issue = Mock()
        mock_issue.fields.updated = "2024-01-01T11:00:00"  # After timestamp
        mock_issue.fields.status.name = "In Progress"
        mock_issue.fields.summary = "Test issue"
        mock_issue.fields.assignee.displayName = "Jane Smith"
        mock_issue.fields.priority.name = "High"
        mock_issue.changelog = Mock()
        mock_issue.changelog.histories = []
        
        mock_jira.issue.return_value = mock_issue
        mock_jira.comments.return_value = []
        
        result = jira_watch_issue(
            issue_key="PROJ-123", 
            url="https://test.atlassian.net",
            since_timestamp="2024-01-01T10:00:00",
            email="test@example.com",
            token="test_token"
        )
        
        assert "changes detected" in result
        assert "In Progress" in result
        assert "Jane Smith" in result


class TestJIRAWatchProject:
    """Test JIRA project watching functionality."""
    
    @patch('praisonaiagents.tools.jira_tools._get_jira_connection')
    def test_watch_project_recent_activity(self, mock_connection):
        """Test getting recent activity from a project."""
        mock_jira = Mock()
        mock_connection.return_value = mock_jira
        
        # Mock recent issues
        mock_issue = Mock()
        mock_issue.key = "PROJ-123"
        mock_issue.fields.summary = "Test issue"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.updated = "2024-01-01T10:00:00"
        
        mock_jira.search_issues.return_value = [mock_issue]
        
        result = jira_watch_project(
            project_key="PROJ",
            url="https://test.atlassian.net",
            email="test@example.com",
            token="test_token"
        )
        
        assert "recent activity" in result
        assert "PROJ" in result
        assert "PROJ-123" in result


class TestJIRAValidation:
    """Test JIRA input validation."""
    
    def test_validate_project_key_valid(self):
        """Test valid project key validation."""
        from praisonaiagents.tools.jira_tools import _validate_project_key
        
        # Valid keys
        assert _validate_project_key("PROJ")
        assert _validate_project_key("MY_PROJECT")
        assert _validate_project_key("ABC123")
        assert _validate_project_key("A")
    
    def test_validate_project_key_invalid(self):
        """Test invalid project key validation."""
        from praisonaiagents.tools.jira_tools import _validate_project_key
        
        # Invalid keys
        with pytest.raises(ValueError):
            _validate_project_key("proj")  # lowercase
        with pytest.raises(ValueError):
            _validate_project_key("123")  # starts with number
        with pytest.raises(ValueError):
            _validate_project_key("PROJ-123")  # contains dash
        with pytest.raises(ValueError):
            _validate_project_key("PROJ OR 1=1")  # injection attempt


def test_jira_tools_import():
    """Test that JIRA tools can be imported from the tools package."""
    from praisonaiagents.tools import (
        jira_watch_issue,
        jira_watch_project, 
        jira_get_issue_info,
        jira_search_issues
    )
    from praisonaiagents.tools.jira_tools import jira_tools
    
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


class TestTimestampParsing:
    """Test timestamp parsing utilities."""
    
    def test_parse_timestamp_valid_formats(self):
        """Test parsing various valid ISO 8601 formats."""
        from praisonaiagents.tools.jira_tools import _parse_timestamp
        
        # Test ISO format with Z
        dt = _parse_timestamp("2024-01-01T10:00:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 10
        
        # Test ISO format with +00:00
        dt2 = _parse_timestamp("2024-01-01T10:00:00+00:00")
        assert dt2 is not None
        
        # Test ISO format with +0000 (JIRA format)
        dt3 = _parse_timestamp("2024-01-01T10:00:00.000+0000")
        assert dt3 is not None
        
        # Test ISO format with timezone offset
        dt4 = _parse_timestamp("2024-01-01T10:00:00-05:00")
        assert dt4 is not None
    
    def test_parse_timestamp_invalid(self):
        """Test parsing invalid timestamps."""
        from praisonaiagents.tools.jira_tools import _parse_timestamp
        
        with pytest.raises(ValueError):
            _parse_timestamp("invalid-date")
        
        with pytest.raises(ValueError):
            _parse_timestamp("")
        
        with pytest.raises(ValueError):
            _parse_timestamp("2024-13-40")  # Invalid date values
    
    def test_validate_timestamp(self):
        """Test timestamp validation for JQL injection prevention."""
        from praisonaiagents.tools.jira_tools import _validate_timestamp
        
        # Valid timestamps should not raise
        _validate_timestamp("2024-01-01T10:00:00Z")
        _validate_timestamp("2024-01-01T10:00:00+00:00")
        
        # Invalid timestamps should raise ValueError
        with pytest.raises(ValueError):
            _validate_timestamp("2024-01-01\" OR project != \"\"")
        
        with pytest.raises(ValueError):
            _validate_timestamp("'; DROP TABLE issues; --")