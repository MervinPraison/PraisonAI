//! Thinking Budget Module for PraisonAI Rust SDK.
//!
//! Provides configurable thinking budgets for LLM reasoning:
//! - Token budgets for extended thinking
//! - Time budgets for reasoning
//! - Adaptive budget allocation
//! - Budget tracking and reporting
//!
//! # Example
//!
//! ```ignore
//! use praisonai::thinking::{ThinkingBudget, BudgetLevel, ThinkingTracker};
//!
//! // Create a thinking budget
//! let budget = ThinkingBudget::high();
//!
//! // Or with custom settings
//! let budget = ThinkingBudget::new()
//!     .max_tokens(16000)
//!     .adaptive(true)
//!     .build();
//!
//! // Track usage
//! let mut tracker = ThinkingTracker::new();
//! let usage = tracker.start_session(8000, None, 0.5);
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};

// =============================================================================
// BUDGET LEVEL
// =============================================================================

/// Predefined budget levels for thinking.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BudgetLevel {
    /// Minimal budget (2000 tokens)
    Minimal,
    /// Low budget (4000 tokens)
    Low,
    /// Medium budget (8000 tokens)
    Medium,
    /// High budget (16000 tokens)
    High,
    /// Maximum budget (32000 tokens)
    Maximum,
}

impl BudgetLevel {
    /// Get the token allocation for this level.
    pub fn tokens(&self) -> usize {
        match self {
            BudgetLevel::Minimal => 2000,
            BudgetLevel::Low => 4000,
            BudgetLevel::Medium => 8000,
            BudgetLevel::High => 16000,
            BudgetLevel::Maximum => 32000,
        }
    }
}

impl Default for BudgetLevel {
    fn default() -> Self {
        BudgetLevel::Medium
    }
}

// =============================================================================
// THINKING BUDGET
// =============================================================================

/// Budget constraints for extended thinking.
///
/// Controls how much thinking/reasoning the LLM can do
/// before producing a response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThinkingBudget {
    /// Maximum tokens for thinking
    pub max_tokens: usize,
    /// Maximum time in seconds (optional)
    pub max_time_seconds: Option<f64>,
    /// Whether to adapt budget based on complexity
    pub adaptive: bool,
    /// Budget level (if using predefined)
    pub level: Option<BudgetLevel>,
    /// Minimum tokens for adaptive budgeting
    pub min_tokens: usize,
    /// Complexity multiplier for adaptive budgeting
    pub complexity_multiplier: f64,
}

impl Default for ThinkingBudget {
    fn default() -> Self {
        Self {
            max_tokens: 8000,
            max_time_seconds: None,
            adaptive: true,
            level: None,
            min_tokens: 1000,
            complexity_multiplier: 1.0,
        }
    }
}

impl ThinkingBudget {
    /// Create a new ThinkingBudget with default values.
    pub fn new() -> ThinkingBudgetBuilder {
        ThinkingBudgetBuilder::default()
    }

    /// Create a budget from a predefined level.
    pub fn from_level(level: BudgetLevel) -> Self {
        Self {
            max_tokens: level.tokens(),
            level: Some(level),
            ..Default::default()
        }
    }

    /// Create a minimal budget.
    pub fn minimal() -> Self {
        Self::from_level(BudgetLevel::Minimal)
    }

    /// Create a low budget.
    pub fn low() -> Self {
        Self::from_level(BudgetLevel::Low)
    }

    /// Create a medium budget.
    pub fn medium() -> Self {
        Self::from_level(BudgetLevel::Medium)
    }

    /// Create a high budget.
    pub fn high() -> Self {
        Self::from_level(BudgetLevel::High)
    }

    /// Create a maximum budget.
    pub fn maximum() -> Self {
        Self::from_level(BudgetLevel::Maximum)
    }

    /// Get token budget based on task complexity.
    ///
    /// # Arguments
    /// * `complexity` - Complexity score (0.0 to 1.0)
    ///
    /// # Returns
    /// Adjusted token budget
    pub fn get_tokens_for_complexity(&self, complexity: f64) -> usize {
        if !self.adaptive {
            return self.max_tokens;
        }

        let range_tokens = self.max_tokens.saturating_sub(self.min_tokens);
        let adjusted = self.min_tokens
            + (range_tokens as f64 * complexity * self.complexity_multiplier) as usize;

        adjusted.min(self.max_tokens)
    }

