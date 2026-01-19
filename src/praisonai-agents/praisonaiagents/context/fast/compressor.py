"""
Context compressor for FastContext.

Provides token-aware context compression:
- TruncateCompressor: Simple token-based truncation
- SmartCompressor: Preserves important content
- LLMLinguaCompressor: Optional LLMLingua integration (wrapper only)

Design principles:
- No external dependencies for basic compression
- Lazy import for optional LLMLingua
- Preserves most relevant content
"""

import logging
from typing import Protocol, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy availability check for llmlingua
_LLMLINGUA_AVAILABLE: Optional[bool] = None


def _check_llmlingua() -> bool:
    """Lazy check for llmlingua availability."""
    global _LLMLINGUA_AVAILABLE
    if _LLMLINGUA_AVAILABLE is None:
        try:
            import llmlingua  # noqa: F401
            _LLMLINGUA_AVAILABLE = True
        except ImportError:
            _LLMLINGUA_AVAILABLE = False
    return _LLMLINGUA_AVAILABLE


class ContextCompressor(Protocol):
    """Protocol for context compression."""
    
    def compress(self, text: str, max_tokens: int) -> str:
        """Compress text to fit within token budget.
        
        Args:
            text: Text to compress
            max_tokens: Maximum tokens allowed
            
        Returns:
            Compressed text
        """
        ...


@dataclass
class CompressionConfig:
    """Configuration for context compression."""
    chars_per_token: float = 4.0  # Conservative estimate
    preserve_start_lines: int = 5  # Preserve first N lines
    preserve_end_lines: int = 3   # Preserve last N lines
    truncation_marker: str = "\n\n... [content truncated] ...\n\n"


class TruncateCompressor:
    """Simple token-aware truncation compressor.
    
    Preserves start and end of content, truncates middle.
    """
    
    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        return int(len(text) / self.config.chars_per_token)
    
    def compress(self, text: str, max_tokens: int) -> str:
        """Compress text by truncating middle.
        
        Args:
            text: Text to compress
            max_tokens: Maximum tokens allowed
            
        Returns:
            Compressed text
        """
        current_tokens = self.estimate_tokens(text)
        
        if current_tokens <= max_tokens:
            return text
        
        # Calculate how much to keep
        max_chars = int(max_tokens * self.config.chars_per_token)
        marker_len = len(self.config.truncation_marker)
        available_chars = max_chars - marker_len
        
        if available_chars <= 0:
            return text[:max_chars]
        
        # Split into lines for smarter truncation
        lines = text.split('\n')
        
        # Preserve start and end lines
        start_lines = lines[:self.config.preserve_start_lines]
        end_lines = lines[-self.config.preserve_end_lines:] if self.config.preserve_end_lines > 0 else []
        
        start_text = '\n'.join(start_lines)
        end_text = '\n'.join(end_lines)
        
        # Calculate remaining budget for middle
        preserved_len = len(start_text) + len(end_text)
        middle_budget = available_chars - preserved_len
        
        if middle_budget <= 0:
            # Not enough room, just truncate at char level
            half = available_chars // 2
            return text[:half] + self.config.truncation_marker + text[-half:]
        
        # Take some middle content
        middle_lines = lines[self.config.preserve_start_lines:-self.config.preserve_end_lines] if self.config.preserve_end_lines > 0 else lines[self.config.preserve_start_lines:]
        middle_text = '\n'.join(middle_lines)
        
        if len(middle_text) <= middle_budget:
            return text  # Actually fits
        
        # Truncate middle
        middle_truncated = middle_text[:middle_budget // 2]
        
        return start_text + '\n' + middle_truncated + self.config.truncation_marker + end_text


class SmartCompressor:
    """Smart compressor that preserves important content.
    
    Uses heuristics to identify important lines (definitions, headers, etc.)
    """
    
    IMPORTANT_PATTERNS = [
        'def ', 'class ', 'async def ',  # Function/class definitions
        'import ', 'from ',  # Imports
        '# ', '"""', "'''",  # Comments/docstrings
        'if __name__', 'return ',  # Key statements
    ]
    
    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        self._fallback = TruncateCompressor(config)
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        return int(len(text) / self.config.chars_per_token)
    
    def _score_line(self, line: str) -> int:
        """Score a line's importance."""
        score = 0
        stripped = line.strip()
        
        for pattern in self.IMPORTANT_PATTERNS:
            if stripped.startswith(pattern):
                score += 10
        
        # Penalize empty lines
        if not stripped:
            score -= 5
        
        return score
    
    def compress(self, text: str, max_tokens: int) -> str:
        """Compress text preserving important lines.
        
        Args:
            text: Text to compress
            max_tokens: Maximum tokens allowed
            
        Returns:
            Compressed text
        """
        current_tokens = self.estimate_tokens(text)
        
        if current_tokens <= max_tokens:
            return text
        
        lines = text.split('\n')
        
        if len(lines) <= 10:
            # Too few lines for smart compression
            return self._fallback.compress(text, max_tokens)
        
        # Score each line
        scored_lines = [(i, line, self._score_line(line)) for i, line in enumerate(lines)]
        
        # Sort by score (keep highest)
        sorted_by_score = sorted(scored_lines, key=lambda x: x[2], reverse=True)
        
        # Select lines until we hit token budget
        max_chars = int(max_tokens * self.config.chars_per_token)
        selected_indices = set()
        current_chars = len(self.config.truncation_marker)
        
        for idx, line, score in sorted_by_score:
            line_chars = len(line) + 1  # +1 for newline
            if current_chars + line_chars <= max_chars:
                selected_indices.add(idx)
                current_chars += line_chars
        
        # Rebuild text in original order
        result_lines = []
        last_included = -1
        
        for i in range(len(lines)):
            if i in selected_indices:
                if last_included >= 0 and i - last_included > 1:
                    result_lines.append("...")
                result_lines.append(lines[i])
                last_included = i
        
        return '\n'.join(result_lines)


def get_compressor(compressor_type: str = "truncate") -> ContextCompressor:
    """Get a context compressor by type.
    
    Args:
        compressor_type: One of "truncate", "smart", "llmlingua"
        
    Returns:
        ContextCompressor instance
        
    Raises:
        ValueError: If compressor_type is invalid
    """
    if compressor_type == "truncate":
        return TruncateCompressor()
    
    elif compressor_type == "smart":
        return SmartCompressor()
    
    elif compressor_type == "llmlingua":
        if not _check_llmlingua():
            logger.warning("llmlingua not available, using smart compressor")
            return SmartCompressor()
        # LLMLingua integration would go here
        # For now, fallback to smart
        return SmartCompressor()
    
    else:
        raise ValueError(f"Invalid compressor type: {compressor_type}. Must be 'truncate', 'smart', or 'llmlingua'")


def is_llmlingua_available() -> bool:
    """Check if llmlingua is available.
    
    Returns:
        True if llmlingua is installed
    """
    return _check_llmlingua()
