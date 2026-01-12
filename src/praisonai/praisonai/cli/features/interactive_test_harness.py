"""
Interactive Test Harness for PraisonAI.

Provides workspace isolation, fixtures, tool trace wrappers, and artifact writing
for testing interactive mode through the headless core executor.
"""

import json
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Blocked commands for safe execution
BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf /*",
    "sudo rm",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",  # Fork bomb
    "chmod -R 777 /",
    "curl | sh",
    "wget | sh",
}

# Allowed commands (whitelist for strict mode)
SAFE_COMMANDS = {
    "echo",
    "cat",
    "ls",
    "pwd",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    "python",
    "python3",
    "pip",
    "pip3",
    "node",
    "npm",
}


@dataclass
class WorkspaceFixture:
    """Definition of a workspace fixture."""
    name: str
    files: Dict[str, str] = field(default_factory=dict)  # path -> content
    directories: List[str] = field(default_factory=list)
    
    @classmethod
    def empty(cls) -> "WorkspaceFixture":
        """Create an empty workspace fixture."""
        return cls(name="empty")
    
    @classmethod
    def seeded(cls) -> "WorkspaceFixture":
        """Create a seeded workspace with common files."""
        return cls(
            name="seeded",
            files={
                "README.md": "# Test Project\n\nThis is a test project.",
                "main.py": "# Main entry point\nprint('Hello, World!')\n",
                "config.json": '{"name": "test", "version": "1.0.0"}',
            },
            directories=["src", "tests"],
        )
    
    @classmethod
    def git(cls) -> "WorkspaceFixture":
        """Create a git-initialized workspace."""
        fixture = cls.seeded()
        fixture.name = "git"
        fixture.files[".gitignore"] = "__pycache__/\n*.pyc\n.env\n"
        return fixture
    
    @classmethod
    def python_project(cls) -> "WorkspaceFixture":
        """Create a Python project workspace."""
        return cls(
            name="python_project",
            files={
                "README.md": "# Python Project\n",
                "main.py": '''"""Main module."""

def main():
    """Main function."""
    print("Hello from main!")

if __name__ == "__main__":
    main()
''',
                "utils.py": '''"""Utility functions."""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b

class Calculator:
    """Simple calculator class."""
    
    def __init__(self):
        self.result = 0
    
    def add(self, x: int) -> int:
        self.result += x
        return self.result
''',
                "requirements.txt": "# No dependencies\n",
            },
            directories=["tests"],
        )


BUILTIN_FIXTURES = {
    "empty": WorkspaceFixture.empty,
    "seeded": WorkspaceFixture.seeded,
    "git": WorkspaceFixture.git,
    "python_project": WorkspaceFixture.python_project,
}


@dataclass
class TestArtifacts:
    """Container for test artifacts."""
    transcript: List[Dict[str, str]] = field(default_factory=list)
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)
    result: Dict[str, Any] = field(default_factory=dict)
    workspace_snapshot: Optional[Dict[str, str]] = None
    judge_result: Optional[Dict[str, Any]] = None
    
    def save(self, artifacts_dir: Path) -> None:
        """Save artifacts to directory."""
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Save transcript
        transcript_path = artifacts_dir / "transcript.txt"
        with open(transcript_path, "w") as f:
            for entry in self.transcript:
                role = entry.get("role", "unknown")
                content = entry.get("content", "")
                f.write(f"[{role.upper()}]\n{content}\n\n")
        
        # Save tool trace as JSONL
        trace_path = artifacts_dir / "tool_trace.jsonl"
        with open(trace_path, "w") as f:
            for trace in self.tool_trace:
                f.write(json.dumps(trace) + "\n")
        
        # Save result
        result_path = artifacts_dir / "result.json"
        with open(result_path, "w") as f:
            json.dump(self.result, f, indent=2, default=str)
        
        # Save workspace snapshot if present
        if self.workspace_snapshot:
            snapshot_dir = artifacts_dir / "workspace"
            snapshot_dir.mkdir(exist_ok=True)
            for rel_path, content in self.workspace_snapshot.items():
                file_path = snapshot_dir / rel_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
        
        # Save judge result if present
        if self.judge_result:
            judge_path = artifacts_dir / "judge_result.json"
            with open(judge_path, "w") as f:
                json.dump(self.judge_result, f, indent=2, default=str)
        
        logger.debug(f"Saved artifacts to {artifacts_dir}")


class InteractiveTestHarness:
    """
    Test harness for interactive mode testing.
    
    Provides:
    - Workspace isolation (temp directory)
    - Fixture setup
    - Tool trace capture
    - Artifact generation
    - File assertions
    - Tool call assertions
    """
    
    def __init__(
        self,
        workspace: Optional[Path] = None,
        artifacts_dir: Optional[Path] = None,
        keep_workspace: bool = False,
        safe_commands: bool = True,
    ):
        """
        Initialize test harness.
        
        Args:
            workspace: Workspace directory (created if None)
            artifacts_dir: Directory for artifacts (created if None)
            keep_workspace: Keep workspace after cleanup
            safe_commands: Enforce safe command execution
        """
        self._workspace_created = workspace is None
        self.workspace = workspace or Path(tempfile.mkdtemp(prefix="praison_test_"))
        self.artifacts_dir = artifacts_dir or self.workspace / "artifacts"
        self.keep_workspace = keep_workspace
        self.safe_commands = safe_commands
        self.artifacts = TestArtifacts()
        self._executor = None
    
    def setup_workspace(self, fixture: str = "empty") -> None:
        """
        Set up workspace with fixture.
        
        Args:
            fixture: Fixture name (empty, seeded, git, python_project)
        """
        # Get fixture
        if fixture in BUILTIN_FIXTURES:
            fixture_obj = BUILTIN_FIXTURES[fixture]()
        else:
            logger.warning(f"Unknown fixture '{fixture}', using empty")
            fixture_obj = WorkspaceFixture.empty()
        
        # Create directories
        self.workspace.mkdir(parents=True, exist_ok=True)
        for dir_path in fixture_obj.directories:
            (self.workspace / dir_path).mkdir(parents=True, exist_ok=True)
        
        # Create files
        for rel_path, content in fixture_obj.files.items():
            file_path = self.workspace / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        
        # Initialize git if needed
        if fixture == "git":
            import subprocess
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=self.workspace,
                    capture_output=True,
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"Git init failed: {e}")
        
        logger.debug(f"Set up workspace with fixture '{fixture}' at {self.workspace}")
    
    def create_executor(
        self,
        model: str = "gpt-4o-mini",
        approval_mode: str = "auto",
        agents: Optional[List[Dict[str, Any]]] = None,
        workflow: Optional[Dict[str, Any]] = None,
    ):
        """
        Create headless executor using interactive core.
        
        Args:
            model: LLM model
            approval_mode: Approval mode (auto, manual, scoped)
            agents: Multi-agent configs
            workflow: Workflow routing config
            
        Returns:
            HeadlessInteractiveCore executor
        """
        from .interactive_core_headless import (
            HeadlessConfig,
            HeadlessInteractiveCore,
            AgentConfig,
        )
        
        agent_configs = []
        if agents:
            for a in agents:
                agent_configs.append(AgentConfig(
                    name=a.get("name", "Agent"),
                    instructions=a.get("instructions", "You are a helpful assistant."),
                    role=a.get("role", "assistant"),
                    llm=a.get("llm", model),
                ))
        
        config = HeadlessConfig(
            workspace=str(self.workspace),
            model=model,
            approval_mode=approval_mode,
            agents=agent_configs if agent_configs else None,
            workflow=workflow,
        )
        
        self._executor = HeadlessInteractiveCore(config)
        return self._executor
    
    def run(
        self,
        prompts: List[str],
        model: str = "gpt-4o-mini",
        approval_mode: str = "auto",
        agents: Optional[List[Dict[str, Any]]] = None,
        workflow: Optional[Dict[str, Any]] = None,
    ):
        """
        Run prompts through headless interactive core.
        
        Args:
            prompts: List of prompts to execute
            model: LLM model
            approval_mode: Approval mode
            agents: Multi-agent configs
            workflow: Workflow routing
            
        Returns:
            HeadlessExecutionResult
        """
        if not self._executor:
            self.create_executor(model, approval_mode, agents, workflow)
        
        result = self._executor.run(prompts)
        
        # Store in artifacts
        self.artifacts.transcript = result.transcript
        self.artifacts.tool_trace = self._executor.get_tool_trace()
        self.artifacts.result = result.to_dict()
        
        return result
    
    def verify_files(self, expected_files: Dict[str, str]) -> Dict[str, bool]:
        """
        Verify expected files exist and match content patterns.
        
        Args:
            expected_files: Dict of {relative_path: content_regex}
            
        Returns:
            Dict of {path: passed}
        """
        results = {}
        
        for rel_path, content_pattern in expected_files.items():
            file_path = self.workspace / rel_path
            
            if not file_path.exists():
                logger.debug(f"File not found: {rel_path}")
                results[rel_path] = False
                continue
            
            content = file_path.read_text()
            
            if content_pattern:
                try:
                    if re.search(content_pattern, content, re.MULTILINE | re.DOTALL):
                        results[rel_path] = True
                    else:
                        logger.debug(f"Content mismatch for {rel_path}: pattern '{content_pattern}' not found")
                        results[rel_path] = False
                except re.error as e:
                    logger.warning(f"Invalid regex pattern for {rel_path}: {e}")
                    results[rel_path] = False
            else:
                # Just check existence
                results[rel_path] = True
        
        return results
    
    def verify_tool_calls(
        self,
        expected_tools: Optional[List[str]] = None,
        forbidden_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Verify tool calls match expectations.
        
        Args:
            expected_tools: Tools that MUST have been called
            forbidden_tools: Tools that MUST NOT have been called
            
        Returns:
            Dict with verification results
        """
        called_tools = set()
        if self._executor:
            called_tools = set(self._executor.get_tools_called())
        
        results = {
            "called_tools": list(called_tools),
            "expected_passed": True,
            "forbidden_passed": True,
            "missing_tools": [],
            "forbidden_called": [],
        }
        
        # Check expected tools
        if expected_tools:
            expected_set = set(expected_tools)
            missing = expected_set - called_tools
            if missing:
                results["expected_passed"] = False
                results["missing_tools"] = list(missing)
        
        # Check forbidden tools
        if forbidden_tools:
            forbidden_set = set(forbidden_tools)
            forbidden_called = forbidden_set & called_tools
            if forbidden_called:
                results["forbidden_passed"] = False
                results["forbidden_called"] = list(forbidden_called)
        
        results["passed"] = results["expected_passed"] and results["forbidden_passed"]
        return results
    
    def verify_response(self, response: str, pattern: str) -> bool:
        """
        Verify response matches pattern.
        
        Args:
            response: Response text
            pattern: Regex pattern
            
        Returns:
            True if matches
        """
        if not pattern:
            return True
        
        try:
            return bool(re.search(pattern, response, re.MULTILINE | re.DOTALL | re.IGNORECASE))
        except re.error as e:
            logger.warning(f"Invalid response pattern: {e}")
            return False
    
    def snapshot_workspace(self) -> Dict[str, str]:
        """
        Create snapshot of workspace files.
        
        Returns:
            Dict of {relative_path: content}
        """
        snapshot = {}
        
        for file_path in self.workspace.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(self.workspace))
                # Skip binary files and large files
                if file_path.suffix in {".pyc", ".so", ".dll", ".exe", ".bin"}:
                    continue
                if file_path.stat().st_size > 100_000:  # 100KB limit
                    continue
                try:
                    snapshot[rel_path] = file_path.read_text()
                except Exception:
                    pass  # Skip unreadable files
        
        self.artifacts.workspace_snapshot = snapshot
        return snapshot
    
    def save_artifacts(self, test_id: str = "test") -> Path:
        """
        Save all artifacts to directory.
        
        Args:
            test_id: Test identifier for subdirectory
            
        Returns:
            Path to artifacts directory
        """
        test_artifacts_dir = self.artifacts_dir / test_id
        self.artifacts.save(test_artifacts_dir)
        return test_artifacts_dir
    
    def cleanup(self) -> None:
        """Clean up workspace and executor resources."""
        # Clean up executor (stops LSP/ACP subsystems)
        if self._executor is not None:
            try:
                self._executor.cleanup()
                logger.debug("Cleaned up executor resources")
            except Exception as e:
                logger.warning(f"Failed to clean up executor: {e}")
            finally:
                self._executor = None
        
        # Clean up workspace
        if self._workspace_created and not self.keep_workspace:
            try:
                shutil.rmtree(self.workspace)
                logger.debug(f"Cleaned up workspace: {self.workspace}")
            except Exception as e:
                logger.warning(f"Failed to clean up workspace: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False


def create_test_harness(
    fixture: str = "empty",
    workspace: Optional[Path] = None,
    artifacts_dir: Optional[Path] = None,
    keep_workspace: bool = False,
) -> InteractiveTestHarness:
    """
    Create and set up a test harness.
    
    Args:
        fixture: Workspace fixture name
        workspace: Workspace path (temp if None)
        artifacts_dir: Artifacts directory
        keep_workspace: Keep workspace after cleanup
        
    Returns:
        Configured InteractiveTestHarness
    """
    harness = InteractiveTestHarness(
        workspace=workspace,
        artifacts_dir=artifacts_dir,
        keep_workspace=keep_workspace,
    )
    harness.setup_workspace(fixture)
    return harness
