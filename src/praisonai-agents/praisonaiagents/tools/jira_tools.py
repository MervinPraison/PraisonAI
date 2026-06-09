"""JIRA Tools for PraisonAI Agents - Monitor and watch JIRA issues and projects"""
import os
import time
import logging
import re
from typing import Dict, List, Optional, Any
from .decorator import tool

logger = logging.getLogger(__name__)

def _get_jira_connection(
    url: str,
    username: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None
):
    """Create JIRA connection with proper authentication.
    
    Args:
        url: JIRA server URL
        username: Username or use JIRA_USERNAME env var
        token: API token or use JIRA_API_TOKEN env var  
        email: Email for cloud JIRA or use JIRA_EMAIL env var
    """
    try:
        from jira import JIRA
    except ImportError:
        raise ImportError(
            "JIRA library not installed. Install with: pip install jira"
        )
    
    # Get credentials from environment if not provided
    username = username or os.getenv('JIRA_USERNAME')
    token = token or os.getenv('JIRA_API_TOKEN')
    email = email or os.getenv('JIRA_EMAIL')
    
    if not url:
        raise ValueError("JIRA URL is required")
    
    # For cloud JIRA, use email + token
    if email and token:
        auth = (email, token)
    # For server JIRA, use username + token/password
    elif username and token:
        auth = (username, token)
    else:
        raise ValueError(
            "JIRA authentication required. Provide either:\n"
            "- email + token (for cloud JIRA)\n"
            "- username + token (for server JIRA)\n"
            "Or set environment variables: JIRA_EMAIL, JIRA_USERNAME, JIRA_API_TOKEN"
        )
    
    return JIRA(server=url, basic_auth=auth)

@tool
def jira_watch_issue(
    issue_key: str,
    url: str,
    since_timestamp: Optional[str] = None,
    username: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None
) -> str:
    """Check a specific JIRA issue for changes since a timestamp.
    
    Args:
        issue_key: JIRA issue key (e.g., "PROJ-123")
        url: JIRA server URL 
        since_timestamp: Check for changes since this ISO timestamp (optional)
        username: Username or use JIRA_USERNAME env var
        token: API token or use JIRA_API_TOKEN env var
        email: Email for cloud JIRA or use JIRA_EMAIL env var
    """
    try:
        jira = _get_jira_connection(url, username, token, email)
        
        # Get current issue state
        issue = jira.issue(issue_key, expand='changelog')
        current_updated = issue.fields.updated
        current_status = issue.fields.status.name
        
        logger.info(f"Checking JIRA issue {issue_key} for changes")
        logger.info(f"Current status: {current_status}")
        logger.info(f"Last updated: {current_updated}")
        
        changes_detected = []
        
        # If no timestamp provided, just return current state
        if not since_timestamp:
            result = f"JIRA issue {issue_key} current state:\n"
            result += f"Status: {current_status}\n"
            result += f"Summary: {issue.fields.summary}\n"
            result += f"Assignee: {issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned'}\n"
            result += f"Priority: {issue.fields.priority.name if issue.fields.priority else 'None'}\n"
            result += f"Updated: {current_updated}\n"
            return result
        
        # Check if updated since timestamp
        if current_updated > since_timestamp:
            change_info = {
                'timestamp': current_updated,
                'status': current_status,
                'summary': issue.fields.summary,
                'assignee': issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned',
                'priority': issue.fields.priority.name if issue.fields.priority else 'None'
            }
            
            # Get recent changelog entries
            recent_changes = []
            if issue.changelog and issue.changelog.histories:
                for history in issue.changelog.histories[-3:]:  # Last 3 changes
                    if history.created > since_timestamp:
                        for item in history.items:
                            recent_changes.append({
                                'field': item.field,
                                'from': item.fromString,
                                'to': item.toString,
                                'author': history.author.displayName,
                                'created': history.created
                            })
            
            change_info['recent_changes'] = recent_changes
            changes_detected.append(change_info)
            
            logger.info(f"Change detected in {issue_key} at {current_updated}")
            
            # Check for recent comments
            comments = jira.comments(issue_key)
            comment_changes = []
            if comments:
                for comment in comments:
                    if comment.created > since_timestamp:
                        comment_changes.append({
                            'author': comment.author.displayName,
                            'body': comment.body[:500],  # First 500 chars
                            'created': comment.created
                        })
            
            # Add comment changes as separate entries if they exist
            if comment_changes:
                change_info['recent_comments'] = comment_changes
        
        if changes_detected:
            result = f"JIRA issue {issue_key} - changes detected since {since_timestamp}:\n"
            for i, change in enumerate(changes_detected, 1):
                result += f"\n--- Change {i} at {change['timestamp']} ---\n"
                result += f"Status: {change['status']}\n"
                result += f"Assignee: {change['assignee']}\n"
                result += f"Priority: {change['priority']}\n"
                
                if change.get('recent_changes'):
                    result += "Recent field changes:\n"
                    for rc in change['recent_changes']:
                        result += f"  - {rc['field']}: '{rc['from']}' → '{rc['to']}' by {rc['author']}\n"
                
                if change.get('recent_comments'):
                    result += "Recent comments:\n"
                    for comment in change['recent_comments']:
                        result += f"  - {comment['author']} ({comment['created']}): {comment['body'][:200]}...\n"
            
            return result
        else:
            return f"No changes detected in JIRA issue {issue_key} since {since_timestamp}"
            
    except Exception as e:
        logger.error(f"Failed to watch JIRA issue: {e}")
        return f"Error watching JIRA issue {issue_key}: {e}"

