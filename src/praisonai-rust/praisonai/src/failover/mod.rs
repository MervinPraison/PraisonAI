//! Model Failover Module for PraisonAI Rust SDK
//!
//! Provides auth profile management and automatic failover between
//! LLM providers when rate limits or errors occur.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::{FailoverManager, AuthProfile, FailoverConfig};
//!
//! let mut manager = FailoverManager::new(FailoverConfig::default());
//! manager.add_profile(AuthProfile::new("openai-primary", "openai", "sk-..."));
//! manager.add_profile(AuthProfile::new("openai-backup", "openai", "sk-...").priority(1));
//!
//! // Get next available profile
//! if let Some(profile) = manager.get_next_profile() {
//!     println!("Using profile: {}", profile.name);
//! }
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};

use crate::error::Result;

/// Status of an LLM provider.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ProviderStatus {
    /// Provider is available for use
    Available,
    /// Provider is rate limited
    RateLimited,
    /// Provider encountered an error
    Error,
    /// Provider is disabled
    Disabled,
}

impl Default for ProviderStatus {
    fn default() -> Self {
        Self::Available
    }
}

impl std::fmt::Display for ProviderStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Available => write!(f, "available"),
            Self::RateLimited => write!(f, "rate_limited"),
            Self::Error => write!(f, "error"),
            Self::Disabled => write!(f, "disabled"),
        }
    }
}

/// Authentication profile for an LLM provider.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthProfile {
    /// Profile name for identification
    pub name: String,
    /// Provider name (openai, anthropic, google, etc.)
    pub provider: String,
    /// API key for authentication
    #[serde(skip_serializing)]
    pub api_key: String,
    /// Optional base URL override
    pub base_url: Option<String>,
    /// Default model for this profile
    pub model: Option<String>,
    /// Priority for failover (lower = higher priority)
    pub priority: i32,
    /// Requests per minute limit
    pub rate_limit_rpm: Option<u32>,
    /// Tokens per minute limit
    pub rate_limit_tpm: Option<u32>,
    /// Current status
    pub status: ProviderStatus,
    /// Last error message
    pub last_error: Option<String>,
    /// Last error timestamp
    #[serde(skip)]
    pub last_error_time: Option<Instant>,
    /// Cooldown until timestamp
    #[serde(skip)]
    pub cooldown_until: Option<Instant>,
    /// Additional provider-specific configuration
    pub metadata: HashMap<String, String>,
}

impl AuthProfile {
    /// Create a new auth profile.
    pub fn new(name: impl Into<String>, provider: impl Into<String>, api_key: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            provider: provider.into(),
            api_key: api_key.into(),
            base_url: None,
            model: None,
            priority: 0,
            rate_limit_rpm: None,
            rate_limit_tpm: None,
            status: ProviderStatus::Available,
            last_error: None,
            last_error_time: None,
            cooldown_until: None,
            metadata: HashMap::new(),
        }
    }

    /// Set base URL
    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = Some(url.into());
        self
    }

    /// Set default model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set priority (lower = higher priority)
    pub fn priority(mut self, priority: i32) -> Self {
        self.priority = priority;
        self
    }

    /// Set rate limit (requests per minute)
    pub fn rate_limit_rpm(mut self, rpm: u32) -> Self {
        self.rate_limit_rpm = Some(rpm);
        self
    }

    /// Set rate limit (tokens per minute)
    pub fn rate_limit_tpm(mut self, tpm: u32) -> Self {
        self.rate_limit_tpm = Some(tpm);
        self
    }

    /// Add metadata
    pub fn metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    /// Check if this profile is currently available.
    pub fn is_available(&self) -> bool {
        if self.status == ProviderStatus::Disabled {
            return false;
        }
        if let Some(cooldown_until) = self.cooldown_until {
            if Instant::now() < cooldown_until {
                return false;
            }
        }
        true
    }

    /// Mark this profile as rate limited.
    pub fn mark_rate_limited(&mut self, cooldown: Duration) {
        self.status = ProviderStatus::RateLimited;
        self.cooldown_until = Some(Instant::now() + cooldown);
        self.last_error = Some("Rate limited".to_string());
        self.last_error_time = Some(Instant::now());
    }

    /// Mark this profile as having an error.
    pub fn mark_error(&mut self, error: impl Into<String>, cooldown: Duration) {
        self.status = ProviderStatus::Error;
        self.cooldown_until = Some(Instant::now() + cooldown);
        self.last_error = Some(error.into());
        self.last_error_time = Some(Instant::now());
    }

    /// Reset this profile to available status.
    pub fn reset(&mut self) {
        self.status = ProviderStatus::Available;
        self.cooldown_until = None;
        self.last_error = None;
        self.last_error_time = None;
    }

    /// Convert to dictionary (hides sensitive data).
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("name".to_string(), serde_json::json!(self.name));
        map.insert("provider".to_string(), serde_json::json!(self.provider));
        
        // Mask API key
        let masked_key = if self.api_key.len() > 4 {
            format!("***{}", &self.api_key[self.api_key.len()-4..])
        } else {
            "****".to_string()
        };
        map.insert("api_key".to_string(), serde_json::json!(masked_key));
        
        map.insert("base_url".to_string(), serde_json::json!(self.base_url));
        map.insert("model".to_string(), serde_json::json!(self.model));
        map.insert("priority".to_string(), serde_json::json!(self.priority));
        map.insert("rate_limit_rpm".to_string(), serde_json::json!(self.rate_limit_rpm));
        map.insert("rate_limit_tpm".to_string(), serde_json::json!(self.rate_limit_tpm));
        map.insert("status".to_string(), serde_json::json!(self.status.to_string()));
        map.insert("last_error".to_string(), serde_json::json!(self.last_error));
        map
    }
}

