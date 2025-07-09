"""General utility functions for PraisonAI agents.

This module contains utility functions that don't fit into more specific
modules but are used across the codebase.
"""


def clean_triple_backticks(text: str) -> str:
    """Remove triple backticks and surrounding json fences from a string.
    
    This function is useful for cleaning LLM outputs that may include
    markdown code fences around JSON or other content.
    
    Args:
        text: Input text that may contain triple backticks
        
    Returns:
        Cleaned text with backticks removed
        
    Examples:
        >>> clean_triple_backticks("```json\\n{\"key\": \"value\"}\\n```")
        '{"key": "value"}'
        >>> clean_triple_backticks("```\\nsome code\\n```")
        'some code'
    """
    cleaned = text.strip()
    
    # Remove json-specific fences
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    
    # Remove generic fences at start
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    
    # Remove fences at end
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    
    return cleaned


__all__ = [
    'clean_triple_backticks',
]