def _validate_project_key(project_key: str) -> bool:
    """Validate JIRA project key to prevent injection.
    
    Args:
        project_key: Project key to validate
        
    Returns:
        True if valid, raises ValueError if invalid
    """
    # JIRA project keys must be uppercase letters, numbers, and underscores
    # and start with a letter
    if not re.match(r'^[A-Z][A-Z0-9_]*$', project_key):
        raise ValueError(f"Invalid project key format: {project_key}. Must start with letter and contain only uppercase letters, numbers, and underscores.")
    return True

@tool  
def jira_watch_project(
    project_key: str,
    url: str,
    since_timestamp: Optional[str] = None,
    username: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None
) -> str:
    """Check a JIRA project for new issues and updates since a timestamp.
    
    Args:
        project_key: JIRA project key (e.g., "PROJ")
        url: JIRA server URL
        since_timestamp: Check for changes since this ISO timestamp (optional)
        username: Username or use JIRA_USERNAME env var
        token: API token or use JIRA_API_TOKEN env var
        email: Email for cloud JIRA or use JIRA_EMAIL env var
    """
    try:
        # Validate project key to prevent JQL injection
        _validate_project_key(project_key)
        
        jira = _get_jira_connection(url, username, token, email)
        
        logger.info(f"Checking JIRA project {project_key} for changes")
        
        project_changes = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'new_issues': [],
            'updated_issues': []
        }
        
        # If no timestamp provided, return recent activity
        if not since_timestamp:
            recent_jql = f'project = {project_key} ORDER BY updated DESC'
            recent_issues = jira.search_issues(recent_jql, maxResults=20)
            
            result = f"JIRA project {project_key} recent activity ({len(recent_issues)} issues):\n"
            for issue in recent_issues[:10]:  # Show top 10
                result += f"  {issue.key}: {issue.fields.summary[:60]}...\n"
                result += f"    Status: {issue.fields.status.name}, Updated: {issue.fields.updated}\n"
            return result
        
        # Check for new issues since timestamp
        new_jql = f'project = {project_key} AND created >= "{since_timestamp}" ORDER BY created DESC'
        new_issues = jira.search_issues(new_jql, maxResults=50)
        
        for issue in new_issues:
            project_changes['new_issues'].append({
                'key': issue.key,
                'summary': issue.fields.summary,
                'status': issue.fields.status.name,
                'assignee': issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned',
                'creator': issue.fields.creator.displayName,
                'created': issue.fields.created
            })
        
        # Check for updated issues since timestamp
        updated_jql = f'project = {project_key} AND updated >= "{since_timestamp}" AND created < "{since_timestamp}" ORDER BY updated DESC'
        updated_issues = jira.search_issues(updated_jql, maxResults=50)
        
        for issue in updated_issues:
            project_changes['updated_issues'].append({
                'key': issue.key,
                'summary': issue.fields.summary,
                'status': issue.fields.status.name,
                'assignee': issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned',
                'updated': issue.fields.updated
            })
        
        if project_changes['new_issues'] or project_changes['updated_issues']:
            result = f"JIRA project {project_key} - changes detected since {since_timestamp}:\n"
            result += f"\n--- Activity at {project_changes['timestamp']} ---\n"
            
            if project_changes['new_issues']:
                result += f"New issues ({len(project_changes['new_issues'])}):\n"
                for issue in project_changes['new_issues']:
                    result += f"  📝 {issue['key']}: {issue['summary'][:80]}...\n"
                    result += f"     Status: {issue['status']}, Assignee: {issue['assignee']}, Created: {issue['created']}\n"
            
            if project_changes['updated_issues']:
                result += f"Updated issues ({len(project_changes['updated_issues'])}):\n"
                for issue in project_changes['updated_issues']:
                    result += f"  🔄 {issue['key']}: {issue['summary'][:80]}...\n"
                    result += f"     Status: {issue['status']}, Updated: {issue['updated']}\n"
            
            return result
        else:
            return f"No changes detected in JIRA project {project_key} since {since_timestamp}"
            
    except Exception as e:
        logger.error(f"Failed to watch JIRA project: {e}")
        return f"Error watching JIRA project {project_key}: {e}"