    /// Convert to HashMap for serialization.
    pub fn to_map(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("max_tokens".to_string(), serde_json::json!(self.max_tokens));
        map.insert("max_time_seconds".to_string(), serde_json::json!(self.max_time_seconds));
        map.insert("adaptive".to_string(), serde_json::json!(self.adaptive));
        map.insert("level".to_string(), serde_json::json!(self.level));
        map.insert("min_tokens".to_string(), serde_json::json!(self.min_tokens));
        map.insert("complexity_multiplier".to_string(), serde_json::json!(self.complexity_multiplier));
        map
    }
}

/// Builder for ThinkingBudget.
#[derive(Debug, Default)]
pub struct ThinkingBudgetBuilder {
    max_tokens: Option<usize>,
    max_time_seconds: Option<f64>,
    adaptive: Option<bool>,
    level: Option<BudgetLevel>,
    min_tokens: Option<usize>,
    complexity_multiplier: Option<f64>,
}

impl ThinkingBudgetBuilder {
    /// Set maximum tokens.
    pub fn max_tokens(mut self, tokens: usize) -> Self {
        self.max_tokens = Some(tokens);
        self
    }

    /// Set maximum time in seconds.
    pub fn max_time_seconds(mut self, seconds: f64) -> Self {
        self.max_time_seconds = Some(seconds);
        self
    }

    /// Set adaptive mode.
    pub fn adaptive(mut self, adaptive: bool) -> Self {
        self.adaptive = Some(adaptive);
        self
    }

    /// Set budget level.
    pub fn level(mut self, level: BudgetLevel) -> Self {
        self.level = Some(level);
        self
    }

    /// Set minimum tokens for adaptive budgeting.
    pub fn min_tokens(mut self, tokens: usize) -> Self {
        self.min_tokens = Some(tokens);
        self
    }

    /// Set complexity multiplier.
    pub fn complexity_multiplier(mut self, multiplier: f64) -> Self {
        self.complexity_multiplier = Some(multiplier);
        self
    }

    /// Build the ThinkingBudget.
    pub fn build(self) -> ThinkingBudget {
        let level = self.level;
        let max_tokens = if let Some(l) = level {
            l.tokens()
        } else {
            self.max_tokens.unwrap_or(8000)
        };

        ThinkingBudget {
            max_tokens,
            max_time_seconds: self.max_time_seconds,
            adaptive: self.adaptive.unwrap_or(true),
            level,
            min_tokens: self.min_tokens.unwrap_or(1000),
            complexity_multiplier: self.complexity_multiplier.unwrap_or(1.0),
        }
    }
}

// =============================================================================
// THINKING CONFIG
// =============================================================================

/// Configuration for thinking behavior.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThinkingConfig {
    /// Whether thinking is enabled
    pub enabled: bool,
    /// Budget for thinking
    pub budget: ThinkingBudget,
    /// Whether to show thinking in output
    pub show_thinking: bool,
    /// Whether to log thinking usage
    pub log_usage: bool,
}

impl Default for ThinkingConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            budget: ThinkingBudget::default(),
            show_thinking: false,
            log_usage: false,
        }
    }
}

impl ThinkingConfig {
    /// Create a new config with thinking enabled.
    pub fn enabled() -> Self {
        Self {
            enabled: true,
            ..Default::default()
        }
    }

    /// Create a new config with a specific budget level.
    pub fn with_level(level: BudgetLevel) -> Self {
        Self {
            enabled: true,
            budget: ThinkingBudget::from_level(level),
            ..Default::default()
        }
    }
}

// =============================================================================
// THINKING USAGE
// =============================================================================

/// Usage statistics for a single thinking session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThinkingUsage {
    /// Tokens used in this session
    pub tokens_used: usize,
    /// Time taken in seconds
    pub time_seconds: f64,
    /// Token budget for this session
    pub budget_tokens: usize,
    /// Time budget for this session (optional)
    pub budget_time: Option<f64>,
    /// Task complexity (0.0 to 1.0)
    pub complexity: f64,
    /// When the session started
    #[serde(skip)]
    pub started_at: Option<Instant>,
    /// When the session ended
    #[serde(skip)]
    pub ended_at: Option<Instant>,
}

impl Default for ThinkingUsage {
    fn default() -> Self {
        Self {
            tokens_used: 0,
            time_seconds: 0.0,
            budget_tokens: 0,
            budget_time: None,
            complexity: 0.5,
            started_at: None,
            ended_at: None,
        }
    }
}

impl ThinkingUsage {
    /// Get remaining token budget.
    pub fn tokens_remaining(&self) -> usize {
        self.budget_tokens.saturating_sub(self.tokens_used)
    }

    /// Get remaining time budget.
    pub fn time_remaining(&self) -> Option<f64> {
        self.budget_time.map(|bt| (bt - self.time_seconds).max(0.0))
    }

