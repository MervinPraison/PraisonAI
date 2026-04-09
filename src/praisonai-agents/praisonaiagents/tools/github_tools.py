import os
import subprocess
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import logging
from .decorator import tool

logger = logging.getLogger(__name__)

@tool
def github_create_branch(branch_name: str) -> str:
    """Create and checkout a new git branch.
    
    Args:
        branch_name: The name of the branch to create and checkout.
    """
    try:
        # Check if we are in a git repository
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", branch_name], check=True, capture_output=True, text=True)
        return f"Successfully created and checked out branch '{branch_name}'"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create branch: {e.stderr}")
        return f"Error creating branch: {e.stderr}"

@tool
def github_commit_and_push(commit_message: str) -> str:
    """Stage all changes, commit them with the provided message, and push to the remote repository.
    
    Args:
        commit_message: The message to use for the commit.
    """
    try:
        # Add all changes
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], check=True, capture_output=True, text=True)
        if not status.stdout.strip():
            return "No changes to commit."
            
        # Commit changes
        subprocess.run(["git", "commit", "-m", commit_message], check=True, capture_output=True, text=True)
        
        # Get current branch
        branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=True, capture_output=True, text=True)
        current_branch = branch_result.stdout.strip()
        
        # Push to remote
        subprocess.run(["git", "push", "-u", "origin", current_branch], check=True, capture_output=True, text=True)
        return f"Successfully committed and pushed changes to branch '{current_branch}'"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to commit and push: {e.stderr}")
        return f"Error committing and pushing: {e.stderr}"

@tool
def github_create_pull_request(title: str, body: str, head_branch: str, base_branch: str = "main") -> str:
    """Create a Pull Request on GitHub using the gh CLI.
    
    Args:
        title: The title/summary of the Pull Request that will appear in the GitHub UI. 
               Should be descriptive and concise (e.g., "Fix login validation bug").
        body: The detailed description/content of the Pull Request. Can include markdown 
              formatting, issue references (#123), and explanations of changes made.
        head_branch: The source branch containing your changes that you want to merge. 
                     This is typically the feature branch you've been working on.
        base_branch: The target branch to merge your changes into. Usually the main 
                     development branch like "main", "master", or "develop". Defaults to "main".
    
    Returns:
        str: Success message with PR URL if created successfully, or error message if failed.
    
    Example:
        >>> github_create_pull_request(
        ...     title="Add user authentication feature", 
        ...     body="Implements secure login with JWT tokens\\n\\nFixes #123",
        ...     head_branch="feature/auth",
        ...     base_branch="main"
        ... )
        'Successfully created Pull Request:\nhttps://github.com/user/repo/pull/456'
    """
    try:
        # Verify gh CLI is installed and authenticated
        subprocess.run(["gh", "auth", "status"], check=True, capture_output=True)
        
        # Create PR
        cmd = [
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--head", head_branch,
            "--base", base_branch
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return f"Successfully created Pull Request:\n{result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create PR: {e.stderr}")
        return f"Error creating Pull Request. Make sure 'gh' CLI is installed and authenticated: {e.stderr}"
