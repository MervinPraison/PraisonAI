"""
Text utility functions for PraisonAI Code module.

Provides utilities for text processing including:
- String normalization (smart quotes, unicode)
- HTML entity unescaping
- Similarity calculation using Levenshtein distance
"""

import html
import re
import unicodedata


def normalize_string(text: str) -> str:
    """
    Normalize a string for comparison.
    
    Handles:
    - Smart quotes to regular quotes
    - Unicode normalization
    - Consistent whitespace
    
    Args:
        text: The text to normalize
        
    Returns:
        Normalized text string
    """
    if not text:
        return ""
    
    # Unicode normalization (NFC form)
    normalized = unicodedata.normalize('NFC', text)
    
    # Replace smart quotes with regular quotes
    quote_replacements = {
        '\u2018': "'",  # Left single quote
        '\u2019': "'",  # Right single quote
        '\u201C': '"',  # Left double quote
        '\u201D': '"',  # Right double quote
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u2026': '...',  # Ellipsis
    }
    
    for smart, regular in quote_replacements.items():
        normalized = normalized.replace(smart, regular)
    
    return normalized


def unescape_html_entities(text: str) -> str:
    """
    Unescape HTML entities in text.
    
    Args:
        text: Text with HTML entities
        
    Returns:
        Text with entities converted to characters
        
    Example:
        >>> unescape_html_entities("&lt;div&gt;")
        '<div>'
    """
    if not text:
        return ""
    return html.unescape(text)


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate the Levenshtein distance between two strings.
    
    This is the minimum number of single-character edits (insertions,
    deletions, or substitutions) required to change one string into the other.
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        The edit distance between the strings
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def get_similarity(original: str, search: str) -> float:
    """
    Calculate similarity ratio between two strings using Levenshtein distance.
    
    Args:
        original: The original string
        search: The string to compare against
        
    Returns:
        Similarity ratio from 0.0 (completely different) to 1.0 (identical)
    """
    if not search:
        return 0.0
    
    # Normalize both strings for comparison
    normalized_original = normalize_string(original)
    normalized_search = normalize_string(search)
    
    if normalized_original == normalized_search:
        return 1.0
    
    # Calculate Levenshtein distance
    dist = levenshtein_distance(normalized_original, normalized_search)
    
    # Calculate similarity ratio
    max_length = max(len(normalized_original), len(normalized_search))
    if max_length == 0:
        return 1.0
    
    return 1.0 - (dist / max_length)


def fuzzy_search(
    lines: list,
    search_chunk: str,
    start_index: int,
    end_index: int
) -> tuple:
    """
    Perform a middle-out fuzzy search to find the best match for search_chunk.
    
    Searches outward from the middle of the range to find the slice of lines
    that is most similar to the search chunk.
    
    Args:
        lines: List of lines to search in
        search_chunk: The text to search for
        start_index: Start of search range (inclusive)
        end_index: End of search range (exclusive)
        
    Returns:
        Tuple of (best_score, best_match_index, best_match_content)
    """
    best_score = 0.0
    best_match_index = -1
    best_match_content = ""
    
    search_lines = search_chunk.split('\n')
    search_len = len(search_lines)
    
    if search_len == 0:
        return (0.0, -1, "")
    
    # Middle-out search from the midpoint
    mid_point = (start_index + end_index) // 2
    left_index = mid_point
    right_index = mid_point + 1
    
    while left_index >= start_index or right_index <= end_index - search_len:
        # Check left side
        if left_index >= start_index:
            original_chunk = '\n'.join(lines[left_index:left_index + search_len])
            similarity = get_similarity(original_chunk, search_chunk)
            if similarity > best_score:
                best_score = similarity
                best_match_index = left_index
                best_match_content = original_chunk
            left_index -= 1
        
        # Check right side
        if right_index <= end_index - search_len:
            original_chunk = '\n'.join(lines[right_index:right_index + search_len])
            similarity = get_similarity(original_chunk, search_chunk)
            if similarity > best_score:
                best_score = similarity
                best_match_index = right_index
                best_match_content = original_chunk
            right_index += 1
    
    return (best_score, best_match_index, best_match_content)


def strip_markdown_code_fences(content: str) -> str:
    """
    Strip markdown code fences from content.
    
    Handles content that starts with ```language and ends with ```.
    
    Args:
        content: Content potentially wrapped in code fences
        
    Returns:
        Content with code fences removed
    """
    if not content:
        return ""
    
    lines = content.split('\n')
    
    # Check if starts with code fence
    if lines and lines[0].strip().startswith('```'):
        lines = lines[1:]
    
    # Check if ends with code fence
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    
    return '\n'.join(lines)


def get_indentation(line: str) -> str:
    """
    Extract the leading whitespace (indentation) from a line.
    
    Args:
        line: The line to extract indentation from
        
    Returns:
        The leading whitespace string (tabs and/or spaces)
    """
    match = re.match(r'^[\t ]*', line)
    return match.group(0) if match else ""


def preserve_indentation(original_lines: list, replacement_lines: list) -> list:
    """
    Apply replacement lines while preserving the indentation from original.
    
    Args:
        original_lines: The original lines being replaced
        replacement_lines: The new lines to insert
        
    Returns:
        Replacement lines with adjusted indentation
    """
    if not original_lines or not replacement_lines:
        return replacement_lines
    
    # Get base indentation from first original line
    original_base_indent = get_indentation(original_lines[0])
    
    # Get base indentation from first replacement line
    replacement_base_indent = get_indentation(replacement_lines[0])
    
    result = []
    for line in replacement_lines:
        current_indent = get_indentation(line)
        content = line.lstrip()
        
        # Calculate relative indentation
        if len(current_indent) >= len(replacement_base_indent):
            relative_indent = current_indent[len(replacement_base_indent):]
            new_indent = original_base_indent + relative_indent
        else:
            # Line has less indentation than base, adjust accordingly
            new_indent = original_base_indent[:max(0, len(original_base_indent) - (len(replacement_base_indent) - len(current_indent)))]
        
        result.append(new_indent + content)
    
    return result
