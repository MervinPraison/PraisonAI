//! Parse Utilities
//!
//! Utility functions for parameter parsing:
//! - URL detection and parsing
//! - Path detection
//! - Typo suggestion (only on error path)
//! - Error message generation
//! - String cleaning utilities

use std::collections::HashSet;

// =============================================================================
// URL Detection
// =============================================================================

/// Detect URL scheme from a string. O(1) operation.
///
/// # Examples
/// ```
/// use praisonai::parity::parse_utils::detect_url_scheme;
///
/// assert_eq!(detect_url_scheme("postgresql://localhost/db"), Some("postgresql".to_string()));
/// assert_eq!(detect_url_scheme("redis://localhost:6379"), Some("redis".to_string()));
/// assert_eq!(detect_url_scheme("not a url"), None);
/// ```
pub fn detect_url_scheme(value: &str) -> Option<String> {
    if !value.contains("://") {
        return None;
    }

    let idx = value.find("://")?;
    if idx > 0 {
        let scheme = &value[..idx];
        // Validate scheme contains only valid characters
        if scheme
            .chars()
            .all(|c| c.is_alphanumeric() || c == '+' || c == '-' || c == '.')
        {
            return Some(scheme.to_lowercase());
        }
    }

    None
}

// =============================================================================
// Path Detection
// =============================================================================

/// Check if a string looks like a file path. O(1) operation.
///
/// # Examples
/// ```
/// use praisonai::parity::parse_utils::is_path_like;
///
/// assert!(is_path_like("docs/"));
/// assert!(is_path_like("./data.pdf"));
/// assert!(!is_path_like("verbose"));
/// ```
pub fn is_path_like(value: &str) -> bool {
    // Check for path indicators
    if value.starts_with("./")
        || value.starts_with("../")
        || value.starts_with('/')
        || value.starts_with("~/")
    {
        return true;
    }

    // Check for directory indicator
    if value.ends_with('/') {
        return true;
    }

    // Check for file extension (common ones)
    if value.contains('.') {
        let ext = value.rsplit('.').next().unwrap_or("").to_lowercase();
        if matches!(
            ext.as_str(),
            "pdf" | "txt" | "md" | "csv" | "json" | "yaml" | "yml" | "docx" | "doc" | "html" | "xml"
        ) {
            return true;
        }
    }

    false
}

/// Check if a string is numeric. O(1) operation.
pub fn is_numeric_string(value: &str) -> bool {
    !value.is_empty() && value.chars().all(|c| c.is_ascii_digit())
}

// =============================================================================
// Policy String Detection
// =============================================================================

/// Check if a string is a policy specification. O(1) operation.
///
/// Policy strings have format: type:action (e.g., "policy:strict", "pii:redact")
///
/// # Examples
/// ```
/// use praisonai::parity::parse_utils::is_policy_string;
///
/// assert!(is_policy_string("policy:strict"));
/// assert!(is_policy_string("pii:redact"));
/// assert!(!is_policy_string("strict"));
/// ```
pub fn is_policy_string(value: &str) -> bool {
    if !value.contains(':') {
        return false;
    }

    let parts: Vec<&str> = value.splitn(2, ':').collect();
    if parts.len() != 2 {
        return false;
    }

    let (policy_type, action) = (parts[0], parts[1]);

    // Policy type should be short identifier (policy, pii, safety, etc.)
    if policy_type.is_empty() || action.is_empty() {
        return false;
    }
    if policy_type.contains(' ') || policy_type.len() > 20 {
        return false;
    }

    true
}

/// Parse a policy string into type and action. O(1) operation.
///
/// # Examples
/// ```
/// use praisonai::parity::parse_utils::parse_policy_string;
///
/// assert_eq!(parse_policy_string("policy:strict"), ("policy", "strict"));
/// assert_eq!(parse_policy_string("pii:redact"), ("pii", "redact"));
/// ```
pub fn parse_policy_string(value: &str) -> (&str, &str) {
    match value.split_once(':') {
        Some((policy_type, action)) => (policy_type, action),
        None => (value, ""),
    }
}

// =============================================================================
// Typo Suggestion
// =============================================================================

