//! Configuration Loader
//!
//! Loads configuration from multiple sources with precedence:
//! 1. Explicit parameters (highest)
//! 2. Environment variables
//! 3. Config file (.praisonai/config.toml or praisonai.toml)
//! 4. Defaults (lowest)

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

// =============================================================================
// Config Types
// =============================================================================

/// Configuration validation error
#[derive(Debug, Clone, thiserror::Error)]
pub enum ConfigValidationError {
    /// Unknown key in config
    #[error("Unknown key '{key}' in section [{section}]. Did you mean '{suggestion:?}'?")]
    UnknownKey {
        section: String,
        key: String,
        suggestion: Option<String>,
    },
    /// Invalid type
    #[error("Invalid type for [{section}.{key}]: expected {expected}, got {actual}")]
    InvalidType {
        section: String,
        key: String,
        expected: String,
        actual: String,
    },
    /// Multiple errors
    #[error("Config validation failed:\n{}", .0.iter().map(|e| format!("  - {}", e)).collect::<Vec<_>>().join("\n"))]
    Multiple(Vec<ConfigValidationError>),
}

/// Plugins configuration
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PluginsConfig {
    /// Whether plugins are enabled (bool, list of names, or "true"/"false")
    #[serde(default)]
    pub enabled: PluginsEnabled,
    /// Whether to auto-discover plugins
    #[serde(default = "default_true")]
    pub auto_discover: bool,
    /// Plugin directories
    #[serde(default = "default_plugin_dirs")]
    pub directories: Vec<String>,
}

fn default_true() -> bool {
    true
}

fn default_plugin_dirs() -> Vec<String> {
    vec![
        "./.praisonai/plugins/".to_string(),
        "~/.praisonai/plugins/".to_string(),
    ]
}

/// Plugins enabled state
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum PluginsEnabled {
    /// Boolean enabled/disabled
    Bool(bool),
    /// List of specific plugin names
    List(Vec<String>),
}

impl Default for PluginsEnabled {
    fn default() -> Self {
        Self::Bool(false)
    }
}

impl PluginsEnabled {
    /// Check if plugins are enabled
    pub fn is_enabled(&self) -> bool {
        match self {
            Self::Bool(b) => *b,
            Self::List(list) => !list.is_empty(),
        }
    }

    /// Get list of enabled plugins (None if all enabled)
    pub fn get_list(&self) -> Option<&[String]> {
        match self {
            Self::Bool(_) => None,
            Self::List(list) => Some(list),
        }
    }
}

/// Defaults configuration for Agent parameters
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DefaultsConfig {
    /// Default LLM model
    pub model: Option<String>,
    /// Default base URL
    pub base_url: Option<String>,
    /// Default API key (not recommended in config)
    pub api_key: Option<String>,
    /// Allow delegation
    #[serde(default)]
    pub allow_delegation: bool,
    /// Allow code execution
    #[serde(default)]
    pub allow_code_execution: bool,
    /// Code execution mode
    #[serde(default = "default_code_execution_mode")]
    pub code_execution_mode: String,
    /// Memory configuration
    pub memory: Option<serde_json::Value>,
    /// Knowledge configuration
    pub knowledge: Option<serde_json::Value>,
    /// Planning configuration
    pub planning: Option<serde_json::Value>,
    /// Reflection configuration
    pub reflection: Option<serde_json::Value>,
    /// Guardrails configuration
    pub guardrails: Option<serde_json::Value>,
    /// Web configuration
    pub web: Option<serde_json::Value>,
    /// Output configuration
    pub output: Option<serde_json::Value>,
    /// Execution configuration
    pub execution: Option<serde_json::Value>,
    /// Caching configuration
    pub caching: Option<serde_json::Value>,
    /// Autonomy configuration
    pub autonomy: Option<serde_json::Value>,
    /// Skills configuration
    pub skills: Option<serde_json::Value>,
    /// Context configuration
    pub context: Option<serde_json::Value>,
    /// Hooks configuration
    pub hooks: Option<serde_json::Value>,
    /// Templates configuration
    pub templates: Option<serde_json::Value>,
}

