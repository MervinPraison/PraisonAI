"""
Multi-Search-Replace Diff Strategy for PraisonAI Code.

This module implements a diff strategy that applies SEARCH/REPLACE blocks
to file content with fuzzy matching support, similar to Kilo Code's approach.

Diff Format:
    <<<<<<< SEARCH
    :start_line:N
    -------
    [exact content to find]
    =======
    [new content to replace with]
    >>>>>>> REPLACE
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..utils.text_utils import (
    get_similarity,
    fuzzy_search,
    get_indentation,
)
from ..utils.file_utils import (
    strip_line_numbers,
    every_line_has_line_numbers,
    add_line_numbers,
    detect_line_ending,
)


# Default buffer lines for fuzzy search around start_line hint
BUFFER_LINES = 40


@dataclass
class DiffBlock:
    """
    Represents a single SEARCH/REPLACE block.
    
    Attributes:
        search_content: The content to search for
        replace_content: The content to replace with
        start_line: Optional line number hint (1-indexed)
        end_line: Optional end line hint (1-indexed)
    """
    search_content: str
    replace_content: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None


@dataclass
class DiffResult:
    """
    Result of applying a diff operation.
    
    Attributes:
        success: Whether the diff was applied successfully
        content: The resulting content (if successful)
        error: Error message (if failed)
        applied_count: Number of blocks successfully applied
        failed_blocks: List of failed block results
    """
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    applied_count: int = 0
    failed_blocks: List[dict] = field(default_factory=list)


def _unescape_markers(content: str) -> str:
    """
    Unescape escaped diff markers in content.
    
    Args:
        content: Content with potentially escaped markers
        
    Returns:
        Content with markers unescaped
    """
    replacements = [
        (r'^\\\<\<\<\<\<\<\<', '<<<<<<<'),
        (r'^\\=======', '======='),
        (r'^\\\>\>\>\>\>\>\>', '>>>>>>>'),
        (r'^\\-------', '-------'),
        (r'^\\:end_line:', ':end_line:'),
        (r'^\\:start_line:', ':start_line:'),
    ]
    
    result = content
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.MULTILINE)
    
    return result


def validate_diff_format(diff_content: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a diff string has correct marker sequencing.
    
    Args:
        diff_content: The diff content to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # State machine states
    STATE_START = 0
    STATE_AFTER_SEARCH = 1
    STATE_AFTER_SEPARATOR = 2
    
    state = STATE_START
    line_num = 0
    
    SEARCH_PATTERN = re.compile(r'^<<<<<<< SEARCH>?$')
    SEP = '======='
    REPLACE = '>>>>>>> REPLACE'
    
    lines = diff_content.split('\n')
    
    for line in lines:
        line_num += 1
        marker = line.strip()
        
        # Check for line markers in REPLACE sections
        if state == STATE_AFTER_SEPARATOR:
            if marker.startswith(':start_line:') and not line.strip().startswith('\\:start_line:'):
                return False, f"ERROR: Line marker ':start_line:' found in REPLACE section at line {line_num}"
            if marker.startswith(':end_line:') and not line.strip().startswith('\\:end_line:'):
                return False, f"ERROR: Line marker ':end_line:' found in REPLACE section at line {line_num}"
        
        if state == STATE_START:
            if marker == SEP:
                return False, f"ERROR: Unexpected '=======' at line {line_num}, expected '<<<<<<< SEARCH'"
            if marker == REPLACE:
                return False, f"ERROR: Unexpected '>>>>>>> REPLACE' at line {line_num}"
            if SEARCH_PATTERN.match(marker):
                state = STATE_AFTER_SEARCH
        
        elif state == STATE_AFTER_SEARCH:
            if SEARCH_PATTERN.match(marker):
                return False, f"ERROR: Duplicate '<<<<<<< SEARCH' at line {line_num}"
            if marker == REPLACE:
                return False, f"ERROR: Missing '=======' before '>>>>>>> REPLACE' at line {line_num}"
            if marker == SEP:
                state = STATE_AFTER_SEPARATOR
        
        elif state == STATE_AFTER_SEPARATOR:
            if SEARCH_PATTERN.match(marker):
                return False, f"ERROR: Unexpected '<<<<<<< SEARCH' at line {line_num}, expected '>>>>>>> REPLACE'"
            if marker == SEP:
                return False, f"ERROR: Duplicate '=======' at line {line_num}"
            if marker == REPLACE:
                state = STATE_START
    
    if state != STATE_START:
        expected = "'======='" if state == STATE_AFTER_SEARCH else "'>>>>>>> REPLACE'"
        return False, f"ERROR: Unexpected end of diff, expected {expected}"
    
    return True, None


def parse_diff_blocks(diff_content: str) -> Tuple[List[DiffBlock], Optional[str]]:
    """
    Parse SEARCH/REPLACE blocks from diff content.
    
    Args:
        diff_content: The diff content to parse
        
    Returns:
        Tuple of (list of DiffBlock, error message if any)
    """
    # Validate format first
    is_valid, error = validate_diff_format(diff_content)
    if not is_valid:
        return [], error
    
    # Regex to match SEARCH/REPLACE blocks
    # Groups: 1=start_line line, 2=start_line number, 3=end_line line, 4=end_line number,
    #         5=separator line, 6=search content, 7=replace content
    pattern = re.compile(
        r'(?:^|\n)(?<!\\)<<<<<<< SEARCH>?\s*\n'
        r'((?::start_line:\s*(\d+)\s*\n))?'
        r'((?::end_line:\s*(\d+)\s*\n))?'
        r'((?<!\\)-------\s*\n)?'
        r'([\s\S]*?)(?:\n)?'
        r'(?:(?<=\n)(?<!\\)=======\s*\n)'
        r'([\s\S]*?)(?:\n)?'
        r'(?:(?<=\n)(?<!\\)>>>>>>> REPLACE)(?=\n|$)',
        re.MULTILINE
    )
    
    matches = list(pattern.finditer(diff_content))
    
    if not matches:
        return [], "Invalid diff format - no valid SEARCH/REPLACE blocks found"
    
    blocks = []
    for match in matches:
        start_line = int(match.group(2)) if match.group(2) else None
        end_line = int(match.group(4)) if match.group(4) else None
        search_content = match.group(6) or ""
        replace_content = match.group(7) or ""
        
        blocks.append(DiffBlock(
            search_content=search_content,
            replace_content=replace_content,
            start_line=start_line,
            end_line=end_line,
        ))
    
    # Sort by start_line (blocks without start_line go last)
    blocks.sort(key=lambda b: b.start_line if b.start_line else float('inf'))
    
    return blocks, None


def apply_search_replace_diff(
    original_content: str,
    diff_content: str,
    fuzzy_threshold: float = 1.0,
    buffer_lines: int = BUFFER_LINES,
) -> DiffResult:
    """
    Apply SEARCH/REPLACE diff blocks to original content.
    
    Args:
        original_content: The original file content
        diff_content: The diff content with SEARCH/REPLACE blocks
        fuzzy_threshold: Similarity threshold (0.0-1.0, 1.0 = exact match)
        buffer_lines: Number of lines to search around start_line hint
        
    Returns:
        DiffResult with success status and resulting content
    """
    # Parse diff blocks
    blocks, parse_error = parse_diff_blocks(diff_content)
    if parse_error:
        return DiffResult(success=False, error=parse_error)
    
    if not blocks:
        return DiffResult(
            success=False,
            error="No valid SEARCH/REPLACE blocks found in diff"
        )
    
    # Detect line ending from original content
    line_ending = detect_line_ending(original_content)
    result_lines = original_content.split('\n')
    if original_content.endswith('\n'):
        # Handle trailing newline
        if result_lines and result_lines[-1] == '':
            result_lines = result_lines[:-1]
    
    delta = 0  # Track line number changes from previous replacements
    applied_count = 0
    failed_blocks = []
    
    for block in blocks:
        search_content = _unescape_markers(block.search_content)
        replace_content = _unescape_markers(block.replace_content)
        
        # Handle line numbers in content
        has_all_line_numbers = (
            (every_line_has_line_numbers(search_content) and every_line_has_line_numbers(replace_content)) or
            (every_line_has_line_numbers(search_content) and not replace_content.strip())
        )
        
        start_line = block.start_line
        if has_all_line_numbers and not start_line:
            # Extract start line from first line number in search content
            first_line = search_content.split('\n')[0]
            match = re.match(r'\s*(\d+)', first_line)
            if match:
                start_line = int(match.group(1))
        
        if has_all_line_numbers:
            search_content = strip_line_numbers(search_content)
            replace_content = strip_line_numbers(replace_content)
        
        # Validate search content
        if search_content == replace_content:
            failed_blocks.append({
                'error': 'Search and replace content are identical - no changes would be made',
                'search': search_content[:100],
            })
            continue
        
        search_lines = search_content.split('\n') if search_content else []
        replace_lines = replace_content.split('\n') if replace_content else []
        
        if not search_lines or (len(search_lines) == 1 and not search_lines[0]):
            failed_blocks.append({
                'error': 'Empty search content is not allowed',
            })
            continue
        
        # Apply delta to start_line
        adjusted_start = start_line + delta if start_line else None
        
        # Initialize search
        match_index = -1
        best_score = 0.0
        best_match_content = ""
        search_chunk = '\n'.join(search_lines)
        
        # Determine search bounds
        search_start_index = 0
        search_end_index = len(result_lines)
        
        if adjusted_start:
            # Try exact match at start_line first
            exact_start_index = adjusted_start - 1  # Convert to 0-indexed
            exact_end_index = exact_start_index + len(search_lines)
            
            if 0 <= exact_start_index < len(result_lines):
                original_chunk = '\n'.join(result_lines[exact_start_index:exact_end_index])
                similarity = get_similarity(original_chunk, search_chunk)
                
                if similarity >= fuzzy_threshold:
                    match_index = exact_start_index
                    best_score = similarity
                    best_match_content = original_chunk
                else:
                    # Set bounds for buffered search
                    search_start_index = max(0, adjusted_start - buffer_lines - 1)
                    search_end_index = min(len(result_lines), adjusted_start + len(search_lines) + buffer_lines)
        
        # If no match found yet, try fuzzy search
        if match_index == -1:
            score, idx, content = fuzzy_search(
                result_lines, search_chunk, search_start_index, search_end_index
            )
            match_index = idx
            best_score = score
            best_match_content = content
        
        # Check if match meets threshold
        if match_index == -1 or best_score < fuzzy_threshold:
            # Try aggressive line number stripping as fallback
            aggressive_search = strip_line_numbers(search_content, aggressive=True)
            aggressive_replace = strip_line_numbers(replace_content, aggressive=True)
            
            if aggressive_search != search_content:
                aggressive_lines = aggressive_search.split('\n') if aggressive_search else []
                aggressive_chunk = '\n'.join(aggressive_lines)
                
                score, idx, content = fuzzy_search(
                    result_lines, aggressive_chunk, search_start_index, search_end_index
                )
                
                if idx != -1 and score >= fuzzy_threshold:
                    match_index = idx
                    best_score = score
                    best_match_content = content
                    search_content = aggressive_search
                    replace_content = aggressive_replace
                    search_lines = aggressive_lines
                    replace_lines = replace_content.split('\n') if replace_content else []
        
        # Still no match - report error
        if match_index == -1 or best_score < fuzzy_threshold:
            line_info = f" at line {start_line}" if start_line else ""
            
            # Build context for error message
            context_start = max(0, (adjusted_start or 1) - 1 - buffer_lines)
            context_end = min(len(result_lines), (adjusted_start or 1) + len(search_lines) + buffer_lines)
            original_context = '\n'.join(result_lines[context_start:context_end])
            
            failed_blocks.append({
                'error': f"No sufficiently similar match found{line_info} ({int(best_score * 100)}% similar, needs {int(fuzzy_threshold * 100)}%)",
                'search_content': search_chunk[:200],
                'best_match': best_match_content[:200] if best_match_content else None,
                'similarity': best_score,
                'context': add_line_numbers(original_context, context_start + 1)[:500],
            })
            continue
        
        # Apply the replacement with indentation preservation
        matched_lines = result_lines[match_index:match_index + len(search_lines)]
        
        # Get indentation from original
        original_indents = [get_indentation(line) for line in matched_lines]
        search_indents = [get_indentation(line) for line in search_lines]
        
        # Apply replacement with preserved indentation
        indented_replace_lines = []
        for i, line in enumerate(replace_lines):
            matched_indent = original_indents[0] if original_indents else ""
            current_indent = get_indentation(line)
            search_base_indent = search_indents[0] if search_indents else ""
            
            # Calculate relative indentation
            search_base_level = len(search_base_indent)
            current_level = len(current_indent)
            relative_level = current_level - search_base_level
            
            if relative_level < 0:
                final_indent = matched_indent[:max(0, len(matched_indent) + relative_level)]
            else:
                final_indent = matched_indent + current_indent[search_base_level:]
            
            indented_replace_lines.append(final_indent + line.lstrip())
        
        # Construct final content
        before_match = result_lines[:match_index]
        after_match = result_lines[match_index + len(search_lines):]
        result_lines = before_match + indented_replace_lines + after_match
        
        # Update delta
        delta += len(replace_lines) - len(matched_lines)
        applied_count += 1
    
    # Build final content
    final_content = line_ending.join(result_lines)
    
    if applied_count == 0:
        return DiffResult(
            success=False,
            error="No blocks were successfully applied",
            failed_blocks=failed_blocks,
        )
    
    return DiffResult(
        success=True,
        content=final_content,
        applied_count=applied_count,
        failed_blocks=failed_blocks,
    )
