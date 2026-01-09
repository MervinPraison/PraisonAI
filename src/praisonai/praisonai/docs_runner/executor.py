"""
Docs Executor - Main orchestrator for docs code execution.

Coordinates extraction, classification, workspace creation, execution, and reporting.
"""

from __future__ import annotations

import fnmatch
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable

from .extractor import FenceExtractor, CodeBlock
from .classifier import RunnableClassifier
from .workspace import WorkspaceWriter
from .runner import SnippetRunner
from .reporter import DocsReportBuilder, SnippetResult


@dataclass
class DocsRunReport:
    """Complete report from a docs execution run."""
    
    snippets: List[SnippetResult]
    docs_path: Path
    workspace_path: Optional[Path] = None
    report_path: Optional[Path] = None
    cli_args: List[str] = field(default_factory=list)
    
    @property
    def totals(self) -> dict:
        """Calculate totals by status."""
        counts = {"passed": 0, "failed": 0, "skipped": 0, "timeout": 0, "not_run": 0}
        for s in self.snippets:
            if s.status in counts:
                counts[s.status] += 1
        return counts


class DocsExecutor:
    """Main orchestrator for docs code execution."""
    
    def __init__(
        self,
        docs_path: Path,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        timeout: int = 60,
        fail_fast: bool = False,
        stream_output: bool = True,
        dry_run: bool = False,
        mode: str = "lenient",  # lenient or strict
        max_snippets: Optional[int] = None,
        require_env: Optional[List[str]] = None,
        env_overrides: Optional[dict] = None,
        report_dir: Optional[Path] = None,
        workspace_dir: Optional[Path] = None,
        generate_json: bool = True,
        generate_md: bool = True,
    ):
        """
        Initialize docs executor.
        
        Args:
            docs_path: Path to documentation directory.
            include_patterns: Glob patterns to include docs.
            exclude_patterns: Glob patterns to exclude docs.
            languages: Languages to execute (default: python).
            timeout: Per-snippet timeout in seconds.
            fail_fast: Stop on first failure.
            stream_output: Stream output to terminal.
            dry_run: Extract only, don't execute.
            mode: 'lenient' or 'strict' (strict fails on not_run).
            max_snippets: Maximum snippets to process.
            require_env: Global required env vars.
            env_overrides: Environment variable overrides.
            report_dir: Directory for reports.
            workspace_dir: Directory for extracted scripts.
            generate_json: Generate JSON report.
            generate_md: Generate Markdown report.
        """
        self.docs_path = Path(docs_path).resolve()
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.languages = languages or ["python"]
        self.timeout = timeout
        self.fail_fast = fail_fast
        self.stream_output = stream_output
        self.dry_run = dry_run
        self.mode = mode
        self.max_snippets = max_snippets
        self.require_env = require_env or []
        self.env_overrides = env_overrides or {}
        self.report_dir = Path(report_dir) if report_dir else None
        self.workspace_dir = Path(workspace_dir) if workspace_dir else None
        self.generate_json = generate_json
        self.generate_md = generate_md
    
    def discover_docs(self) -> List[Path]:
        """
        Discover documentation files.
        
        Returns:
            List of paths to doc files.
        """
        docs = []
        
        for ext in ('*.md', '*.mdx'):
            for doc_file in self.docs_path.rglob(ext):
                # Skip hidden and node_modules
                rel_path = doc_file.relative_to(self.docs_path)
                parts = rel_path.parts
                
                if any(p.startswith('.') or p == 'node_modules' for p in parts):
                    continue
                
                rel_str = rel_path.as_posix()
                
                # Apply include patterns
                if self.include_patterns:
                    if not any(fnmatch.fnmatch(rel_str, p) or fnmatch.fnmatch(doc_file.name, p) 
                               for p in self.include_patterns):
                        continue
                
                # Apply exclude patterns
                if self.exclude_patterns:
                    if any(fnmatch.fnmatch(rel_str, p) for p in self.exclude_patterns):
                        continue
                
                docs.append(doc_file)
        
        return sorted(docs, key=lambda p: p.relative_to(self.docs_path).as_posix())
    
    def _get_pythonpath(self) -> List[str]:
        """Get PYTHONPATH additions for local package imports."""
        paths = []
        
        # Try to find src directories
        current = self.docs_path
        for _ in range(5):
            src_dir = current / "src"
            if src_dir.exists():
                for subdir in src_dir.iterdir():
                    if subdir.is_dir() and not subdir.name.startswith('.'):
                        paths.append(str(subdir))
                break
            
            parent = current.parent
            if parent == current:
                break
            current = parent
        
        return paths
    
    def run(
        self,
        on_doc_start: Optional[Callable[[Path, int, int], None]] = None,
        on_snippet_start: Optional[Callable[[CodeBlock, int, int], None]] = None,
        on_snippet_end: Optional[Callable[[SnippetResult, int, int], None]] = None,
        on_output: Optional[Callable[[str, str], None]] = None,
    ) -> DocsRunReport:
        """
        Run docs code execution.
        
        Args:
            on_doc_start: Callback when starting a doc.
            on_snippet_start: Callback when starting a snippet.
            on_snippet_end: Callback when snippet completes.
            on_output: Callback for streaming output.
            
        Returns:
            DocsRunReport with all results.
        """
        # Check global required env
        for key in self.require_env:
            if not os.environ.get(key):
                return DocsRunReport(
                    snippets=[],
                    docs_path=self.docs_path,
                    cli_args=[f"--require-env={key} (missing)"],
                )
        
        # Discover docs
        docs = self.discover_docs()
        
        # Extract all code blocks
        extractor = FenceExtractor(languages=self.languages)
        all_blocks: List[CodeBlock] = []
        
        for doc in docs:
            blocks = extractor.extract(doc)
            # Filter to target languages
            blocks = [b for b in blocks if b.language in self.languages]
            all_blocks.extend(blocks)
        
        # Apply max_snippets limit
        if self.max_snippets and len(all_blocks) > self.max_snippets:
            all_blocks = all_blocks[:self.max_snippets]
        
        # Classify blocks
        classifier = RunnableClassifier(target_languages=tuple(self.languages))
        
        # Create workspace
        if self.workspace_dir:
            workspace_path = self.workspace_dir
        else:
            workspace_path = Path(tempfile.mkdtemp(prefix="praisonai_docs_"))
        
        workspace = WorkspaceWriter(workspace_path)
        
        # Create runner
        runner = SnippetRunner(
            timeout=self.timeout,
            capture_output=True,
            stream_output=self.stream_output,
            env_overrides=self.env_overrides,
            pythonpath_additions=self._get_pythonpath(),
        )
        
        results: List[SnippetResult] = []
        total = len(all_blocks)
        
        for idx, block in enumerate(all_blocks, 1):
            if on_snippet_start:
                on_snippet_start(block, idx, total)
            
            # Classify
            classification = classifier.classify(block)
            
            # Create result skeleton
            result = SnippetResult(
                doc_path=block.doc_path,
                block_index=block.block_index,
                language=block.language,
                line_start=block.line_start,
                line_end=block.line_end,
                runnable_decision=classification.reason,
                status="not_run",
                code_hash=block.code_hash,
            )
            
            if not classification.is_runnable:
                # Not runnable - mark as not_run or skipped
                if classification.reason == "directive_skip":
                    result.status = "skipped"
                    result.skip_reason = "Directive skip"
                else:
                    result.status = "not_run"
                    result.skip_reason = classification.reason
                
                results.append(result)
                
                if on_snippet_end:
                    on_snippet_end(result, idx, total)
                continue
            
            # Check required env from directive
            if classification.require_env:
                missing = runner.check_required_env(classification.require_env)
                if missing:
                    result.status = "skipped"
                    result.skip_reason = f"Missing env: {missing}"
                    results.append(result)
                    
                    if on_snippet_end:
                        on_snippet_end(result, idx, total)
                    continue
            
            # Dry run - don't execute
            if self.dry_run:
                result.status = "not_run"
                result.skip_reason = "Dry run mode"
                results.append(result)
                
                if on_snippet_end:
                    on_snippet_end(result, idx, total)
                continue
            
            # Write to workspace
            script_path = workspace.write(block)
            
            # Execute
            timeout = classification.timeout or self.timeout
            exec_result = runner.run(
                script_path,
                require_env=classification.require_env,
                custom_timeout=timeout,
                on_output=on_output if self.stream_output else None,
            )
            
            # Update result with execution data
            result.status = exec_result.status
            result.exit_code = exec_result.exit_code
            result.duration_seconds = exec_result.duration_seconds
            result.start_time = exec_result.start_time
            result.end_time = exec_result.end_time
            result.error_summary = exec_result.error_summary
            result.stdout = exec_result.stdout
            result.stderr = exec_result.stderr
            
            results.append(result)
            
            if on_snippet_end:
                on_snippet_end(result, idx, total)
            
            # Check fail-fast
            if self.fail_fast and result.status == "failed":
                break
        
        # Save workspace manifest
        workspace.save_manifest()
        
        # Generate reports
        report_path = None
        if self.report_dir:
            reporter = DocsReportBuilder(self.report_dir)
            reporter.save_logs(results)
            
            if self.generate_json:
                reporter.generate_json(results, self.docs_path)
            
            if self.generate_md:
                reporter.generate_markdown(results, self.docs_path)
            
            report_path = self.report_dir
        
        return DocsRunReport(
            snippets=results,
            docs_path=self.docs_path,
            workspace_path=workspace_path,
            report_path=report_path,
        )