fn default_code_execution_mode() -> String {
    "safe".to_string()
}

/// Manager configuration for multi-agent workflows
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ManagerConfig {
    /// Manager LLM model
    pub llm: Option<String>,
    /// Maximum iterations
    pub max_iter: Option<usize>,
    /// Verbose output
    #[serde(default)]
    pub verbose: bool,
}

/// Session configuration
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SessionConfig {
    /// Session ID
    pub session_id: Option<String>,
    /// User ID
    pub user_id: Option<String>,
    /// Persist session
    #[serde(default)]
    pub persist: bool,
    /// Session storage path
    pub storage_path: Option<String>,
}

/// AutoRAG configuration
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AutoRagConfig {
    /// Enable AutoRAG
    #[serde(default)]
    pub enabled: bool,
    /// Chunk size
    pub chunk_size: Option<usize>,
    /// Chunk overlap
    pub chunk_overlap: Option<usize>,
    /// Embedding model
    pub embedding_model: Option<String>,
    /// Vector store backend
    pub vector_store: Option<String>,
}

/// Root configuration for PraisonAI
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PraisonConfig {
    /// Plugins configuration
    #[serde(default)]
    pub plugins: PluginsConfig,
    /// Defaults configuration
    #[serde(default)]
    pub defaults: DefaultsConfig,
}

impl PraisonConfig {
    /// Convert to dictionary
    pub fn to_dict(&self) -> serde_json::Value {
        serde_json::to_value(self).unwrap_or_default()
    }
}

// =============================================================================
// Config Loading Functions
// =============================================================================

/// Global config cache
static CONFIG_CACHE: OnceLock<PraisonConfig> = OnceLock::new();

/// Find config file in standard locations
fn find_config_file() -> Option<PathBuf> {
    let cwd = std::env::current_dir().ok()?;
    
    // Project-local locations
    let local_paths = [
        cwd.join(".praisonai").join("config.toml"),
        cwd.join("praisonai.toml"),
    ];
    
    for path in &local_paths {
        if path.exists() {
            return Some(path.clone());
        }
    }
    
    // User global location
    if let Some(home) = dirs::home_dir() {
        let global_path = home.join(".praisonai").join("config.toml");
        if global_path.exists() {
            return Some(global_path);
        }
    }
    
    None
}

/// Load configuration from file
fn load_config_from_file() -> PraisonConfig {
    let config_path = match find_config_file() {
        Some(path) => path,
        None => return PraisonConfig::default(),
    };
    
    let content = match std::fs::read_to_string(&config_path) {
        Ok(c) => c,
        Err(_) => return PraisonConfig::default(),
    };
    
    // Parse TOML
    match toml::from_str(&content) {
        Ok(config) => config,
        Err(e) => {
            tracing::warn!("Failed to parse config from {:?}: {}", config_path, e);
            PraisonConfig::default()
        }
    }
}

/// Get the global configuration
///
/// Loads config lazily on first access and caches it.
pub fn get_config() -> &'static PraisonConfig {
    CONFIG_CACHE.get_or_init(load_config_from_file)
}

/// Get config path if it exists
pub fn get_config_path() -> Option<PathBuf> {
    find_config_file()
}

/// Get plugins configuration
pub fn get_plugins_config() -> &'static PluginsConfig {
    &get_config().plugins
}

/// Get defaults configuration
pub fn get_defaults_config() -> &'static DefaultsConfig {
    &get_config().defaults
}

/// Get a specific default value
///
/// Supports nested keys like "memory.backend"
pub fn get_default<T: serde::de::DeserializeOwned>(key: &str, fallback: T) -> T {
    let defaults = get_defaults_config();
    let value = serde_json::to_value(defaults).unwrap_or_default();
    
    // Handle nested keys
    let parts: Vec<&str> = key.split('.').collect();
    let mut current = &value;
    
    for part in parts {
        match current.get(part) {
            Some(v) => current = v,
            None => return fallback,
        }
    }
    
    serde_json::from_value(current.clone()).unwrap_or(fallback)
}