@tool
def jira_get_issue_info(
    issue_key: str,
    url: str,
    username: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None
) -> str:
    """Get detailed information about a specific JIRA issue.
    
    Args:
        issue_key: JIRA issue key (e.g., "PROJ-123")
        url: JIRA server URL
        username: Username or use JIRA_USERNAME env var
        token: API token or use JIRA_API_TOKEN env var
        email: Email for cloud JIRA or use JIRA_EMAIL env var
    """
    try:
        jira = _get_jira_connection(url, username, token, email)
        issue = jira.issue(issue_key, expand='changelog,comments')
        
        result = f"JIRA Issue: {issue.key}\n"
        result += f"Summary: {issue.fields.summary}\n"
        result += f"Status: {issue.fields.status.name}\n"
        result += f"Priority: {issue.fields.priority.name if issue.fields.priority else 'None'}\n"
        result += f"Assignee: {issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned'}\n"
        result += f"Reporter: {issue.fields.reporter.displayName}\n"
        result += f"Created: {issue.fields.created}\n"
        result += f"Updated: {issue.fields.updated}\n"
        
        if issue.fields.description:
            result += f"Description: {issue.fields.description[:500]}...\n"
        
        # Recent comments
        comments = jira.comments(issue_key)
        if comments:
            result += f"\nRecent Comments ({len(comments[-3:])}):\n"
            for comment in comments[-3:]:
                result += f"  - {comment.author.displayName} ({comment.created}): {comment.body[:200]}...\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get JIRA issue info: {e}")
        return f"Error getting JIRA issue {issue_key}: {e}"

@tool
def jira_search_issues(
    jql: str,
    url: str,
    max_results: int = 20,
    username: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None
) -> str:
    """Search JIRA issues using JQL (JIRA Query Language).
    
    Args:
        jql: JQL query string (e.g., "project = PROJ AND status = Open")
        url: JIRA server URL
        max_results: Maximum number of results to return (default: 20)
        username: Username or use JIRA_USERNAME env var
        token: API token or use JIRA_API_TOKEN env var
        email: Email for cloud JIRA or use JIRA_EMAIL env var
    """
    try:
        jira = _get_jira_connection(url, username, token, email)
        issues = jira.search_issues(jql, maxResults=max_results)
        
        if not issues:
            return f"No issues found for JQL: {jql}"
        
        result = f"Found {len(issues)} issues for JQL: {jql}\n\n"
        
        for issue in issues:
            result += f"{issue.key}: {issue.fields.summary}\n"
            result += f"  Status: {issue.fields.status.name}\n"
            result += f"  Assignee: {issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned'}\n"
            result += f"  Updated: {issue.fields.updated}\n\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to search JIRA issues: {e}")
        return f"Error searching JIRA issues: {e}"

# Module-level callable for tools collection
def jira_tools():
    """Return all JIRA tools as a collection."""
    return [
        jira_watch_issue,
        jira_watch_project,
        jira_get_issue_info,
        jira_search_issues
    ]