/// Find the most similar string from candidates using Levenshtein distance.
///
/// This function is ONLY called on error paths, never on happy paths.
pub fn suggest_similar<'a>(value: &str, candidates: &'a [&str], max_distance: usize) -> Option<&'a str> {
    if value.is_empty() || candidates.is_empty() {
        return None;
    }

    let value_lower = value.to_lowercase();
    let mut best_match = None;
    let mut best_distance = max_distance + 1;

    for candidate in candidates {
        let distance = levenshtein_distance(&value_lower, &candidate.to_lowercase());
        if distance < best_distance {
            best_distance = distance;
            best_match = Some(*candidate);
        }
    }

    if best_distance <= max_distance {
        best_match
    } else {
        None
    }
}

/// Calculate Levenshtein distance between two strings.
///
/// Simple implementation - only used on error paths.
fn levenshtein_distance(s1: &str, s2: &str) -> usize {
    let s1_chars: Vec<char> = s1.chars().collect();
    let s2_chars: Vec<char> = s2.chars().collect();

    if s1_chars.len() < s2_chars.len() {
        return levenshtein_distance(s2, s1);
    }

    if s2_chars.is_empty() {
        return s1_chars.len();
    }

    let mut previous_row: Vec<usize> = (0..=s2_chars.len()).collect();

    for (i, c1) in s1_chars.iter().enumerate() {
        let mut current_row = vec![i + 1];

        for (j, c2) in s2_chars.iter().enumerate() {
            let insertions = previous_row[j + 1] + 1;
            let deletions = current_row[j] + 1;
            let substitutions = previous_row[j] + if c1 != c2 { 1 } else { 0 };
            current_row.push(insertions.min(deletions).min(substitutions));
        }

        previous_row = current_row;
    }

    previous_row[s2_chars.len()]
}

// =============================================================================
// String Cleaning Utilities
// =============================================================================

/// Clean triple backticks from a string (common in LLM outputs)
///
/// Removes markdown code block markers like ```json ... ``` or ```python ... ```
pub fn clean_triple_backticks(text: &str) -> String {
    let text = text.trim();

    // Check if starts with triple backticks
    if !text.starts_with("```") {
        return text.to_string();
    }

    // Find the end of the first line (language specifier)
    let first_newline = text.find('\n').unwrap_or(text.len());
    let after_opening = &text[first_newline..].trim_start();

    // Find closing backticks
    if let Some(closing_idx) = after_opening.rfind("```") {
        after_opening[..closing_idx].trim().to_string()
    } else {
        after_opening.to_string()
    }
}

/// Clean and normalize whitespace in a string
pub fn clean_whitespace(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Extract JSON from a string that may contain markdown code blocks
pub fn extract_json(text: &str) -> Option<&str> {
    let text = text.trim();

    // Try to find JSON object
    if let Some(start) = text.find('{') {
        if let Some(end) = text.rfind('}') {
            if end > start {
                return Some(&text[start..=end]);
            }
        }
    }

    // Try to find JSON array
    if let Some(start) = text.find('[') {
        if let Some(end) = text.rfind(']') {
            if end > start {
                return Some(&text[start..=end]);
            }
        }
    }

    None
}

// =============================================================================
// Validation Utilities
// =============================================================================

/// Validate that all keys in a set are valid
pub fn validate_keys<'a>(
    provided: &HashSet<&'a str>,
    valid: &HashSet<&str>,
) -> Vec<&'a str> {
    provided
        .iter()
        .filter(|k| !valid.contains(*k))
        .copied()
        .collect()
}

/// Create a helpful error message for invalid preset
pub fn make_preset_error(
    param_name: &str,
    value: &str,
    presets: &[&str],
    url_schemes: Option<&[&str]>,
) -> String {
    let mut parts = vec![format!("Invalid {} value: '{}'.", param_name, value)];

    if let Some(suggestion) = suggest_similar(value, presets, 2) {
        parts.push(format!("Did you mean '{}'?", suggestion));
    }

    if !presets.is_empty() {
        parts.push(format!("Valid presets: {}", presets.join(", ")));
    }

    if let Some(schemes) = url_schemes {
        let scheme_examples: Vec<String> = schemes.iter().map(|s| format!("{}://...", s)).collect();
        parts.push(format!("Or use a URL: {}", scheme_examples.join(", ")));
    }

    parts.join(" ")
}