/// Configuration for failover behavior.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FailoverConfig {
    /// Maximum retry attempts per request
    pub max_retries: u32,
    /// Base delay between retries (seconds)
    pub retry_delay: f64,
    /// Whether to use exponential backoff
    pub exponential_backoff: bool,
    /// Maximum retry delay (seconds)
    pub max_retry_delay: f64,
    /// Cooldown duration for rate limits (seconds)
    pub cooldown_on_rate_limit: f64,
    /// Cooldown duration for errors (seconds)
    pub cooldown_on_error: f64,
    /// Whether to rotate profiles on success
    pub rotate_on_success: bool,
}

impl Default for FailoverConfig {
    fn default() -> Self {
        Self {
            max_retries: 3,
            retry_delay: 1.0,
            exponential_backoff: true,
            max_retry_delay: 60.0,
            cooldown_on_rate_limit: 60.0,
            cooldown_on_error: 30.0,
            rotate_on_success: false,
        }
    }
}

impl FailoverConfig {
    /// Create a new config with defaults
    pub fn new() -> Self {
        Self::default()
    }

    /// Set max retries
    pub fn max_retries(mut self, retries: u32) -> Self {
        self.max_retries = retries;
        self
    }

    /// Set retry delay
    pub fn retry_delay(mut self, delay: f64) -> Self {
        self.retry_delay = delay;
        self
    }

    /// Set exponential backoff
    pub fn exponential_backoff(mut self, enabled: bool) -> Self {
        self.exponential_backoff = enabled;
        self
    }

    /// Set max retry delay
    pub fn max_retry_delay(mut self, delay: f64) -> Self {
        self.max_retry_delay = delay;
        self
    }

    /// Set cooldown on rate limit
    pub fn cooldown_on_rate_limit(mut self, seconds: f64) -> Self {
        self.cooldown_on_rate_limit = seconds;
        self
    }

    /// Set cooldown on error
    pub fn cooldown_on_error(mut self, seconds: f64) -> Self {
        self.cooldown_on_error = seconds;
        self
    }
}

/// Callback type for failover events.
pub type FailoverCallback = Box<dyn Fn(&AuthProfile, &AuthProfile) + Send + Sync>;

/// Manages failover between multiple LLM auth profiles.
///
/// Provides automatic failover when rate limits or errors occur,
/// with configurable retry behavior and cooldown periods.
pub struct FailoverManager {
    /// Failover configuration
    pub config: FailoverConfig,
    /// Registered profiles
    profiles: Vec<AuthProfile>,
    /// Current profile index
    current_index: usize,
    /// Failover callbacks
    callbacks: Vec<FailoverCallback>,
}

