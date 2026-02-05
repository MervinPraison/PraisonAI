//! Parameter Resolver
//!
//! Unified parameter resolution following precedence rules:
//! Instance > Config > Dict > Array > String > Bool > Default

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// Array Modes
// =============================================================================

/// Array parsing modes for parameter resolution
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ArrayMode {
    /// Return list as-is (e.g., hooks)
    #[default]
    Passthrough,
    /// List of source paths/URLs
    Sources,
    /// Sources + optional config dict at end
    SourcesWithConfig,
    /// [preset, {overrides}]
    PresetOverride,
    /// Single item treated as scalar, else list
    SingleOrList,
    /// List of step names (workflow context/routing)
    StepNames,
}

// =============================================================================
// Resolved Value
// =============================================================================

/// Result of parameter resolution
#[derive(Debug, Clone)]
pub enum ResolvedValue {
    /// No value (disabled or unset)
    None,
    /// Boolean value
    Bool(bool),
    /// String value
    String(String),
    /// List of strings
    List(Vec<String>),
    /// Dictionary/object value
    Dict(HashMap<String, serde_json::Value>),
    /// JSON value (for complex configs)
    Json(serde_json::Value),
}

impl ResolvedValue {
    /// Check if value is none/disabled
    pub fn is_none(&self) -> bool {
        matches!(self, Self::None)
    }

    /// Check if value is enabled (not none)
    pub fn is_some(&self) -> bool {
        !self.is_none()
    }

    /// Get as bool
    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Self::Bool(b) => Some(*b),
            _ => None,
        }
    }

    /// Get as string
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Self::String(s) => Some(s),
            _ => None,
        }
    }

    /// Get as list
    pub fn as_list(&self) -> Option<&[String]> {
        match self {
            Self::List(l) => Some(l),
            _ => None,
        }
    }

    /// Convert to JSON value
    pub fn to_json(&self) -> serde_json::Value {
        match self {
            Self::None => serde_json::Value::Null,
            Self::Bool(b) => serde_json::Value::Bool(*b),
            Self::String(s) => serde_json::Value::String(s.clone()),
            Self::List(l) => serde_json::json!(l),
            Self::Dict(d) => serde_json::json!(d),
            Self::Json(v) => v.clone(),
        }
    }
}

impl Default for ResolvedValue {
    fn default() -> Self {
        Self::None
    }
}

// =============================================================================
// Resolution Options
// =============================================================================

/// Options for parameter resolution
#[derive(Debug, Clone, Default)]
pub struct ResolveOptions {
    /// Parameter name (for error messages)
    pub param_name: String,
    /// Valid presets
    pub presets: HashMap<String, serde_json::Value>,
    /// URL schemes mapping
    pub url_schemes: HashMap<String, String>,
    /// Array handling mode
    pub array_mode: ArrayMode,
    /// String handling mode
    pub string_mode: Option<StringMode>,
    /// Default value
    pub default: Option<ResolvedValue>,
}

/// String handling modes
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StringMode {
    /// Treat path-like strings as sources
    PathAsSource,
    /// Treat string as LLM model name
    LlmModel,
    /// Treat string as LLM prompt
    LlmPrompt,
}

// =============================================================================
// Main Resolver Function
// =============================================================================

/// Resolve a parameter value following precedence rules
///
/// Precedence: Instance > Config > Array > Dict > String > Bool > Default
pub fn resolve(value: &serde_json::Value, options: &ResolveOptions) -> ResolvedValue {
    // 1. None/null -> Default
    if value.is_null() {
        return options.default.clone().unwrap_or(ResolvedValue::None);
    }

    // 2. Array handling
    if let Some(arr) = value.as_array() {
        return resolve_array(arr, options);
    }

    // 3. Dict/Object handling
    if let Some(obj) = value.as_object() {
        let dict: HashMap<String, serde_json::Value> = obj
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        return ResolvedValue::Dict(dict);
    }

    // 4. String handling
    if let Some(s) = value.as_str() {
        return resolve_string(s, options);
    }

    // 5. Bool handling
    if let Some(b) = value.as_bool() {
        if b {
            // True -> return default config or true
            return options.default.clone().unwrap_or(ResolvedValue::Bool(true));
        } else {
            // False -> disabled
            return ResolvedValue::None;
        }
    }

    // 6. Number or other -> wrap as JSON
    ResolvedValue::Json(value.clone())
}

