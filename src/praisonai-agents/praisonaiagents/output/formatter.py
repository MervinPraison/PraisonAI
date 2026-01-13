"""
Output Formatter for PraisonAI Agents.

Formats output according to style settings.
"""

import re
import json
from typing import Optional, Dict, Any

from .style import OutputStyle


class OutputFormatter:
    """
    Formats agent output according to style settings.
    
    Example:
        style = OutputStyle.concise()
        formatter = OutputFormatter(style)
        formatted = formatter.format(response)
    """
    
    def __init__(self, style: Optional[OutputStyle] = None):
        """
        Initialize the formatter.
        
        Args:
            style: Output style to use
        """
        self.style = style or OutputStyle()
    
    def format(self, text: str) -> str:
        """
        Format text according to style.
        
        Args:
            text: Text to format
            
        Returns:
            Formatted text
        """
        if not text:
            return text
        
        result = text
        
        # Apply length limits
        if self.style.max_length and len(result) > self.style.max_length:
            result = self._truncate(result, self.style.max_length)
        
        # Apply format conversion
        if self.style.format == "plain":
            result = self._to_plain(result)
        elif self.style.format == "json":
            result = self._to_json(result)
        
        return result
    
    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length."""
        if len(text) <= max_length:
            return text
        
        # Try to truncate at sentence boundary
        truncated = text[:max_length]
        
        # Find last sentence end
        for end_char in ['. ', '! ', '? ', '\n']:
            last_end = truncated.rfind(end_char)
            if last_end > max_length * 0.7:  # At least 70% of max
                return truncated[:last_end + 1].strip() + "..."
        
        # Fall back to word boundary
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.8:
            return truncated[:last_space].strip() + "..."
        
        return truncated.strip() + "..."
    
    def _to_plain(self, text: str) -> str:
        """Convert markdown to plain text."""
        result = text
        
        # Remove headers
        result = re.sub(r'^#{1,6}\s+', '', result, flags=re.MULTILINE)
        
        # Remove bold/italic
        result = re.sub(r'\*\*([^*]+)\*\*', r'\1', result)
        result = re.sub(r'\*([^*]+)\*', r'\1', result)
        result = re.sub(r'__([^_]+)__', r'\1', result)
        result = re.sub(r'_([^_]+)_', r'\1', result)
        
        # Remove code blocks (keep content)
        result = re.sub(r'```[a-z]*\n?', '', result)
        
        # Remove inline code
        result = re.sub(r'`([^`]+)`', r'\1', result)
        
        # Remove links (keep text)
        result = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', result)
        
        # Remove horizontal rules
        result = re.sub(r'^---+$', '', result, flags=re.MULTILINE)
        
        # Clean up extra whitespace
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        return result.strip()
    
    def _to_json(self, text: str) -> str:
        """Wrap text in JSON structure."""
        return json.dumps({
            "response": text,
            "format": "text"
        }, indent=2)
    
    def get_word_count(self, text: str) -> int:
        """Get word count of text."""
        return len(text.split())
    
    def get_char_count(self, text: str) -> int:
        """Get character count of text."""
        return len(text)
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Rough estimate: ~4 chars per token
        return len(text) // 4
