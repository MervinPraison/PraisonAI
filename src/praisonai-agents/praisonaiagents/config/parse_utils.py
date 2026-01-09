"""
Parse Utilities for Consolidated Parameter Resolution.

Provides O(1) utility functions for parameter parsing:
- URL detection and parsing
- Path detection
- Typo suggestion (only on error path)
- Error message generation

Performance: All happy-path operations are O(1).
Typo suggestion uses Levenshtein distance only when raising errors.
"""

from typing import Any, Dict, Iterable, Optional


def detect_url_scheme(value: str) -> Optional[str]:
    """
    Detect URL scheme from a string. O(1) operation.
    
    Args:
        value: String to check for URL scheme
        
    Returns:
        Scheme name (lowercase) if URL detected, None otherwise
        
    Examples:
        >>> detect_url_scheme("postgresql://localhost/db")
        'postgresql'
        >>> detect_url_scheme("redis://localhost:6379")
        'redis'
        >>> detect_url_scheme("not a url")
        None
    """
    if not isinstance(value, str):
        return None
    
    # Fast check for :// presence
    if "://" not in value:
        return None
    
    # Extract scheme (everything before ://)
    idx = value.find("://")
    if idx > 0:
        scheme = value[:idx].lower()
        # Validate scheme contains only valid characters
        if scheme.isalnum() or all(c.isalnum() or c in '+-.' for c in scheme):
            return scheme
    
    return None


def parse_url_to_config(
    url: str,
    config_class: type,
    url_schemes: Dict[str, str],
) -> Any:
    """
    Parse a URL string into a config object.
    
    Args:
        url: URL string (e.g., "postgresql://localhost/db")
        config_class: Config dataclass to instantiate
        url_schemes: Mapping of URL schemes to backend names
        
    Returns:
        Config instance with backend and url set
        
    Raises:
        ValueError: If URL scheme is not supported
    """
    scheme = detect_url_scheme(url)
    if not scheme:
        raise ValueError(f"Invalid URL format: {url}")
    
    if scheme not in url_schemes:
        valid_schemes = ", ".join(sorted(url_schemes.keys()))
        raise ValueError(
            f"Unsupported URL scheme '{scheme}' in '{url}'. "
            f"Supported schemes: {valid_schemes}"
        )
    
    backend = url_schemes[scheme]
    
    # Create config with backend and URL in config dict
    return config_class(backend=backend, config={"url": url})


def is_path_like(value: str) -> bool:
    """
    Check if a string looks like a file path. O(1) operation.
    
    Args:
        value: String to check
        
    Returns:
        True if string looks like a path
        
    Examples:
        >>> is_path_like("docs/")
        True
        >>> is_path_like("./data.pdf")
        True
        >>> is_path_like("verbose")
        False
    """
    if not isinstance(value, str):
        return False
    
    # Check for path indicators
    if value.startswith(("./", "../", "/", "~/")):
        return True
    
    # Check for directory indicator
    if value.endswith("/"):
        return True
    
    # Check for file extension (common ones)
    if "." in value:
        ext = value.rsplit(".", 1)[-1].lower()
        if ext in ("pdf", "txt", "md", "csv", "json", "yaml", "yml", "docx", "doc", "html", "xml"):
            return True
    
    return False


def is_numeric_string(value: str) -> bool:
    """
    Check if a string is numeric. O(1) operation.
    
    Args:
        value: String to check
        
    Returns:
        True if string is numeric
    """
    if not isinstance(value, str):
        return False
    return value.isdigit()


def suggest_similar(value: str, candidates: Iterable[str], max_distance: int = 2) -> Optional[str]:
    """
    Find the most similar string from candidates using Levenshtein distance.
    
    This function is ONLY called on error paths, never on happy paths.
    
    Args:
        value: The invalid value
        candidates: Valid options to compare against
        max_distance: Maximum edit distance to consider a match
        
    Returns:
        Most similar candidate if within max_distance, None otherwise
    """
    if not value or not candidates:
        return None
    
    candidates_list = list(candidates)
    if not candidates_list:
        return None
    
    value_lower = value.lower()
    best_match = None
    best_distance = max_distance + 1
    
    for candidate in candidates_list:
        distance = _levenshtein_distance(value_lower, candidate.lower())
        if distance < best_distance:
            best_distance = distance
            best_match = candidate
    
    return best_match if best_distance <= max_distance else None