impl FailoverManager {
    /// Create a new failover manager.
    pub fn new(config: FailoverConfig) -> Self {
        Self {
            config,
            profiles: Vec::new(),
            current_index: 0,
            callbacks: Vec::new(),
        }
    }

    /// Create with default config.
    pub fn default_config() -> Self {
        Self::new(FailoverConfig::default())
    }

    /// Add an auth profile.
    pub fn add_profile(&mut self, profile: AuthProfile) {
        self.profiles.push(profile);
        self.profiles.sort_by_key(|p| p.priority);
    }

    /// Remove a profile by name.
    pub fn remove_profile(&mut self, name: &str) -> bool {
        if let Some(pos) = self.profiles.iter().position(|p| p.name == name) {
            self.profiles.remove(pos);
            true
        } else {
            false
        }
    }

    /// Get a profile by name.
    pub fn get_profile(&self, name: &str) -> Option<&AuthProfile> {
        self.profiles.iter().find(|p| p.name == name)
    }

    /// Get a mutable profile by name.
    pub fn get_profile_mut(&mut self, name: &str) -> Option<&mut AuthProfile> {
        self.profiles.iter_mut().find(|p| p.name == name)
    }

    /// List all profiles.
    pub fn list_profiles(&self) -> &[AuthProfile] {
        &self.profiles
    }

    /// Get the next available profile.
    ///
    /// Returns profiles in priority order, skipping those that are
    /// rate limited or in cooldown.
    pub fn get_next_profile(&mut self) -> Option<&AuthProfile> {
        if self.profiles.is_empty() {
            return None;
        }

        // First, check if any cooldowns have expired
        let now = Instant::now();
        for profile in &mut self.profiles {
            if let Some(cooldown_until) = profile.cooldown_until {
                if now >= cooldown_until {
                    profile.reset();
                }
            }
        }

        // Find first available profile
        for profile in &self.profiles {
            if profile.is_available() {
                return Some(profile);
            }
        }

        // If none available, return the one with shortest remaining cooldown
        self.profiles
            .iter()
            .filter(|p| p.status != ProviderStatus::Disabled)
            .min_by_key(|p| {
                p.cooldown_until
                    .map(|t| t.duration_since(now))
                    .unwrap_or(Duration::ZERO)
            })
    }

    /// Mark a profile as failed.
    pub fn mark_failure(&mut self, profile_name: &str, error: &str, is_rate_limit: bool) {
        let cooldown = if is_rate_limit {
            Duration::from_secs_f64(self.config.cooldown_on_rate_limit)
        } else {
            Duration::from_secs_f64(self.config.cooldown_on_error)
        };

        if let Some(profile) = self.get_profile_mut(profile_name) {
            if is_rate_limit {
                profile.mark_rate_limited(cooldown);
            } else {
                profile.mark_error(error, cooldown);
            }
        }

        // Notify callbacks
        let failed_profile = self.get_profile(profile_name).cloned();
        if let (Some(failed), Some(next)) = (failed_profile, self.get_next_profile().cloned()) {
            if failed.name != next.name {
                for callback in &self.callbacks {
                    callback(&failed, &next);
                }
            }
        }
    }

    /// Mark a profile as successful.
    pub fn mark_success(&mut self, profile_name: &str) {
        if let Some(profile) = self.get_profile_mut(profile_name) {
            if profile.status != ProviderStatus::Available {
                profile.reset();
            }
        }
    }

    /// Register a callback for failover events.
    pub fn on_failover(&mut self, callback: FailoverCallback) {
        self.callbacks.push(callback);
    }

    /// Calculate retry delay for an attempt.
    pub fn get_retry_delay(&self, attempt: u32) -> Duration {
        let delay = if self.config.exponential_backoff {
            self.config.retry_delay * 2.0_f64.powi(attempt as i32)
        } else {
            self.config.retry_delay
        };

        Duration::from_secs_f64(delay.min(self.config.max_retry_delay))
    }

    /// Get failover manager status.
    pub fn status(&self) -> FailoverStatus {
        let available = self.profiles.iter().filter(|p| p.is_available()).count();
        FailoverStatus {
            total_profiles: self.profiles.len(),
            available_profiles: available,
            profiles: self.profiles.iter().map(|p| p.to_dict()).collect(),
            config: self.config.clone(),
        }
    }

