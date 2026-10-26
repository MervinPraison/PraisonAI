import os
import re
import subprocess
import logging
import secrets
from typing import List, Optional
from .decorator import tool

logger = logging.getLogger(__name__)

AGENT_BRANCH_PREFIX = "praisonai/"


def _git(*args: str, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a git command (in ``cwd`` when given) capturing output as text."""
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, cwd=cwd)


def _default_branch(cwd: Optional[str] = None) -> str:
    """Detect the remote default branch, falling back to main/master."""
    try:
        ref = _git("symbolic-ref", "refs/remotes/origin/HEAD", cwd=cwd).stdout.strip()
        # e.g. refs/remotes/origin/main -> main
        return ref.rsplit("/", 1)[-1]
    except subprocess.CalledProcessError:
        pass
    for candidate in ("main", "master"):
        try:
            _git("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{candidate}", cwd=cwd)
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


def _divergence_refusal(branch: str, cwd: Optional[str] = None) -> Optional[str]:
    """Return a refusal reason if pushing ``branch`` would require a force.

    A force push is required when the remote branch exists but is not an
    ancestor of HEAD. This check is *never* overridable (see
    github_commit_and_push) and therefore applies to every branch, including
    agent-prefixed ones.
    """
    try:
        _git("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}", cwd=cwd)
        remote_exists = True
    except subprocess.CalledProcessError:
        remote_exists = False
    if remote_exists:
        try:
            _git("merge-base", "--is-ancestor", f"origin/{branch}", "HEAD", cwd=cwd)
        except subprocess.CalledProcessError:
            return (
                f"refusing to push to '{branch}': the remote branch has "
                f"diverged from HEAD and pushing would require a force."
            )
    return None


def _branch_push_safety(branch: str, cwd: Optional[str] = None) -> Optional[str]:
    """Return a refusal reason if pushing ``branch`` is unsafe, else None.

    Rules (see github_commit_and_push docstring):
      * Agent-prefixed branches (``praisonai/``) skip the default/foreign-author
        rules but are still subject to the (never-overridable) divergence check.
      * The repository default branch is never pushed directly.
      * Branches carrying commits authored by someone other than the
        configured committer identity are refused.
      * Branches whose existing remote is not an ancestor of HEAD
        (i.e. would require a force push) are refused.
    """
    # Divergence (force-push) is refused for every branch, agent-prefixed or not.
    diverged = _divergence_refusal(branch, cwd=cwd)
    if diverged:
        return diverged

    if branch.startswith(AGENT_BRANCH_PREFIX):
        return None

    default = _default_branch(cwd=cwd)
    if branch == default:
        return (
            f"refusing to push to '{branch}': it is the repository "
            f"default/protected branch. Pass allow_unsafe_branch=True to override."
        )

    # Foreign-author check: commits on this branch since the merge-base with
    # the default branch must all be authored by the configured committer.
    try:
        committer = _git("config", "user.email", cwd=cwd).stdout.strip()
    except subprocess.CalledProcessError:
        committer = ""
    if committer:
        try:
            merge_base = _git(
                "merge-base", f"origin/{default}", "HEAD", cwd=cwd
            ).stdout.strip()
            authors = _git(
                "log", "--format=%ae", f"{merge_base}..HEAD", cwd=cwd
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

    return None

@tool
def github_create_branch(branch_name: str, repo_path: Optional[str] = None) -> str:
    """Create and checkout a new git branch.

    
    Args:
        branch_name: The name of the branch to create and checkout.
        repo_path: Repository directory to run git in. Defaults to the
            current working directory.
    """
    try:
        # Check if we are in a git repository
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], check=True, capture_output=True, cwd=repo_path)
        # Validate branch name to prevent misinterpretation as git options or invalid refs
        try:
            subprocess.run(
                ["git", "check-ref-format", f"refs/heads/{branch_name}"],
                check=True, capture_output=True, text=True, cwd=repo_path
            )
        except subprocess.CalledProcessError as e:
            return f"Error: invalid branch name '{branch_name}': {e.stderr.strip() if e.stderr else 'branch name is not a valid git ref'}"
        subprocess.run(["git", "checkout", "-B", branch_name], check=True, capture_output=True, text=True, cwd=repo_path)
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
    repo_path: Optional[str] = None,
    paths: Optional[List[str]] = None,
) -> str:
    """Stage tracked changes, commit them, and push to the remote repository safely.

    Only changes to already-tracked files are staged (``git add -u``); new
    files are committed only when listed in ``paths``. Staging happens after
    the safety checks below, so a refusal leaves the index untouched.

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
        repo_path: Repository directory to run git in. Defaults to the
            current working directory.
        paths: Extra (e.g. untracked) files to stage alongside tracked changes.
    """
    try:
        allow_unsafe = allow_unsafe_branch or os.environ.get(
            "PRAISONAI_GIT_ALLOW_UNSAFE_BRANCH", ""
        ).lower() in ("1", "true", "yes")

        # Check if there are changes to commit (tracked changes or explicit paths)
        status = _git("status", "--porcelain", "--untracked-files=no", cwd=repo_path)
        if not status.stdout.strip() and not paths:
            return "No changes to commit."

        # Resolve target branch (defaults to current)
        current_branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo_path).stdout.strip()
        target_branch = branch or current_branch

        default = _default_branch(cwd=repo_path)
        auto_created = False

        # Rule 2: default branch is never pushed directly (unless overridden).
        if target_branch == default and not allow_unsafe:
            target_branch = _auto_branch_name(commit_message)
            auto_created = True

        # Safety checks run BEFORE any commit or branch mutation so that a
        # refusal leaves the working tree and pending changes untouched (a
        # retry can then succeed). Adding the new commit does not change the
        # divergence/foreign-author verdicts, which are about existing history.
        if not allow_unsafe:
            reason = _branch_push_safety(target_branch, cwd=repo_path)
            if reason:
                return f"Error: {reason}"
        else:
            if not target_branch.startswith(AGENT_BRANCH_PREFIX):
                logger.warning(
                    "PRAISONAI: allow_unsafe_branch bypassing branch-safety "
                    "checks for '%s'", target_branch
                )
            # Even when overriding, divergence (force) is never permitted.
            diverged = _divergence_refusal(target_branch, cwd=repo_path)
            if diverged:
                return f"Error: {diverged}"

        # Move to the resolved branch only after passing safety checks.
        if auto_created:
            # Fresh agent branch created from current HEAD.
            _git("checkout", "-B", target_branch, cwd=repo_path)
        elif target_branch != current_branch:
            # Switch to the requested branch without discarding its commits:
            # ``-B`` would reset an existing branch to HEAD, so use a plain
            # checkout when the branch already exists and only create it when
            # it does not.
            try:
                _git(
                    "show-ref", "--verify", "--quiet",
                    f"refs/heads/{target_branch}", cwd=repo_path,
                )
                _git("checkout", target_branch, cwd=repo_path)
            except subprocess.CalledProcessError:
                _git("checkout", "-b", target_branch, cwd=repo_path)

        # Stage tracked changes plus explicitly listed paths (never ``git add .``)
        _git("add", "-u", cwd=repo_path)
        if paths:
            _git("add", "--", *paths, cwd=repo_path)

        # Commit changes on the resolved branch
        _git("commit", "-m", commit_message, cwd=repo_path)

        # Push to remote (never with --force)
        _git("push", "-u", "origin", target_branch, cwd=repo_path)
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
def github_create_pull_request(
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
    repo_path: Optional[str] = None,
) -> str:
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
        repo_path: Repository directory to run gh in. Defaults to the current
                   working directory.
    
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
        subprocess.run(["gh", "auth", "status"], check=True, capture_output=True, cwd=repo_path)
        
        # Create PR
        cmd = [
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--head", head_branch,
            "--base", base_branch
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=repo_path)
        return f"Successfully created Pull Request:\n{result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create PR: {e.stderr}")
        return f"Error creating Pull Request. Make sure 'gh' CLI is installed and authenticated: {e.stderr}"