def _levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance between two strings.
    
    Simple implementation - only used on error paths.
    """
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def make_preset_error(
    param_name: str,
    value: str,
    presets: Iterable[str],
    url_schemes: Optional[Dict[str, str]] = None,
) -> ValueError:
    """
    Create a helpful error message for invalid preset.
    
    Args:
        param_name: Name of the parameter
        value: Invalid value provided
        presets: Valid preset options
        url_schemes: Optional URL schemes if applicable
        
    Returns:
        ValueError with helpful message
    """
    presets_list = list(presets)
    suggestion = suggest_similar(value, presets_list)
    
    msg_parts = [f"Invalid {param_name} value: '{value}'."]
    
    if suggestion:
        msg_parts.append(f"Did you mean '{suggestion}'?")
    
    if presets_list:
        msg_parts.append(f"Valid presets: {', '.join(sorted(presets_list))}")
    
    if url_schemes:
        schemes = ", ".join(f"{k}://..." for k in sorted(url_schemes.keys()))
        msg_parts.append(f"Or use a URL: {schemes}")
    
    return ValueError(" ".join(msg_parts))


def make_array_error(
    param_name: str,
    value: list,
    expected_format: str,
) -> ValueError:
    """
    Create a helpful error message for invalid array format.
    
    Args:
        param_name: Name of the parameter
        value: Invalid array value
        expected_format: Description of expected format
        
    Returns:
        ValueError with helpful message
    """
    return ValueError(
        f"Invalid {param_name} array format: {value}. "
        f"Expected: {expected_format}"
    )


def is_policy_string(value: str) -> bool:
    """
    Check if a string is a policy specification. O(1) operation.
    
    Policy strings have format: type:action (e.g., "policy:strict", "pii:redact")
    
    Args:
        value: String to check
        
    Returns:
        True if string is a policy specification
        
    Examples:
        >>> is_policy_string("policy:strict")
        True
        >>> is_policy_string("pii:redact")
        True
        >>> is_policy_string("strict")
        False
    """
    if not isinstance(value, str):
        return False
    
    # Policy strings have exactly one colon and no spaces before it
    if ":" not in value:
        return False
    
    # Check format: type:action (no spaces, short strings)
    parts = value.split(":", 1)
    if len(parts) != 2:
        return False
    
    policy_type, action = parts
    # Policy type should be short identifier (policy, pii, safety, etc.)
    if not policy_type or not action:
        return False
    if " " in policy_type or len(policy_type) > 20:
        return False
    
    return True


def parse_policy_string(value: str) -> tuple:
    """
    Parse a policy string into type and action. O(1) operation.
    
    Args:
        value: Policy string (e.g., "policy:strict", "pii:redact")
        
    Returns:
        Tuple of (policy_type, action)
        
    Examples:
        >>> parse_policy_string("policy:strict")
        ('policy', 'strict')
        >>> parse_policy_string("pii:redact")
        ('pii', 'redact')
    """
    parts = value.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (value, "")


def merge_config_with_overrides(
    base_config: Any,
    overrides: Dict[str, Any],
    config_class: type,
) -> Any:
    """
    Merge a base config with override dict.
    
    Args:
        base_config: Base config instance
        overrides: Dict of field overrides
        config_class: Config class for creating new instance
        
    Returns:
        New config instance with overrides applied
    """
    # Get base values as dict
    if hasattr(base_config, '__dataclass_fields__'):
        # Dataclass
        from dataclasses import asdict
        base_dict = asdict(base_config)
    elif hasattr(base_config, '__dict__'):
        base_dict = dict(base_config.__dict__)
    else:
        base_dict = {}
    
    # Apply overrides
    base_dict.update(overrides)
    
    # Create new instance
    return config_class(**base_dict)