    /// Reset all profiles to available status.
    pub fn reset_all(&mut self) {
        for profile in &mut self.profiles {
            profile.reset();
        }
    }

    /// Get the number of profiles.
    pub fn len(&self) -> usize {
        self.profiles.len()
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.profiles.is_empty()
    }
}

impl Default for FailoverManager {
    fn default() -> Self {
        Self::default_config()
    }
}

/// Status information for the failover manager.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FailoverStatus {
    /// Total number of profiles
    pub total_profiles: usize,
    /// Number of available profiles
    pub available_profiles: usize,
    /// Profile information
    pub profiles: Vec<HashMap<String, serde_json::Value>>,
    /// Configuration
    pub config: FailoverConfig,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_provider_status() {
        assert_eq!(ProviderStatus::default(), ProviderStatus::Available);
        assert_eq!(ProviderStatus::Available.to_string(), "available");
        assert_eq!(ProviderStatus::RateLimited.to_string(), "rate_limited");
    }

    #[test]
    fn test_auth_profile_new() {
        let profile = AuthProfile::new("test", "openai", "sk-test123");
        assert_eq!(profile.name, "test");
        assert_eq!(profile.provider, "openai");
        assert_eq!(profile.api_key, "sk-test123");
        assert_eq!(profile.priority, 0);
        assert!(profile.is_available());
    }

    #[test]
    fn test_auth_profile_builder() {
        let profile = AuthProfile::new("test", "openai", "sk-test")
            .base_url("https://api.example.com")
            .model("gpt-4")
            .priority(1)
            .rate_limit_rpm(100);

        assert_eq!(profile.base_url, Some("https://api.example.com".to_string()));
        assert_eq!(profile.model, Some("gpt-4".to_string()));
        assert_eq!(profile.priority, 1);
        assert_eq!(profile.rate_limit_rpm, Some(100));
    }

    #[test]
    fn test_auth_profile_rate_limited() {
        let mut profile = AuthProfile::new("test", "openai", "sk-test");
        profile.mark_rate_limited(Duration::from_secs(60));

        assert_eq!(profile.status, ProviderStatus::RateLimited);
        assert!(!profile.is_available());
        assert!(profile.last_error.is_some());
    }

    #[test]
    fn test_auth_profile_error() {
        let mut profile = AuthProfile::new("test", "openai", "sk-test");
        profile.mark_error("Connection failed", Duration::from_secs(30));

        assert_eq!(profile.status, ProviderStatus::Error);
        assert!(!profile.is_available());
        assert_eq!(profile.last_error, Some("Connection failed".to_string()));
    }

    #[test]
    fn test_auth_profile_reset() {
        let mut profile = AuthProfile::new("test", "openai", "sk-test");
        profile.mark_error("Error", Duration::from_secs(30));
        profile.reset();

        assert_eq!(profile.status, ProviderStatus::Available);
        assert!(profile.is_available());
        assert!(profile.last_error.is_none());
    }

    #[test]
    fn test_auth_profile_to_dict() {
        let profile = AuthProfile::new("test", "openai", "sk-test123");
        let dict = profile.to_dict();

        assert_eq!(dict.get("name").unwrap(), "test");
        assert_eq!(dict.get("provider").unwrap(), "openai");
        // API key should be masked
        let api_key = dict.get("api_key").unwrap().as_str().unwrap();
        assert!(api_key.starts_with("***"));
    }

    #[test]
    fn test_failover_config_default() {
        let config = FailoverConfig::default();
        assert_eq!(config.max_retries, 3);
        assert_eq!(config.retry_delay, 1.0);
        assert!(config.exponential_backoff);
    }

    #[test]
    fn test_failover_config_builder() {
        let config = FailoverConfig::new()
            .max_retries(5)
            .retry_delay(2.0)
            .exponential_backoff(false);

        assert_eq!(config.max_retries, 5);
        assert_eq!(config.retry_delay, 2.0);
        assert!(!config.exponential_backoff);
    }

    #[test]
    fn test_failover_manager_new() {
        let manager = FailoverManager::default();
        assert!(manager.is_empty());
        assert_eq!(manager.len(), 0);
    }

    #[test]
    fn test_failover_manager_add_profile() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("primary", "openai", "sk-1").priority(0));
        manager.add_profile(AuthProfile::new("backup", "openai", "sk-2").priority(1));

        assert_eq!(manager.len(), 2);
        assert!(!manager.is_empty());
    }

    #[test]
    fn test_failover_manager_get_profile() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("test", "openai", "sk-test"));

        let profile = manager.get_profile("test");
        assert!(profile.is_some());
        assert_eq!(profile.unwrap().name, "test");

        let missing = manager.get_profile("missing");
        assert!(missing.is_none());
    }

    #[test]
    fn test_failover_manager_remove_profile() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("test", "openai", "sk-test"));

        assert!(manager.remove_profile("test"));
        assert!(!manager.remove_profile("test"));
        assert!(manager.is_empty());
    }

    #[test]
    fn test_failover_manager_get_next_profile() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("primary", "openai", "sk-1").priority(0));
        manager.add_profile(AuthProfile::new("backup", "openai", "sk-2").priority(1));

        let profile = manager.get_next_profile();
        assert!(profile.is_some());
        assert_eq!(profile.unwrap().name, "primary");
    }

    #[test]
    fn test_failover_manager_priority_order() {
        let mut manager = FailoverManager::default();
        // Add in reverse priority order
        manager.add_profile(AuthProfile::new("backup", "openai", "sk-2").priority(1));
        manager.add_profile(AuthProfile::new("primary", "openai", "sk-1").priority(0));

        // Should still get primary first due to sorting
        let profile = manager.get_next_profile();
        assert_eq!(profile.unwrap().name, "primary");
    }

    #[test]
    fn test_failover_manager_mark_failure() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("primary", "openai", "sk-1").priority(0));
        manager.add_profile(AuthProfile::new("backup", "openai", "sk-2").priority(1));

        manager.mark_failure("primary", "Rate limit", true);

        // Should now get backup
        let profile = manager.get_next_profile();
        assert_eq!(profile.unwrap().name, "backup");
    }

    #[test]
    fn test_failover_manager_mark_success() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("test", "openai", "sk-test"));
        manager.mark_failure("test", "Error", false);
        manager.mark_success("test");

        let profile = manager.get_profile("test").unwrap();
        assert_eq!(profile.status, ProviderStatus::Available);
    }

    #[test]
    fn test_failover_manager_retry_delay() {
        let manager = FailoverManager::new(
            FailoverConfig::new()
                .retry_delay(1.0)
                .exponential_backoff(true)
                .max_retry_delay(10.0)
        );

        assert_eq!(manager.get_retry_delay(0), Duration::from_secs(1));
        assert_eq!(manager.get_retry_delay(1), Duration::from_secs(2));
        assert_eq!(manager.get_retry_delay(2), Duration::from_secs(4));
        assert_eq!(manager.get_retry_delay(10), Duration::from_secs(10)); // Capped
    }

    #[test]
    fn test_failover_manager_retry_delay_no_backoff() {
        let manager = FailoverManager::new(
            FailoverConfig::new()
                .retry_delay(2.0)
                .exponential_backoff(false)
        );

        assert_eq!(manager.get_retry_delay(0), Duration::from_secs(2));
        assert_eq!(manager.get_retry_delay(1), Duration::from_secs(2));
        assert_eq!(manager.get_retry_delay(5), Duration::from_secs(2));
    }

    #[test]
    fn test_failover_manager_status() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("primary", "openai", "sk-1"));
        manager.add_profile(AuthProfile::new("backup", "openai", "sk-2"));

        let status = manager.status();
        assert_eq!(status.total_profiles, 2);
        assert_eq!(status.available_profiles, 2);
    }

    #[test]
    fn test_failover_manager_reset_all() {
        let mut manager = FailoverManager::default();
        manager.add_profile(AuthProfile::new("primary", "openai", "sk-1"));
        manager.add_profile(AuthProfile::new("backup", "openai", "sk-2"));

        manager.mark_failure("primary", "Error", false);
        manager.mark_failure("backup", "Error", false);

        manager.reset_all();

        let status = manager.status();
        assert_eq!(status.available_profiles, 2);
    }
}
