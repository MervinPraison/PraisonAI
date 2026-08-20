import os
import re
import subprocess
import logging
import secrets
from typing import Optional
from .decorator import tool

logger = logging.getLogger(__name__)

AGENT_BRANCH_PREFIX = "praisonai/"


def _git(*args: str) -> subprocess.CompletedProcess:
    """Run a git command capturing output as text."""
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def _default_branch() -> str:
    """Detect the remote default branch, falling back to main/master."""
    try:
        ref = _git("symbolic-ref", "refs/remotes/origin/HEAD").stdout.strip()
        # e.g. refs/remotes/origin/main -> main
        return ref.rsplit("/", 1)[-1]
    except subprocess.CalledProcessError:
        pass
    for candidate in ("main", "master"):
        try:
            _git("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{candidate}")
            return candidate
        except subprocess.CalledProcessError:
            continue
    return "main"


def _slugify(message: str) -> str:
    """Turn a commit message into a short branch-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", message.lower()).strip("-")
    slug = slug[:40].strip("-")
    return slug or "change"


def _auto_branch_name(commit_message: str) -> str:
    """Generate an agent-prefixed branch name from a commit message."""
    return f"{AGENT_BRANCH_PREFIX}{_slugify(commit_message)}-{secrets.token_hex(3)}"


def _branch_push_safety(branch: str) -> Optional[str]:
    """Return a refusal reason if pushing ``branch`` is unsafe, else None.

    Rules (see github_commit_and_push docstring):
      * Agent-prefixed branches (``praisonai/``) are always allowed.
      * The repository default branch is never pushed directly.
      * Branches carrying commits authored by someone other than the
        configured committer identity are refused.
      * Branches whose existing remote is not an ancestor of HEAD
        (i.e. would require a force push) are refused.
    """
    if branch.startswith(AGENT_BRANCH_PREFIX):
        return None

    default = _default_branch()
    if branch == default:
        return (
            f"refusing to push to '{branch}': it is the repository "
            f"default/protected branch. Pass allow_unsafe_branch=True to override."
        )

    # Foreign-author check: commits on this branch since the merge-base with
    # the default branch must all be authored by the configured committer.
    try:
        committer = _git("config", "user.email").stdout.strip()
    except subprocess.CalledProcessError:
        committer = ""
    if committer:
        try:
            merge_base = _git(
                "merge-base", f"origin/{default}", "HEAD"
            ).stdout.strip()
            authors = _git(
                "log", "--format=%ae", f"{merge_base}..HEAD"
            ).stdout.split()
            foreign = {a for a in authors if a and a != committer}
            if foreign:
                return (
                    f"refusing to push to '{branch}': it carries commits "
                    f"authored by someone else ({', '.join(sorted(foreign))}). "
                    f"Pass allow_unsafe_branch=True to override."
                )
        except subprocess.CalledProcessError:
            pass

    # Divergence check: if the remote branch exists and is not an ancestor of
    # HEAD, pushing would require a force. Refuse.
    try:
        _git("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}")
        remote_exists = True
    except subprocess.CalledProcessError:
        remote_exists = False
    if remote_exists:
        try:
            _git(
                "merge-base", "--is-ancestor", f"origin/{branch}", "HEAD"
            )
        except subprocess.CalledProcessError:
            return (
                f"refusing to push to '{branch}': the remote branch has "
                f"diverged from HEAD and pushing would require a force. "
                f"Pass allow_unsafe_branch=True to override."
            )
    return None

@tool
def github_create_branch(branch_name: str) -> str:
    """Create and checkout a new git branch.

    
    Args:
        branch_name: The name of the branch to create and checkout.
    """
    try:
        # Check if we are in a git repository
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], check=True, capture_output=True)
        # Validate branch name to prevent misinterpretation as git options or invalid refs
        try:
            subprocess.run(
                ["git", "check-ref-format", "--branch", branch_name],
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            return f"Error: invalid branch name '{branch_name}': {e.stderr.strip() if e.stderr else 'branch name is not a valid git ref'}"
        subprocess.run(["git", "checkout", "-B", branch_name], check=True, capture_output=True, text=True)
        logger.debug(f"Branch '{branch_name}' checked out successfully.")
        logger.debug(f"Successfully checked out branch '{branch_name}'")
        return f"Successfully created and checked out branch '{branch_name}'"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create branch: {e.stderr}")
        return f"Error creating branch: {e.stderr}"

@tool
def github_commit_and_push(
    commit_message: str,
    branch: Optional[str] = None,
    allow_unsafe_branch: bool = False,
) -> str:
    """Stage all changes, commit them, and push to the remote repository safely.

    Pushes are safe by construction. Before pushing, these rules are enforced:

    1. Agent-prefixed branches (``praisonai/``) are always allowed.
    2. The repository default/protected branch is never pushed directly. If HEAD
       is on it (or ``branch`` names it), a fresh ``praisonai/{slug}-{id}`` branch
       is created from HEAD and the push lands there instead.
    3. Foreign commits: if the target branch carries commits authored by someone
       other than the configured committer, the push is refused.
    4. Divergence: if the remote branch exists and is not an ancestor of HEAD, the
       push is refused (never force). No force-push variant is offered.
    5. Override: ``allow_unsafe_branch=True`` (or env
       ``PRAISONAI_GIT_ALLOW_UNSAFE_BRANCH=true``) bypasses rules 2-3 with a
       logged warning — opt-in, never default.

    Args:
        commit_message: The message to use for the commit.
        branch: Target branch to push to. Defaults to the current branch.
        allow_unsafe_branch: Opt-in override for the default/foreign-author
            refusals. Divergence (force-push) is never allowed.
    """
    try:
        allow_unsafe = allow_unsafe_branch or os.environ.get(
            "PRAISONAI_GIT_ALLOW_UNSAFE_BRANCH", ""
        ).lower() in ("1", "true", "yes")

        # Add all changes
        subprocess.run(["git", "add", "."], check=True, capture_output=True)

        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], check=True, capture_output=True, text=True)
        if not status.stdout.strip():
            return "No changes to commit."

        # Resolve target branch (defaults to current)
        current_branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        target_branch = branch or current_branch

        default = _default_branch()
        auto_created = False

        # Rule 2: default branch is never pushed directly (unless overridden).
        if target_branch == default and not allow_unsafe:
            target_branch = _auto_branch_name(commit_message)
            _git("checkout", "-B", target_branch)
            auto_created = True
        elif target_branch != current_branch:
            # Switch to the requested branch before committing.
            _git("checkout", "-B", target_branch)

        # Commit changes on the resolved branch
        subprocess.run(["git", "commit", "-m", commit_message], check=True, capture_output=True, text=True)

        # Safety checks (skipped for the divergence check are never overridable).
        if not allow_unsafe:
            reason = _branch_push_safety(target_branch)
            if reason:
                return f"Error: {reason}"
        else:
            # Even when overriding, divergence (force) is never permitted.
            if not target_branch.startswith(AGENT_BRANCH_PREFIX):
                logger.warning(
                    "PRAISONAI: allow_unsafe_branch bypassing branch-safety "
                    "checks for '%s'", target_branch
                )
            try:
                _git("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{target_branch}")
                _git("merge-base", "--is-ancestor", f"origin/{target_branch}", "HEAD")
            except subprocess.CalledProcessError as e:
                if "merge-base" in " ".join(e.cmd if e.cmd else []):
                    return (
                        f"Error: refusing to push to '{target_branch}': the remote "
                        f"branch has diverged from HEAD and pushing would require a "
                        f"force."
                    )

        # Push to remote (never with --force)
        subprocess.run(["git", "push", "-u", "origin", target_branch], check=True, capture_output=True, text=True)
        if auto_created:
            return (
                f"Successfully committed and pushed changes to new agent branch "
                f"'{target_branch}' (refused direct push to default branch '{default}')"
            )
        return f"Successfully committed and pushed changes to branch '{target_branch}'"
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
        'Successfully created Pull Request:\\nhttps://github.com/user/repo/pull/456'
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
