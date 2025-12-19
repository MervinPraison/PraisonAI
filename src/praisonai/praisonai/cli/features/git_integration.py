"""
Git Integration System for PraisonAI CLI.

Inspired by Aider's Git integration for auto-commits and change tracking.
Provides seamless Git operations with AI-generated commit messages.

Architecture:
- GitManager: Core Git operations using subprocess
- CommitGenerator: AI-powered commit message generation
- DiffViewer: Rich diff display
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import subprocess
import logging
import re

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class GitStatus:
    """Git repository status."""
    branch: str = ""
    is_clean: bool = True
    staged_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0
    
    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.staged_files or self.modified_files or self.untracked_files)


@dataclass
class GitCommit:
    """Git commit information."""
    hash: str
    short_hash: str
    message: str
    author: str
    date: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


@dataclass
class GitDiff:
    """Git diff information."""
    file_path: str
    additions: int = 0
    deletions: int = 0
    content: str = ""
    is_new: bool = False
    is_deleted: bool = False


# ============================================================================
# Git Manager
# ============================================================================

class GitManager:
    """
    Manages Git operations using subprocess.
    
    Uses subprocess instead of GitPython for lighter dependencies.
    """
    
    def __init__(self, repo_path: Optional[str] = None, verbose: bool = False):
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.verbose = verbose
        self._git_available = self._check_git()
    
    def _check_git(self) -> bool:
        """Check if git is available."""
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command."""
        cmd = ["git"] + list(args)
        if self.verbose:
            logger.debug(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.repo_path
        )
        
        if check and result.returncode != 0:
            logger.debug(f"Git error: {result.stderr}")
        
        return result
    
    @property
    def is_repo(self) -> bool:
        """Check if current directory is a git repository."""
        if not self._git_available:
            return False
        result = self._run_git("rev-parse", "--git-dir", check=False)
        return result.returncode == 0
    
    def get_status(self) -> GitStatus:
        """Get repository status."""
        status = GitStatus()
        
        if not self.is_repo:
            return status
        
        # Get branch
        result = self._run_git("branch", "--show-current", check=False)
        if result.returncode == 0:
            status.branch = result.stdout.strip()
        
        # Get status
        result = self._run_git("status", "--porcelain", check=False)
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                
                status_code = line[:2]
                file_path = line[3:]
                
                if status_code[0] in "MADRCU":
                    status.staged_files.append(file_path)
                if status_code[1] in "MD":
                    status.modified_files.append(file_path)
                if status_code == "??":
                    status.untracked_files.append(file_path)
        
        status.is_clean = not status.has_changes
        
        # Get ahead/behind
        result = self._run_git("rev-list", "--left-right", "--count", "HEAD...@{u}", check=False)
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                status.ahead = int(parts[0])
                status.behind = int(parts[1])
        
        return status
    
    def get_diff(self, staged: bool = False, file_path: Optional[str] = None) -> List[GitDiff]:
        """Get diff information."""
        diffs = []
        
        if not self.is_repo:
            return diffs
        
        args = ["diff"]
        if staged:
            args.append("--staged")
        args.append("--numstat")
        
        if file_path:
            args.append("--")
            args.append(file_path)
        
        result = self._run_git(*args, check=False)
        if result.returncode != 0:
            return diffs
        
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split("\t")
            if len(parts) >= 3:
                additions = int(parts[0]) if parts[0] != "-" else 0
                deletions = int(parts[1]) if parts[1] != "-" else 0
                path = parts[2]
                
                diffs.append(GitDiff(
                    file_path=path,
                    additions=additions,
                    deletions=deletions
                ))
        
        return diffs
    
    def get_diff_content(self, staged: bool = False, file_path: Optional[str] = None) -> str:
        """Get full diff content."""
        if not self.is_repo:
            return ""
        
        args = ["diff"]
        if staged:
            args.append("--staged")
        
        if file_path:
            args.append("--")
            args.append(file_path)
        
        result = self._run_git(*args, check=False)
        return result.stdout if result.returncode == 0 else ""
    
    def stage_files(self, files: Optional[List[str]] = None) -> bool:
        """Stage files for commit."""
        if not self.is_repo:
            return False
        
        if files:
            result = self._run_git("add", *files, check=False)
        else:
            result = self._run_git("add", "-A", check=False)
        
        return result.returncode == 0
    
    def commit(self, message: str, allow_empty: bool = False) -> Optional[GitCommit]:
        """Create a commit."""
        if not self.is_repo:
            return None
        
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        
        result = self._run_git(*args, check=False)
        
        if result.returncode != 0:
            logger.debug(f"Commit failed: {result.stderr}")
            return None
        
        # Get commit info
        return self.get_last_commit()
    
    def get_last_commit(self) -> Optional[GitCommit]:
        """Get the last commit."""
        if not self.is_repo:
            return None
        
        result = self._run_git(
            "log", "-1",
            "--format=%H|%h|%s|%an|%ai",
            check=False
        )
        
        if result.returncode != 0:
            return None
        
        parts = result.stdout.strip().split("|")
        if len(parts) >= 5:
            return GitCommit(
                hash=parts[0],
                short_hash=parts[1],
                message=parts[2],
                author=parts[3],
                date=parts[4]
            )
        
        return None
    
    def get_log(self, count: int = 10) -> List[GitCommit]:
        """Get commit log."""
        commits = []
        
        if not self.is_repo:
            return commits
        
        result = self._run_git(
            "log", f"-{count}",
            "--format=%H|%h|%s|%an|%ai",
            check=False
        )
        
        if result.returncode != 0:
            return commits
        
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split("|")
            if len(parts) >= 5:
                commits.append(GitCommit(
                    hash=parts[0],
                    short_hash=parts[1],
                    message=parts[2],
                    author=parts[3],
                    date=parts[4]
                ))
        
        return commits
    
    def undo_last_commit(self, soft: bool = True) -> bool:
        """Undo the last commit."""
        if not self.is_repo:
            return False
        
        reset_type = "--soft" if soft else "--hard"
        result = self._run_git("reset", reset_type, "HEAD~1", check=False)
        
        return result.returncode == 0
    
    def create_branch(self, name: str, checkout: bool = True) -> bool:
        """Create a new branch."""
        if not self.is_repo:
            return False
        
        if checkout:
            result = self._run_git("checkout", "-b", name, check=False)
        else:
            result = self._run_git("branch", name, check=False)
        
        return result.returncode == 0
    
    def checkout_branch(self, name: str) -> bool:
        """Checkout a branch."""
        if not self.is_repo:
            return False
        
        result = self._run_git("checkout", name, check=False)
        return result.returncode == 0
    
    def get_branches(self) -> List[str]:
        """Get list of branches."""
        if not self.is_repo:
            return []
        
        result = self._run_git("branch", "--list", check=False)
        if result.returncode != 0:
            return []
        
        branches = []
        for line in result.stdout.strip().split("\n"):
            if line:
                # Remove * and whitespace
                branch = line.strip().lstrip("* ")
                branches.append(branch)
        
        return branches
    
    def stash(self, message: Optional[str] = None) -> bool:
        """Stash changes."""
        if not self.is_repo:
            return False
        
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        
        result = self._run_git(*args, check=False)
        return result.returncode == 0
    
    def stash_pop(self) -> bool:
        """Pop stashed changes."""
        if not self.is_repo:
            return False
        
        result = self._run_git("stash", "pop", check=False)
        return result.returncode == 0