/// Resolve array value based on array_mode
fn resolve_array(arr: &[serde_json::Value], options: &ResolveOptions) -> ResolvedValue {
    // Empty array -> disabled
    if arr.is_empty() {
        return ResolvedValue::None;
    }

    match options.array_mode {
        ArrayMode::Passthrough => {
            // Return as JSON array
            ResolvedValue::Json(serde_json::Value::Array(arr.to_vec()))
        }
        ArrayMode::Sources | ArrayMode::StepNames => {
            // Convert to list of strings
            let strings: Vec<String> = arr
                .iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect();
            ResolvedValue::List(strings)
        }
        ArrayMode::SourcesWithConfig => {
            // Sources + optional config dict at end
            let mut sources = Vec::new();
            let mut config = HashMap::new();

            for item in arr {
                if let Some(obj) = item.as_object() {
                    // Dict item - merge into config
                    for (k, v) in obj {
                        config.insert(k.clone(), v.clone());
                    }
                } else if let Some(s) = item.as_str() {
                    sources.push(s.to_string());
                }
            }

            if config.is_empty() {
                ResolvedValue::List(sources)
            } else {
                config.insert("sources".to_string(), serde_json::json!(sources));
                ResolvedValue::Dict(config)
            }
        }
        ArrayMode::SingleOrList => {
            if arr.len() == 1 {
                // Single item - resolve as scalar
                resolve(&arr[0], options)
            } else {
                // Multiple items - return as list
                let strings: Vec<String> = arr
                    .iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect();
                ResolvedValue::List(strings)
            }
        }
        ArrayMode::PresetOverride => {
            // [preset, {overrides}] or [preset]
            if arr.is_empty() {
                return ResolvedValue::None;
            }

            let first = &arr[0];
            if let Some(preset_name) = first.as_str() {
                // Look up preset
                let base = options
                    .presets
                    .get(preset_name)
                    .cloned()
                    .unwrap_or(serde_json::Value::Null);

                // Apply overrides if present
                if arr.len() >= 2 {
                    if let Some(overrides) = arr.last().and_then(|v| v.as_object()) {
                        if let Some(base_obj) = base.as_object() {
                            let mut merged: HashMap<String, serde_json::Value> = base_obj
                                .iter()
                                .map(|(k, v)| (k.clone(), v.clone()))
                                .collect();
                            for (k, v) in overrides {
                                merged.insert(k.clone(), v.clone());
                            }
                            return ResolvedValue::Dict(merged);
                        }
                    }
                }

                if base.is_null() {
                    ResolvedValue::String(preset_name.to_string())
                } else {
                    ResolvedValue::Json(base)
                }
            } else {
                ResolvedValue::Json(serde_json::Value::Array(arr.to_vec()))
            }
        }
    }
}

/// Resolve string value
fn resolve_string(s: &str, options: &ResolveOptions) -> ResolvedValue {
    // Check for URL
    if let Some(scheme) = detect_url_scheme(s) {
        if let Some(backend) = options.url_schemes.get(&scheme) {
            let mut config = HashMap::new();
            config.insert("backend".to_string(), serde_json::json!(backend));
            config.insert("url".to_string(), serde_json::json!(s));
            return ResolvedValue::Dict(config);
        }
    }

    // Check for preset (case-insensitive)
    let s_lower = s.to_lowercase();
    for (preset_name, preset_value) in &options.presets {
        if preset_name.to_lowercase() == s_lower {
            return ResolvedValue::Json(preset_value.clone());
        }
    }

    // Handle string modes
    if let Some(mode) = options.string_mode {
        match mode {
            StringMode::PathAsSource => {
                if is_path_like(s) {
                    return ResolvedValue::List(vec![s.to_string()]);
                }
            }
            StringMode::LlmModel => {
                let mut config = HashMap::new();
                config.insert("llm".to_string(), serde_json::json!(s));
                return ResolvedValue::Dict(config);
            }
            StringMode::LlmPrompt => {
                let mut config = HashMap::new();
                config.insert("llm_validator".to_string(), serde_json::json!(s));
                return ResolvedValue::Dict(config);
            }
        }
    }

    // Return as string
    ResolvedValue::String(s.to_string())
}

// =============================================================================
// URL Detection
// =============================================================================

/// Detect URL scheme from a string
pub fn detect_url_scheme(value: &str) -> Option<String> {
    if !value.contains("://") {
        return None;
    }

    let idx = value.find("://")?;
    if idx > 0 {
        let scheme = &value[..idx];
        // Validate scheme contains only valid characters
        if scheme.chars().all(|c| c.is_alphanumeric() || c == '+' || c == '-' || c == '.') {
            return Some(scheme.to_lowercase());
        }
    }

    None
}

