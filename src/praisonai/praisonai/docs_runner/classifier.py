"""
Runnable Classifier for code blocks.

Determines if a code block is runnable based on:
- Heuristics (imports + terminal actions)
- Directive overrides
- Safety checks (input(), infinite loops)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .extractor import CodeBlock


# Patterns for classification
IMPORT_PATTERN = re.compile(r'^\s*(import\s+\w+|from\s+\w+\s+import)', re.MULTILINE)
TERMINAL_ACTIONS = [
    r'\.start\s*\(',
    r'\.run\s*\(',
    r'\.chat\s*\(',
    r'print\s*\(',
    r'asyncio\.run\s*\(',
    r'if\s+__name__\s*==\s*["\']__main__["\']\s*:',
    r'agents\.start\s*\(',
    r'agent\.start\s*\(',
]
TERMINAL_PATTERN = re.compile('|'.join(TERMINAL_ACTIONS), re.MULTILINE)

INPUT_PATTERN = re.compile(r'\binput\s*\(')
INFINITE_LOOP_PATTERN = re.compile(r'while\s+True\s*:', re.MULTILINE)


@dataclass
class ClassificationResult:
    """Result of classifying a code block."""
    
    is_runnable: bool
    reason: str
    require_env: list = None
    timeout: int = None
    
    def __post_init__(self):
        if self.require_env is None:
            self.require_env = []


class RunnableClassifier:
    """Classifies code blocks as runnable or not."""
    
    def __init__(
        self,
        min_lines: int = 2,
        target_languages: tuple = ("python",),
    ):
        """
        Initialize classifier.
        
        Args:
            min_lines: Minimum lines for a block to be considered runnable.
            target_languages: Languages that can be executed.
        """
        self.min_lines = min_lines
        self.target_languages = target_languages
    
    def classify(self, block: "CodeBlock") -> ClassificationResult:
        """
        Classify a code block as runnable or not.
        
        Args:
            block: The CodeBlock to classify.
            
        Returns:
            ClassificationResult with is_runnable and reason.
        """
        # Check directive skip first
        if block.directive_skip:
            return ClassificationResult(
                is_runnable=False,
                reason="directive_skip",
            )
        
        # Check language
        if block.language not in self.target_languages:
            return ClassificationResult(
                is_runnable=False,
                reason=f"language_not_supported: {block.language}",
            )
        
        # Check directive override for runnable
        if block.directive_runnable is True:
            return ClassificationResult(
                is_runnable=True,
                reason="directive_override",
                require_env=block.directive_require_env,
                timeout=block.directive_timeout,
            )
        
        # Check for interactive input
        if INPUT_PATTERN.search(block.code):
            return ClassificationResult(
                is_runnable=False,
                reason="interactive_input",
            )
        
        # Check minimum lines
        code_lines = [line for line in block.code.split('\n') if line.strip()]
        if len(code_lines) < self.min_lines:
            return ClassificationResult(
                is_runnable=False,
                reason="too_short",
            )
        
        # Check for imports
        has_import = bool(IMPORT_PATTERN.search(block.code))
        
        # Check for terminal action
        has_terminal = bool(TERMINAL_PATTERN.search(block.code))
        
        # Heuristic: needs both import and terminal action
        if has_import and has_terminal:
            return ClassificationResult(
                is_runnable=True,
                reason="heuristic_standalone",
                require_env=block.directive_require_env,
                timeout=block.directive_timeout,
            )
        
        # Check for just print with import (simple scripts)
        if has_import and 'print(' in block.code:
            return ClassificationResult(
                is_runnable=True,
                reason="heuristic_standalone",
                require_env=block.directive_require_env,
                timeout=block.directive_timeout,
            )
        
        # Not runnable - partial snippet
        if not has_import:
            return ClassificationResult(
                is_runnable=False,
                reason="no_import_partial",
            )
        
        return ClassificationResult(
            is_runnable=False,
            reason="no_terminal_action_partial",
        )
