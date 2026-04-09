import subprocess
import logging
from .decorator import tool

logger = logging.getLogger(__name__)

@tool
def github_create_branch(branch_name: str) -> str:
    """Create and checkout a new git branch.
    
logger.debug(f"Branch '{branch_name}' checked out successfully.")
    Args:
        branch_name: The name of the branch to create and checkout.
    """
    try:
        # Check if we are in a git repository
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-B", branch_name], check=True, capture_output=True, text=True)
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
        title: The title of the Pull Request.
        body: The description body of the Pull Request.
        head_branch: The name of the branch where your changes are implemented.
        base_branch: The name of the branch you want your changes pulled into (default is main).
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