    /// Get token utilization percentage.
    pub fn token_utilization(&self) -> f64 {
        if self.budget_tokens == 0 {
            return 0.0;
        }
        self.tokens_used as f64 / self.budget_tokens as f64
    }

    /// Check if over token budget.
    pub fn is_over_budget(&self) -> bool {
        self.tokens_used > self.budget_tokens
    }

    /// Check if over time budget.
    pub fn is_over_time(&self) -> bool {
        match self.budget_time {
            Some(bt) => self.time_seconds > bt,
            None => false,
        }
    }

    /// Convert to HashMap for serialization.
    pub fn to_map(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("tokens_used".to_string(), serde_json::json!(self.tokens_used));
        map.insert("time_seconds".to_string(), serde_json::json!(self.time_seconds));
        map.insert("budget_tokens".to_string(), serde_json::json!(self.budget_tokens));
        map.insert("budget_time".to_string(), serde_json::json!(self.budget_time));
        map.insert("complexity".to_string(), serde_json::json!(self.complexity));
        map.insert("tokens_remaining".to_string(), serde_json::json!(self.tokens_remaining()));
        map.insert("token_utilization".to_string(), serde_json::json!(self.token_utilization()));
        map.insert("is_over_budget".to_string(), serde_json::json!(self.is_over_budget()));
        map
    }
}

// =============================================================================
// THINKING TRACKER
// =============================================================================

/// Tracks thinking usage across multiple sessions.
///
/// Provides aggregate statistics and reporting.
#[derive(Debug, Default)]
pub struct ThinkingTracker {
    /// All tracked sessions
    pub sessions: Vec<ThinkingUsage>,
    /// Total tokens used across all sessions
    pub total_tokens_used: usize,
    /// Total time across all sessions
    pub total_time_seconds: f64,
}

impl ThinkingTracker {
    /// Create a new tracker.
    pub fn new() -> Self {
        Self::default()
    }

    /// Start a new thinking session.
    ///
    /// # Arguments
    /// * `budget_tokens` - Token budget for this session
    /// * `budget_time` - Optional time budget
    /// * `complexity` - Task complexity (0.0 to 1.0)
    ///
    /// # Returns
    /// Index of the new session
    pub fn start_session(
        &mut self,
        budget_tokens: usize,
        budget_time: Option<f64>,
        complexity: f64,
    ) -> usize {
        let usage = ThinkingUsage {
            budget_tokens,
            budget_time,
            complexity,
            started_at: Some(Instant::now()),
            ..Default::default()
        };
        self.sessions.push(usage);
        self.sessions.len() - 1
    }

    /// End a thinking session.
    ///
    /// # Arguments
    /// * `session_idx` - Index of the session to end
    /// * `tokens_used` - Actual tokens used
    /// * `time_seconds` - Actual time taken
    pub fn end_session(&mut self, session_idx: usize, tokens_used: usize, time_seconds: f64) {
        if let Some(usage) = self.sessions.get_mut(session_idx) {
            usage.tokens_used = tokens_used;
            usage.time_seconds = time_seconds;
            usage.ended_at = Some(Instant::now());

            self.total_tokens_used += tokens_used;
            self.total_time_seconds += time_seconds;
        }
    }

    /// Get the number of sessions.
    pub fn session_count(&self) -> usize {
        self.sessions.len()
    }

    /// Get average tokens per session.
    pub fn average_tokens_per_session(&self) -> f64 {
        if self.sessions.is_empty() {
            return 0.0;
        }
        self.total_tokens_used as f64 / self.sessions.len() as f64
    }

    /// Get average time per session.
    pub fn average_time_per_session(&self) -> f64 {
        if self.sessions.is_empty() {
            return 0.0;
        }
        self.total_time_seconds / self.sessions.len() as f64
    }

    /// Get average budget utilization.
    pub fn average_utilization(&self) -> f64 {
        if self.sessions.is_empty() {
            return 0.0;
        }
        let total: f64 = self.sessions.iter().map(|s| s.token_utilization()).sum();
        total / self.sessions.len() as f64
    }

    /// Get number of sessions that went over budget.
    pub fn over_budget_count(&self) -> usize {
        self.sessions.iter().filter(|s| s.is_over_budget()).count()
    }