/// Check if plugins are enabled via config or env var
pub fn is_plugins_enabled() -> bool {
    // Check env var first (highest precedence)
    if let Ok(env_value) = std::env::var("PRAISONAI_PLUGINS") {
        let lower = env_value.to_lowercase();
        if matches!(lower.as_str(), "true" | "1" | "yes" | "on") {
            return true;
        }
        if matches!(lower.as_str(), "false" | "0" | "no" | "off") {
            return false;
        }
        // Treat as comma-separated list of plugin names
        return true;
    }
    
    // Check config file
    get_plugins_config().enabled.is_enabled()
}

/// Get list of enabled plugins (if specific list provided)
pub fn get_enabled_plugins() -> Option<Vec<String>> {
    // Check env var first
    if let Ok(env_value) = std::env::var("PRAISONAI_PLUGINS") {
        let lower = env_value.to_lowercase();
        if !matches!(lower.as_str(), "true" | "1" | "yes" | "on" | "false" | "0" | "no" | "off") {
            // Treat as comma-separated list
            return Some(
                env_value
                    .split(',')
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect(),
            );
        }
    }
    
    // Check config file
    get_plugins_config().enabled.get_list().map(|l| l.to_vec())
}

/// Apply config defaults to a parameter if not explicitly set
pub fn apply_config_defaults<T: serde::de::DeserializeOwned + Default>(
    param_name: &str,
    explicit_value: Option<T>,
) -> Option<T> {
    // If user explicitly passed a value, respect it
    if explicit_value.is_some() {
        return explicit_value;
    }
    
    // Check if config has defaults for this param
    let config_value: Option<serde_json::Value> = get_default(param_name, None);
    
    match config_value {
        Some(v) => {
            // Check if enabled
            if let Some(enabled) = v.get("enabled") {
                if enabled.as_bool() == Some(false) {
                    return None;
                }
            }
            serde_json::from_value(v).ok()
        }
        None => None,
    }
}

// =============================================================================
// Config Validation
// =============================================================================

/// Valid root keys
const VALID_ROOT_KEYS: &[&str] = &["plugins", "defaults"];

/// Valid plugins keys
const VALID_PLUGINS_KEYS: &[&str] = &["enabled", "auto_discover", "directories"];

/// Valid defaults keys
const VALID_DEFAULTS_KEYS: &[&str] = &[
    "model",
    "base_url",
    "api_key",
    "allow_delegation",
    "allow_code_execution",
    "code_execution_mode",
    "memory",
    "knowledge",
    "planning",
    "reflection",
    "guardrails",
    "web",
    "output",
    "execution",
    "caching",
    "autonomy",
    "skills",
    "context",
    "hooks",
    "templates",
];

/// Suggest similar key using simple string matching
fn suggest_similar_key(key: &str, valid_keys: &[&str]) -> Option<String> {
    let key_lower = key.to_lowercase();
    
    for valid in valid_keys {
        let valid_lower = valid.to_lowercase();
        // Exact match after lowercasing
        if valid_lower == key_lower {
            return Some(valid.to_string());
        }
        // Prefix match
        if valid_lower.starts_with(&key_lower) || key_lower.starts_with(&valid_lower) {
            return Some(valid.to_string());
        }
        // Substring match
        if valid_lower.contains(&key_lower) || key_lower.contains(&valid_lower) {
            return Some(valid.to_string());
        }
    }
    
    None
}

