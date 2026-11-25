"""``praisonai ship`` step 1: commit, push, open a draft PR as the user. Never merges."""

import json
import subprocess
from typing import Callable, List, Optional

from praisonaiagents.errors import PraisonAIError
from praisonaiagents.permissions import is_secret_path


class ShipRefused(RuntimeError, PraisonAIError):
    """Ship stopped before changing anything; the message says why."""


def _out(run: Callable, *cmd: str, ok: bool = False) -> Optional[str]:
    proc = run(list(cmd), capture_output=True, text=True)
    if proc.returncode != 0:
        if ok:
            return None
        raise ShipRefused(f"{' '.join(cmd)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout.strip()


def _changed_files(run: Callable) -> List[str]:
    proc = run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], capture_output=True, text=True)
    entries, files = iter(proc.stdout.split("\0")), []
    for entry in entries:
        if len(entry) > 3:
            files.append(entry[3:])
            if entry[0] in "RC":
                next(entries, None)  # a rename's source path follows; skip it
    return files


def ship_to_draft_pr(
    message: Optional[str] = None, dry_run: bool = False, run: Callable = subprocess.run
) -> str:
    """Commit all changes, push the branch and open a draft PR. Returns the PR URL.

    With ``dry_run`` it returns the plan and changes nothing. Raises
    :class:`ShipRefused` on the default branch, a fork, a non-GitHub repo or
    when a secret file (``.env``, a private key) would be committed.
    """
    branch = _out(run, "git", "rev-parse", "--abbrev-ref", "HEAD")
    repo = _out(run, "gh", "repo", "view", "--json", "defaultBranchRef,isFork", ok=True)
    if repo is None:
        raise ShipRefused("not a GitHub repository, or gh is not logged in (run: gh auth login)")
    info = json.loads(repo)
    base = info["defaultBranchRef"]["name"]
    if info.get("isFork"):
        raise ShipRefused("ship does not open pull requests from a fork")
    if branch in (base, "HEAD"):
        raise ShipRefused(f"on the default branch '{base}' (or detached); create a branch first")
    files = _changed_files(run)
    secrets = [f for f in files if is_secret_path(f)]
    if secrets:
        raise ShipRefused(f"refusing to commit secret files: {', '.join(secrets)}")
    if dry_run:
        listed = "".join(f"\n  {f}" for f in files) or "\n  (nothing to commit)"
        return f"Would commit on '{branch}', push, and open a draft PR into '{base}':{listed}"
    if files:
        _out(run, "git", "add", "-A")
        if not message:
            from praisonai_code.cli.features.git_integration import CommitMessageGenerator

            diff = _out(run, "git", "diff", "--cached")
            message = CommitMessageGenerator(use_ai=False).generate(diff)
        _out(run, "git", "commit", "-m", message)
    _out(run, "git", "push", "-u", "origin", "HEAD")
    existing = _out(run, "gh", "pr", "view", "--json", "url,state", ok=True)
    if existing and json.loads(existing).get("state") == "OPEN":
        return json.loads(existing)["url"]
    return _out(run, "gh", "pr", "create", "--draft", "--fill", "--base", base, "--head", branch)