/// Check if a string looks like a file path
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

    // Check for common file extensions
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

// =============================================================================
// Convenience Resolver Functions
// =============================================================================

/// Resolve memory parameter
pub fn resolve_memory(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "memory".to_string(),
        array_mode: ArrayMode::SingleOrList,
        ..Default::default()
    };

    // Add memory presets
    options.presets.insert(
        "default".to_string(),
        serde_json::json!({"enabled": true}),
    );
    options.presets.insert(
        "long_term".to_string(),
        serde_json::json!({"enabled": true, "use_long_term": true}),
    );

    // Add URL schemes
    options.url_schemes.insert("postgresql".to_string(), "postgres".to_string());
    options.url_schemes.insert("postgres".to_string(), "postgres".to_string());
    options.url_schemes.insert("redis".to_string(), "redis".to_string());
    options.url_schemes.insert("sqlite".to_string(), "sqlite".to_string());

    resolve(value, &options)
}

/// Resolve knowledge parameter
pub fn resolve_knowledge(value: &serde_json::Value) -> ResolvedValue {
    let options = ResolveOptions {
        param_name: "knowledge".to_string(),
        array_mode: ArrayMode::SourcesWithConfig,
        string_mode: Some(StringMode::PathAsSource),
        ..Default::default()
    };

    resolve(value, &options)
}

/// Resolve output parameter
pub fn resolve_output(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "output".to_string(),
        array_mode: ArrayMode::PresetOverride,
        ..Default::default()
    };

    // Add output presets
    options.presets.insert(
        "silent".to_string(),
        serde_json::json!({"verbose": false, "stream": false}),
    );
    options.presets.insert(
        "verbose".to_string(),
        serde_json::json!({"verbose": true, "stream": true}),
    );
    options.presets.insert(
        "markdown".to_string(),
        serde_json::json!({"markdown": true}),
    );

    resolve(value, &options)
}

/// Resolve execution parameter
pub fn resolve_execution(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "execution".to_string(),
        array_mode: ArrayMode::PresetOverride,
        ..Default::default()
    };

    // Add execution presets
    options.presets.insert(
        "fast".to_string(),
        serde_json::json!({"max_iter": 5, "max_execution_time": 60}),
    );
    options.presets.insert(
        "thorough".to_string(),
        serde_json::json!({"max_iter": 25, "max_execution_time": 300}),
    );

    resolve(value, &options)
}

/// Resolve planning parameter
pub fn resolve_planning(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "planning".to_string(),
        array_mode: ArrayMode::PresetOverride,
        string_mode: Some(StringMode::LlmModel),
        ..Default::default()
    };

    options.presets.insert(
        "default".to_string(),
        serde_json::json!({"enabled": true}),
    );

    resolve(value, &options)
}

/// Resolve reflection parameter
pub fn resolve_reflection(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "reflection".to_string(),
        array_mode: ArrayMode::PresetOverride,
        ..Default::default()
    };

    options.presets.insert(
        "default".to_string(),
        serde_json::json!({"enabled": true, "max_reflect": 3}),
    );

    resolve(value, &options)
}

/// Resolve context parameter
pub fn resolve_context(value: &serde_json::Value) -> ResolvedValue {
    let options = ResolveOptions {
        param_name: "context".to_string(),
        array_mode: ArrayMode::StepNames,
        ..Default::default()
    };

    resolve(value, &options)
}

/// Resolve routing parameter
pub fn resolve_routing(value: &serde_json::Value) -> ResolvedValue {
    let options = ResolveOptions {
        param_name: "routing".to_string(),
        array_mode: ArrayMode::StepNames,
        ..Default::default()
    };

    resolve(value, &options)
}

/// Resolve hooks parameter
pub fn resolve_hooks(value: &serde_json::Value) -> ResolvedValue {
    let options = ResolveOptions {
        param_name: "hooks".to_string(),
        array_mode: ArrayMode::Passthrough,
        ..Default::default()
    };

    resolve(value, &options)
}

/// Resolve guardrails parameter
pub fn resolve_guardrails(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "guardrails".to_string(),
        array_mode: ArrayMode::PresetOverride,
        string_mode: Some(StringMode::LlmPrompt),
        ..Default::default()
    };

    options.presets.insert(
        "strict".to_string(),
        serde_json::json!({"enabled": true, "max_retries": 3}),
    );

    resolve(value, &options)
}