    /// Get summary statistics.
    pub fn get_summary(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("session_count".to_string(), serde_json::json!(self.session_count()));
        map.insert("total_tokens_used".to_string(), serde_json::json!(self.total_tokens_used));
        map.insert("total_time_seconds".to_string(), serde_json::json!(self.total_time_seconds));
        map.insert("average_tokens_per_session".to_string(), serde_json::json!(self.average_tokens_per_session()));
        map.insert("average_time_per_session".to_string(), serde_json::json!(self.average_time_per_session()));
        map.insert("average_utilization".to_string(), serde_json::json!(self.average_utilization()));
        map.insert("over_budget_count".to_string(), serde_json::json!(self.over_budget_count()));
        map
    }

    /// Clear all tracking data.
    pub fn clear(&mut self) {
        self.sessions.clear();
        self.total_tokens_used = 0;
        self.total_time_seconds = 0.0;
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_budget_level_tokens() {
        assert_eq!(BudgetLevel::Minimal.tokens(), 2000);
        assert_eq!(BudgetLevel::Low.tokens(), 4000);
        assert_eq!(BudgetLevel::Medium.tokens(), 8000);
        assert_eq!(BudgetLevel::High.tokens(), 16000);
        assert_eq!(BudgetLevel::Maximum.tokens(), 32000);
    }

    #[test]
    fn test_thinking_budget_from_level() {
        let budget = ThinkingBudget::high();
        assert_eq!(budget.max_tokens, 16000);
        assert_eq!(budget.level, Some(BudgetLevel::High));
    }

    #[test]
    fn test_thinking_budget_builder() {
        let budget = ThinkingBudget::new()
            .max_tokens(10000)
            .adaptive(false)
            .min_tokens(500)
            .build();

        assert_eq!(budget.max_tokens, 10000);
        assert!(!budget.adaptive);
        assert_eq!(budget.min_tokens, 500);
    }

    #[test]
    fn test_get_tokens_for_complexity() {
        let budget = ThinkingBudget::new()
            .max_tokens(10000)
            .min_tokens(2000)
            .adaptive(true)
            .build();

        // Low complexity
        let tokens = budget.get_tokens_for_complexity(0.0);
        assert_eq!(tokens, 2000);

        // High complexity
        let tokens = budget.get_tokens_for_complexity(1.0);
        assert_eq!(tokens, 10000);

        // Medium complexity
        let tokens = budget.get_tokens_for_complexity(0.5);
        assert_eq!(tokens, 6000);
    }

    #[test]
    fn test_thinking_usage() {
        let usage = ThinkingUsage {
            tokens_used: 5000,
            budget_tokens: 10000,
            time_seconds: 30.0,
            budget_time: Some(60.0),
            ..Default::default()
        };

        assert_eq!(usage.tokens_remaining(), 5000);
        assert_eq!(usage.time_remaining(), Some(30.0));
        assert!((usage.token_utilization() - 0.5).abs() < 0.001);
        assert!(!usage.is_over_budget());
        assert!(!usage.is_over_time());
    }

    #[test]
    fn test_thinking_usage_over_budget() {
        let usage = ThinkingUsage {
            tokens_used: 15000,
            budget_tokens: 10000,
            ..Default::default()
        };

        assert!(usage.is_over_budget());
        assert_eq!(usage.tokens_remaining(), 0);
    }

    #[test]
    fn test_thinking_tracker() {
        let mut tracker = ThinkingTracker::new();

        // Start and end a session
        let idx = tracker.start_session(10000, Some(60.0), 0.5);
        tracker.end_session(idx, 5000, 30.0);

        assert_eq!(tracker.session_count(), 1);
        assert_eq!(tracker.total_tokens_used, 5000);
        assert!((tracker.total_time_seconds - 30.0).abs() < 0.001);
    }

    #[test]
    fn test_thinking_tracker_multiple_sessions() {
        let mut tracker = ThinkingTracker::new();

        let idx1 = tracker.start_session(10000, None, 0.5);
        tracker.end_session(idx1, 5000, 30.0);

        let idx2 = tracker.start_session(8000, None, 0.7);
        tracker.end_session(idx2, 6000, 40.0);

        assert_eq!(tracker.session_count(), 2);
        assert_eq!(tracker.total_tokens_used, 11000);
        assert!((tracker.average_tokens_per_session() - 5500.0).abs() < 0.001);
    }

    #[test]
    fn test_thinking_tracker_clear() {
        let mut tracker = ThinkingTracker::new();
        let idx = tracker.start_session(10000, None, 0.5);
        tracker.end_session(idx, 5000, 30.0);

        tracker.clear();

        assert_eq!(tracker.session_count(), 0);
        assert_eq!(tracker.total_tokens_used, 0);
    }

    #[test]
    fn test_thinking_config() {
        let config = ThinkingConfig::with_level(BudgetLevel::High);
        assert!(config.enabled);
        assert_eq!(config.budget.max_tokens, 16000);
    }
}
