"""JIRA Tools for PraisonAI Agents - Monitor and watch JIRA issues and projects"""
import os
import time
import logging
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
    check_interval: int = 300,
    username: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    max_checks: int = 12
) -> str:
    """Watch a specific JIRA issue for changes and return updates.
    
    Args:
        issue_key: JIRA issue key (e.g., "PROJ-123")
        url: JIRA server URL 
        check_interval: Seconds between checks (default: 300 = 5 minutes)
        username: Username or use JIRA_USERNAME env var
        token: API token or use JIRA_API_TOKEN env var
        email: Email for cloud JIRA or use JIRA_EMAIL env var
        max_checks: Maximum number of checks to perform (default: 12 = 1 hour)
    """
    try:
        jira = _get_jira_connection(url, username, token, email)
        
        # Get initial issue state
        issue = jira.issue(issue_key, expand='changelog')
        initial_updated = issue.fields.updated
        initial_status = issue.fields.status.name
        
        logger.info(f"Starting to watch JIRA issue {issue_key}")
        logger.info(f"Initial status: {initial_status}")
        logger.info(f"Last updated: {initial_updated}")
        
        changes_detected = []
        
        for check in range(max_checks):
            time.sleep(check_interval)
            
            # Refresh issue data
            try:
                issue = jira.issue(issue_key, expand='changelog')
                current_updated = issue.fields.updated
                current_status = issue.fields.status.name
                
                # Check if issue was updated
                if current_updated != initial_updated:
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
                    initial_updated = current_updated
                
                # Check for comments
                comments = jira.comments(issue_key)
                if comments:
                    latest_comment = comments[-1]
                    change_info = changes_detected[-1] if changes_detected else {}
                    change_info['latest_comment'] = {
                        'author': latest_comment.author.displayName,
                        'body': latest_comment.body[:500],  # First 500 chars
                        'created': latest_comment.created
                    }
                    
            except Exception as e:
                logger.error(f"Error checking issue {issue_key}: {e}")
                return f"Error monitoring issue {issue_key}: {e}"
        
        if changes_detected:
            result = f"Watched JIRA issue {issue_key} - {len(changes_detected)} changes detected:\n"
            for i, change in enumerate(changes_detected, 1):
                result += f"\n--- Change {i} at {change['timestamp']} ---\n"
                result += f"Status: {change['status']}\n"
                result += f"Assignee: {change['assignee']}\n"
                result += f"Priority: {change['priority']}\n"
                
                if change.get('recent_changes'):
                    result += "Recent field changes:\n"
                    for rc in change['recent_changes']:
                        result += f"  - {rc['field']}: '{rc['from']}' → '{rc['to']}' by {rc['author']}\n"
                
                if change.get('latest_comment'):
                    comment = change['latest_comment']
                    result += f"Latest comment by {comment['author']}: {comment['body'][:200]}...\n"
            
            return result
        else:
            return f"Watched JIRA issue {issue_key} for {max_checks * check_interval // 60} minutes - no changes detected"
            
    except Exception as e:
        logger.error(f"Failed to watch JIRA issue: {e}")
        return f"Error watching JIRA issue {issue_key}: {e}"

@tool  
def jira_watch_project(
    project_key: str,
    url: str,
    check_interval: int = 600,
    username: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    max_checks: int = 6
) -> str:
    """Watch a JIRA project for new issues and updates.
    
    Args:
        project_key: JIRA project key (e.g., "PROJ")
        url: JIRA server URL
        check_interval: Seconds between checks (default: 600 = 10 minutes)
        username: Username or use JIRA_USERNAME env var
        token: API token or use JIRA_API_TOKEN env var
        email: Email for cloud JIRA or use JIRA_EMAIL env var
        max_checks: Maximum number of checks (default: 6 = 1 hour)
    """
    try:
        jira = _get_jira_connection(url, username, token, email)
        
        # Get initial project state
        initial_jql = f'project = {project_key} ORDER BY updated DESC'
        initial_issues = jira.search_issues(initial_jql, maxResults=50)
        initial_count = len(initial_issues)
        initial_keys = {issue.key for issue in initial_issues}
        
        logger.info(f"Starting to watch JIRA project {project_key}")
        logger.info(f"Initial issue count: {initial_count}")
        
        project_changes = []
        
        for check in range(max_checks):
            time.sleep(check_interval)
            
            try:
                # Check for project updates
                current_issues = jira.search_issues(initial_jql, maxResults=50)
                current_count = len(current_issues)
                current_keys = {issue.key for issue in current_issues}
                
                changes_in_check = {
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'new_issues': [],
                    'updated_issues': []
                }
                
                # Check for new issues
                new_issues = current_keys - initial_keys
                if new_issues:
                    for issue_key in new_issues:
                        issue = jira.issue(issue_key)
                        changes_in_check['new_issues'].append({
                            'key': issue_key,
                            'summary': issue.fields.summary,
                            'status': issue.fields.status.name,
                            'assignee': issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned',
                            'creator': issue.fields.creator.displayName,
                            'created': issue.fields.created
                        })
                
                # Check for recently updated issues  
                recent_jql = f'project = {project_key} AND updated >= -{check_interval // 60}m ORDER BY updated DESC'
                recently_updated = jira.search_issues(recent_jql, maxResults=20)
                
                for issue in recently_updated:
                    if issue.key in initial_keys:  # Existing issue was updated
                        changes_in_check['updated_issues'].append({
                            'key': issue.key,
                            'summary': issue.fields.summary,
                            'status': issue.fields.status.name,
                            'assignee': issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned',
                            'updated': issue.fields.updated
                        })
                
                if changes_in_check['new_issues'] or changes_in_check['updated_issues']:
                    project_changes.append(changes_in_check)
                    logger.info(f"Project changes detected in {project_key}")
                
                # Update baseline
                initial_keys = current_keys
                
            except Exception as e:
                logger.error(f"Error checking project {project_key}: {e}")
                return f"Error monitoring project {project_key}: {e}"
        
        if project_changes:
            result = f"Watched JIRA project {project_key} - changes detected in {len(project_changes)} checks:\n"
            
            for i, check_changes in enumerate(project_changes, 1):
                result += f"\n--- Check {i} at {check_changes['timestamp']} ---\n"
                
                if check_changes['new_issues']:
                    result += f"New issues ({len(check_changes['new_issues'])}):\n"
                    for issue in check_changes['new_issues']:
                        result += f"  📝 {issue['key']}: {issue['summary'][:80]}...\n"
                        result += f"     Status: {issue['status']}, Assignee: {issue['assignee']}\n"
                
                if check_changes['updated_issues']:
                    result += f"Updated issues ({len(check_changes['updated_issues'])}):\n"
                    for issue in check_changes['updated_issues']:
                        result += f"  🔄 {issue['key']}: {issue['summary'][:80]}...\n"
                        result += f"     Status: {issue['status']}, Updated: {issue['updated']}\n"
            
            return result
        else:
            return f"Watched JIRA project {project_key} for {max_checks * check_interval // 60} minutes - no changes detected"
            
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