/// Resolve web parameter
pub fn resolve_web(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "web".to_string(),
        array_mode: ArrayMode::PresetOverride,
        ..Default::default()
    };

    options.presets.insert(
        "default".to_string(),
        serde_json::json!({"enabled": true, "search": true, "fetch": true}),
    );

    resolve(value, &options)
}

/// Resolve autonomy parameter
pub fn resolve_autonomy(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "autonomy".to_string(),
        array_mode: ArrayMode::PresetOverride,
        ..Default::default()
    };

    options.presets.insert(
        "full".to_string(),
        serde_json::json!({"enabled": true, "max_steps": 100}),
    );
    options.presets.insert(
        "limited".to_string(),
        serde_json::json!({"enabled": true, "max_steps": 10, "approval_required": true}),
    );

    resolve(value, &options)
}

/// Resolve caching parameter
pub fn resolve_caching(value: &serde_json::Value) -> ResolvedValue {
    let mut options = ResolveOptions {
        param_name: "caching".to_string(),
        ..Default::default()
    };

    options.presets.insert(
        "default".to_string(),
        serde_json::json!({"enabled": true, "prompt_caching": true}),
    );

    resolve(value, &options)
}

/// Resolve skills parameter
pub fn resolve_skills(value: &serde_json::Value) -> ResolvedValue {
    let options = ResolveOptions {
        param_name: "skills".to_string(),
        array_mode: ArrayMode::Sources,
        string_mode: Some(StringMode::PathAsSource),
        ..Default::default()
    };

    resolve(value, &options)
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_null() {
        let options = ResolveOptions::default();
        let result = resolve(&serde_json::Value::Null, &options);
        assert!(result.is_none());
    }

    #[test]
    fn test_resolve_bool_true() {
        let options = ResolveOptions {
            default: Some(ResolvedValue::Dict(HashMap::new())),
            ..Default::default()
        };
        let result = resolve(&serde_json::json!(true), &options);
        assert!(result.is_some());
    }

    #[test]
    fn test_resolve_bool_false() {
        let options = ResolveOptions::default();
        let result = resolve(&serde_json::json!(false), &options);
        assert!(result.is_none());
    }

    #[test]
    fn test_resolve_string() {
        let options = ResolveOptions::default();
        let result = resolve(&serde_json::json!("test"), &options);
        assert_eq!(result.as_str(), Some("test"));
    }

    #[test]
    fn test_resolve_array_passthrough() {
        let options = ResolveOptions {
            array_mode: ArrayMode::Passthrough,
            ..Default::default()
        };
        let result = resolve(&serde_json::json!(["a", "b", "c"]), &options);
        assert!(matches!(result, ResolvedValue::Json(_)));
    }

    #[test]
    fn test_resolve_array_sources() {
        let options = ResolveOptions {
            array_mode: ArrayMode::Sources,
            ..Default::default()
        };
        let result = resolve(&serde_json::json!(["file1.txt", "file2.txt"]), &options);
        assert_eq!(result.as_list(), Some(&["file1.txt".to_string(), "file2.txt".to_string()][..]));
    }

    #[test]
    fn test_detect_url_scheme() {
        assert_eq!(detect_url_scheme("postgresql://localhost/db"), Some("postgresql".to_string()));
        assert_eq!(detect_url_scheme("redis://localhost:6379"), Some("redis".to_string()));
        assert_eq!(detect_url_scheme("not a url"), None);
    }

    #[test]
    fn test_is_path_like() {
        assert!(is_path_like("./data.txt"));
        assert!(is_path_like("../file.pdf"));
        assert!(is_path_like("/absolute/path.json"));
        assert!(is_path_like("docs/"));
        assert!(!is_path_like("verbose"));
    }

    #[test]
    fn test_resolve_memory_url() {
        let result = resolve_memory(&serde_json::json!("postgresql://localhost/db"));
        if let ResolvedValue::Dict(d) = result {
            assert_eq!(d.get("backend").and_then(|v| v.as_str()), Some("postgres"));
        } else {
            panic!("Expected Dict");
        }
    }

    #[test]
    fn test_resolve_output_preset() {
        let result = resolve_output(&serde_json::json!("silent"));
        if let ResolvedValue::Json(v) = result {
            assert_eq!(v.get("verbose").and_then(|v| v.as_bool()), Some(false));
        } else {
            panic!("Expected Json");
        }
    }
}
