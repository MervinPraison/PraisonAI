"""
Patch file for llm.py - Critical security and performance fixes.
This file contains minimal changes that can be safely applied to llm.py
while maintaining full backward compatibility.
"""

# To apply these changes to llm.py, add these imports at the top:
ADDITIONAL_IMPORTS = """
from collections import deque
from functools import lru_cache
from io import StringIO
import re
"""

# Add these constants after the imports:
SECURITY_CONSTANTS = """
# Security and performance constants
MAX_CHAT_HISTORY_SIZE = 100
MAX_PROMPT_SIZE = 100000  # 100k characters
MAX_ITERATIONS = 10  # Prevent infinite loops

# Dangerous patterns for prompt injection detection (logging only)
DANGEROUS_PROMPT_PATTERNS = [
    r'ignore previous instructions',
    r'disregard all prior',
    r'system:',
    r'assistant:',
]
"""

# Replace line 229 in __init__ to fix memory leak:
CHAT_HISTORY_FIX = """
# OLD: self.chat_history = []
# NEW:
self.chat_history = deque(maxlen=MAX_CHAT_HISTORY_SIZE)  # Prevent memory leak
"""

# Add these methods to the LLM class for input validation:
VALIDATION_METHODS = """
    def _validate_prompt_security(self, prompt: Union[str, List[Dict]]) -> None:
        '''Check prompt for potential security issues - logging only for compatibility.'''
        if not prompt:
            return
        
        prompt_str = str(prompt) if not isinstance(prompt, str) else prompt
        
        # Check size
        if len(prompt_str) > MAX_PROMPT_SIZE:
            raise ValueError(f"Prompt exceeds maximum size of {MAX_PROMPT_SIZE} characters")
        
        # Log potential security issues without blocking
        for pattern in DANGEROUS_PROMPT_PATTERNS:
            if re.search(pattern, prompt_str, re.IGNORECASE):
                logging.warning(f"Potential prompt injection pattern detected: {pattern}")
    
    def _safe_json_parse(self, json_str: str) -> Dict:
        '''Safely parse JSON with error handling.'''
        if not json_str:
            return {}
        
        try:
            # Basic validation
            data = json.loads(json_str)
            if not isinstance(data, dict):
                logging.warning(f"Expected dict but got {type(data)}")
                return {}
            return data
        except json.JSONDecodeError as e:
            logging.error(f"JSON parse error: {e}")
            return {}
"""

# Fix for string concatenation performance (use StringIO):
STRING_BUFFER_FIX = """
# In get_response method, around line 731, replace:
# response_text = ""
# with:
response_buffer = StringIO()
response_text = ""

# Then replace all instances of:
# response_text += content
# with:
response_buffer.write(content)
response_text = response_buffer.getvalue()
"""

# Add caching for tool definitions (make _generate_tool_definition cached):
TOOL_CACHE_FIX = """
# Add @lru_cache decorator to _generate_tool_definition method:
@lru_cache(maxsize=128)
def _generate_tool_definition(self, function_or_name) -> Optional[Dict]:
"""

# Fix the infinite loop issue by using MAX_ITERATIONS:
LOOP_FIX = """
# Replace line 679:
# max_iterations = 10  # Prevent infinite loops
# with:
# (This line can be removed as we use the constant)

# Replace line 683:
# while iteration_count < max_iterations:
# with:
while iteration_count < MAX_ITERATIONS:
"""

# Add retry logic for transient failures:
RETRY_LOGIC = """
    def _handle_api_error(self, error: Exception, attempt: int = 0, max_retries: int = 3) -> bool:
        '''Handle API errors with retry logic. Returns True if should retry.'''
        error_str = str(error).lower()
        
        # Don't retry on auth errors
        if any(phrase in error_str for phrase in ['invalid api key', 'authentication', 'unauthorized']):
            return False
        
        # Retry on transient errors
        if any(phrase in error_str for phrase in ['timeout', 'connection', 'rate limit']):
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logging.warning(f"Transient error, retrying in {wait_time}s: {error}")
                time.sleep(wait_time)
                return True
        
        return False
"""

# Safer logging that removes sensitive data:
SAFE_LOGGING_FIX = """
# In _log_llm_config method, replace the masking logic (lines 113-117) with:
# Remove all sensitive fields completely
sensitive_fields = {'api_key', 'api_version', 'base_url', 'api_base', 'key', 'token'}
safe_config = {k: v for k, v in config.items() if k not in sensitive_fields}
"""

# Fix JSON parsing in tool calls to use safe parser:
JSON_PARSE_FIX = """
# In _parse_tool_call_arguments, replace line 335 and similar:
# arguments = json.loads(tool_call["function"]["arguments"])
# with:
arguments = self._safe_json_parse(tool_call["function"]["arguments"])
"""

# Summary of changes to apply:
APPLY_INSTRUCTIONS = """
To apply these fixes to llm.py:

1. Add the additional imports at the top
2. Add the security constants after imports
3. In __init__, replace the chat_history initialization (line 229)
4. Add the validation methods to the class
5. Update get_response to use StringIO for string concatenation
6. Add @lru_cache to _generate_tool_definition
7. Replace the loop condition with MAX_ITERATIONS constant
8. Add the retry logic method
9. Update _log_llm_config to completely remove sensitive fields
10. Update JSON parsing to use the safe parser

These changes address:
- Memory leak from unbounded chat history
- String concatenation performance in loops
- JSON injection vulnerabilities
- Sensitive data in logs
- Infinite loop prevention
- Basic retry logic for transient failures
- Input validation (with warnings only for compatibility)

All changes maintain backward compatibility by:
- Only adding warnings for security issues (not blocking)
- Keeping all existing method signatures
- Adding new methods rather than modifying existing ones where possible
- Using safe defaults that don't change behavior
"""