/// Validate config structure and types
pub fn validate_config(config: &serde_json::Value) -> Result<(), ConfigValidationError> {
    let mut errors = Vec::new();
    
    if let Some(obj) = config.as_object() {
        // Check root keys
        for key in obj.keys() {
            if !VALID_ROOT_KEYS.contains(&key.as_str()) {
                errors.push(ConfigValidationError::UnknownKey {
                    section: "root".to_string(),
                    key: key.clone(),
                    suggestion: suggest_similar_key(key, VALID_ROOT_KEYS),
                });
            }
        }
        
        // Validate [plugins] section
        if let Some(plugins) = obj.get("plugins") {
            if let Some(plugins_obj) = plugins.as_object() {
                for key in plugins_obj.keys() {
                    if !VALID_PLUGINS_KEYS.contains(&key.as_str()) {
                        errors.push(ConfigValidationError::UnknownKey {
                            section: "plugins".to_string(),
                            key: key.clone(),
                            suggestion: suggest_similar_key(key, VALID_PLUGINS_KEYS),
                        });
                    }
                }
            }
        }
        
        // Validate [defaults] section
        if let Some(defaults) = obj.get("defaults") {
            if let Some(defaults_obj) = defaults.as_object() {
                for key in defaults_obj.keys() {
                    if !VALID_DEFAULTS_KEYS.contains(&key.as_str()) {
                        errors.push(ConfigValidationError::UnknownKey {
                            section: "defaults".to_string(),
                            key: key.clone(),
                            suggestion: suggest_similar_key(key, VALID_DEFAULTS_KEYS),
                        });
                    }
                }
            }
        }
    }
    
    if errors.is_empty() {
        Ok(())
    } else if errors.len() == 1 {
        Err(errors.remove(0))
    } else {
        Err(ConfigValidationError::Multiple(errors))
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_plugins_enabled_bool() {
        let enabled = PluginsEnabled::Bool(true);
        assert!(enabled.is_enabled());
        assert!(enabled.get_list().is_none());
        
        let disabled = PluginsEnabled::Bool(false);
        assert!(!disabled.is_enabled());
    }

    #[test]
    fn test_plugins_enabled_list() {
        let enabled = PluginsEnabled::List(vec!["plugin1".to_string(), "plugin2".to_string()]);
        assert!(enabled.is_enabled());
        assert_eq!(enabled.get_list().unwrap().len(), 2);
        
        let empty = PluginsEnabled::List(vec![]);
        assert!(!empty.is_enabled());
    }

    #[test]
    fn test_praison_config_default() {
        let config = PraisonConfig::default();
        assert!(!config.plugins.enabled.is_enabled());
        // auto_discover defaults to false
        assert!(!config.plugins.auto_discover);
    }

    #[test]
    fn test_suggest_similar_key() {
        // Test with exact match (case insensitive)
        let result = suggest_similar_key("model", VALID_DEFAULTS_KEYS);
        assert_eq!(result, Some("model".to_string()));
        
        // Test with prefix match - "mod" should match "model"
        let result2 = suggest_similar_key("mod", VALID_DEFAULTS_KEYS);
        assert_eq!(result2, Some("model".to_string()));
        
        // Test with substring match - "mem" should match "memory"
        let result3 = suggest_similar_key("mem", VALID_DEFAULTS_KEYS);
        assert_eq!(result3, Some("memory".to_string()));
        
        // Test with completely different word - should return None
        let result4 = suggest_similar_key("xyzabc", VALID_DEFAULTS_KEYS);
        assert!(result4.is_none());
    }

    #[test]
    fn test_validate_config_valid() {
        let config = serde_json::json!({
            "plugins": {
                "enabled": true
            },
            "defaults": {
                "model": "gpt-4o"
            }
        });
        
        assert!(validate_config(&config).is_ok());
    }

    #[test]
    fn test_validate_config_invalid_key() {
        let config = serde_json::json!({
            "plugins": {
                "enabeld": true  // typo
            }
        });
        
        let result = validate_config(&config);
        assert!(result.is_err());
    }

    #[test]
    fn test_defaults_config() {
        let defaults = DefaultsConfig {
            model: Some("gpt-4o".to_string()),
            allow_delegation: true,
            ..Default::default()
        };
        
        assert_eq!(defaults.model, Some("gpt-4o".to_string()));
        assert!(defaults.allow_delegation);
        assert!(!defaults.allow_code_execution);
    }
}