/// Create a helpful error message for invalid array format
pub fn make_array_error(param_name: &str, expected_format: &str) -> String {
    format!(
        "Invalid {} array format. Expected: {}",
        param_name, expected_format
    )
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_url_scheme() {
        assert_eq!(
            detect_url_scheme("postgresql://localhost/db"),
            Some("postgresql".to_string())
        );
        assert_eq!(
            detect_url_scheme("redis://localhost:6379"),
            Some("redis".to_string())
        );
        assert_eq!(detect_url_scheme("not a url"), None);
        assert_eq!(detect_url_scheme("http://example.com"), Some("http".to_string()));
        assert_eq!(detect_url_scheme("https://example.com"), Some("https".to_string()));
    }

    #[test]
    fn test_is_path_like() {
        assert!(is_path_like("docs/"));
        assert!(is_path_like("./data.pdf"));
        assert!(is_path_like("../file.txt"));
        assert!(is_path_like("/absolute/path.json"));
        assert!(is_path_like("~/home/file.yaml"));
        assert!(!is_path_like("verbose"));
        assert!(!is_path_like("some_string"));
    }

    #[test]
    fn test_is_numeric_string() {
        assert!(is_numeric_string("123"));
        assert!(is_numeric_string("0"));
        assert!(!is_numeric_string(""));
        assert!(!is_numeric_string("12.3"));
        assert!(!is_numeric_string("abc"));
    }

    #[test]
    fn test_is_policy_string() {
        assert!(is_policy_string("policy:strict"));
        assert!(is_policy_string("pii:redact"));
        assert!(is_policy_string("safety:block"));
        assert!(!is_policy_string("strict"));
        assert!(!is_policy_string(":action"));
        assert!(!is_policy_string("type:"));
    }

    #[test]
    fn test_parse_policy_string() {
        assert_eq!(parse_policy_string("policy:strict"), ("policy", "strict"));
        assert_eq!(parse_policy_string("pii:redact"), ("pii", "redact"));
        assert_eq!(parse_policy_string("no_colon"), ("no_colon", ""));
    }

    #[test]
    fn test_suggest_similar() {
        let candidates = &["model", "memory", "output", "execution"];
        assert_eq!(suggest_similar("modle", candidates, 2), Some("model"));
        assert_eq!(suggest_similar("mem", candidates, 2), None); // too different
        assert_eq!(suggest_similar("memry", candidates, 2), Some("memory"));
    }

    #[test]
    fn test_levenshtein_distance() {
        assert_eq!(levenshtein_distance("", ""), 0);
        assert_eq!(levenshtein_distance("abc", "abc"), 0);
        assert_eq!(levenshtein_distance("abc", "ab"), 1);
        assert_eq!(levenshtein_distance("abc", "abd"), 1);
        assert_eq!(levenshtein_distance("abc", "xyz"), 3);
    }

    #[test]
    fn test_clean_triple_backticks() {
        let input = "```json\n{\"key\": \"value\"}\n```";
        assert_eq!(clean_triple_backticks(input), "{\"key\": \"value\"}");

        let input2 = "```python\nprint('hello')\n```";
        assert_eq!(clean_triple_backticks(input2), "print('hello')");

        let input3 = "no backticks here";
        assert_eq!(clean_triple_backticks(input3), "no backticks here");
    }

    #[test]
    fn test_clean_whitespace() {
        assert_eq!(clean_whitespace("  hello   world  "), "hello world");
        assert_eq!(clean_whitespace("no\nextra\nspaces"), "no extra spaces");
    }

    #[test]
    fn test_extract_json() {
        assert_eq!(
            extract_json("Some text {\"key\": \"value\"} more text"),
            Some("{\"key\": \"value\"}")
        );
        assert_eq!(
            extract_json("Array: [1, 2, 3] here"),
            Some("[1, 2, 3]")
        );
        assert_eq!(extract_json("no json here"), None);
    }

    #[test]
    fn test_make_preset_error() {
        let error = make_preset_error(
            "output",
            "silnet",
            &["silent", "verbose", "markdown"],
            Some(&["http", "https"]),
        );
        assert!(error.contains("Invalid output value"));
        assert!(error.contains("Did you mean 'silent'"));
    }
}