# ============================================================================
# Commit Message Generator
# ============================================================================

class CommitMessageGenerator:
    """
    Generates commit messages using AI or templates.
    """
    
    def __init__(self, use_ai: bool = True):
        self.use_ai = use_ai
    
    def generate(
        self,
        diff_content: str,
        context: Optional[str] = None,
        style: str = "conventional"
    ) -> str:
        """
        Generate a commit message.
        
        Args:
            diff_content: The diff to describe
            context: Optional context about the changes
            style: Message style (conventional, simple, detailed)
            
        Returns:
            Generated commit message
        """
        if not diff_content:
            return "Empty commit"
        
        if self.use_ai:
            return self._generate_with_ai(diff_content, context, style)
        else:
            return self._generate_from_diff(diff_content, style)
    
    def _generate_with_ai(
        self,
        diff_content: str,
        context: Optional[str],
        style: str
    ) -> str:
        """Generate commit message using AI."""
        # This would integrate with the agent system
        # For now, return a template-based message
        return self._generate_from_diff(diff_content, style)
    
    def _generate_from_diff(self, diff_content: str, style: str) -> str:
        """Generate commit message from diff analysis."""
        # Analyze diff
        files_changed = set()
        additions = 0
        deletions = 0
        
        for line in diff_content.split("\n"):
            if line.startswith("diff --git"):
                match = re.search(r"b/(.+)$", line)
                if match:
                    files_changed.add(match.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        
        # Determine change type
        if additions > deletions * 2:
            change_type = "feat"
            action = "Add"
        elif deletions > additions * 2:
            change_type = "refactor"
            action = "Remove"
        else:
            change_type = "fix"
            action = "Update"
        
        # Build message
        if len(files_changed) == 1:
            file_name = list(files_changed)[0]
            scope = Path(file_name).stem
            message = f"{change_type}({scope}): {action} {file_name}"
        elif len(files_changed) <= 3:
            files_str = ", ".join(sorted(files_changed))
            message = f"{change_type}: {action} {files_str}"
        else:
            message = f"{change_type}: {action} {len(files_changed)} files"
        
        if style == "detailed":
            message += f"\n\n+{additions} -{deletions} lines"
        
        return message


# ============================================================================
# Diff Viewer
# ============================================================================

class DiffViewer:
    """
    Rich-based diff viewer.
    """
    
    def __init__(self):
        self._console = None
    
    @property
    def console(self):
        """Lazy load Rich console."""
        if self._console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                self._console = None
        return self._console
    
    def display_diff(self, diff_content: str, title: str = "Changes") -> None:
        """Display diff with syntax highlighting."""
        if not self.console:
            print(diff_content)
            return
        
        from rich.panel import Panel
        from rich.syntax import Syntax
        
        syntax = Syntax(diff_content, "diff", theme="monokai", line_numbers=True)
        self.console.print(Panel(syntax, title=title, border_style="blue"))
    
    def display_status(self, status: GitStatus) -> None:
        """Display git status."""
        if not self.console:
            print(f"Branch: {status.branch}")
            print(f"Staged: {len(status.staged_files)}")
            print(f"Modified: {len(status.modified_files)}")
            print(f"Untracked: {len(status.untracked_files)}")
            return
        
        from rich.panel import Panel
        from rich.table import Table
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Category")
        table.add_column("Files", justify="right")
        
        table.add_row("Branch", status.branch or "detached")
        table.add_row("Staged", str(len(status.staged_files)))
        table.add_row("Modified", str(len(status.modified_files)))
        table.add_row("Untracked", str(len(status.untracked_files)))
        
        if status.ahead or status.behind:
            table.add_row("Ahead/Behind", f"+{status.ahead} / -{status.behind}")
        
        self.console.print(Panel(table, title="📊 Git Status", border_style="green"))
    
    def display_log(self, commits: List[GitCommit]) -> None:
        """Display commit log."""
        if not self.console:
            for commit in commits:
                print(f"{commit.short_hash} {commit.message}")
            return
        
        from rich.table import Table
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Hash")
        table.add_column("Message")
        table.add_column("Author")
        table.add_column("Date")
        
        for commit in commits:
            table.add_row(
                commit.short_hash,
                commit.message[:50] + "..." if len(commit.message) > 50 else commit.message,
                commit.author,
                commit.date[:10]
            )
        
        self.console.print(table)


# ============================================================================
# CLI Integration Handler
# ============================================================================

class GitIntegrationHandler:
    """
    Handler for integrating Git with PraisonAI CLI.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._git: Optional[GitManager] = None
        self._viewer: Optional[DiffViewer] = None
        self._generator: Optional[CommitMessageGenerator] = None
    
    @property
    def feature_name(self) -> str:
        return "git_integration"
    
    def initialize(self, repo_path: Optional[str] = None) -> GitManager:
        """Initialize Git manager."""
        self._git = GitManager(repo_path=repo_path, verbose=self.verbose)
        self._viewer = DiffViewer()
        self._generator = CommitMessageGenerator()
        
        if self.verbose and self._git.is_repo:
            from rich import print as rprint
            status = self._git.get_status()
            rprint(f"[cyan]Git initialized on branch: {status.branch}[/cyan]")
        
        return self._git
    
    def get_git(self) -> Optional[GitManager]:
        """Get the Git manager."""
        return self._git
    
    def show_status(self) -> GitStatus:
        """Show git status."""
        if not self._git:
            self._git = self.initialize()
        
        status = self._git.get_status()
        if self._viewer:
            self._viewer.display_status(status)
        
        return status
    
    def show_diff(self, staged: bool = False) -> str:
        """Show diff."""
        if not self._git:
            self._git = self.initialize()
        
        diff_content = self._git.get_diff_content(staged=staged)
        if self._viewer and diff_content:
            self._viewer.display_diff(diff_content)
        
        return diff_content
    
    def commit(
        self,
        message: Optional[str] = None,
        auto_stage: bool = True
    ) -> Optional[GitCommit]:
        """Create a commit."""
        if not self._git:
            self._git = self.initialize()
        
        if auto_stage:
            self._git.stage_files()
        
        if not message:
            # Generate message from diff
            diff_content = self._git.get_diff_content(staged=True)
            if self._generator:
                message = self._generator.generate(diff_content)
            else:
                message = "Update files"
        
        return self._git.commit(message)
    
    def undo(self, soft: bool = True) -> bool:
        """Undo last commit."""
        if not self._git:
            self._git = self.initialize()
        
        return self._git.undo_last_commit(soft=soft)
    
    def show_log(self, count: int = 10) -> List[GitCommit]:
        """Show commit log."""
        if not self._git:
            self._git = self.initialize()
        
        commits = self._git.get_log(count=count)
        if self._viewer:
            self._viewer.display_log(commits)
        
        return commits
