//! Policy Module for PraisonAI Rust SDK.
//!
//! Provides policy engine for controlling agent behavior.
//!
//! # Example
//!
//! ```ignore
//! use praisonai::policy::{PolicyEngine, PolicyRule, PolicyAction};
//!
//! let mut engine = PolicyEngine::new();
//! engine.add_rule(PolicyRule::new("no-pii")
//!     .pattern(r"\b\d{3}-\d{2}-\d{4}\b")
//!     .action(PolicyAction::Block));
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// POLICY ACTION
// =============================================================================

/// Action to take when a policy is triggered.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PolicyAction {
    /// Allow the action
    Allow,
    /// Block the action
    Block,
    /// Warn but allow
    Warn,
    /// Require approval
    RequireApproval,
    /// Redact sensitive content
    Redact,
    /// Log and allow
    Log,
}

impl Default for PolicyAction {
    fn default() -> Self {
        PolicyAction::Allow
    }
}

// =============================================================================
// POLICY RESULT
// =============================================================================

/// Result of a policy check.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyResult {
    /// Whether the check passed
    pub passed: bool,
    /// Action to take
    pub action: PolicyAction,
    /// Rule that was triggered (if any)
    pub triggered_rule: Option<String>,
    /// Message
    pub message: Option<String>,
    /// Modified content (if redacted)
    pub modified_content: Option<String>,
}

impl PolicyResult {
    /// Create a passing result.
    pub fn pass() -> Self {
        Self {
            passed: true,
            action: PolicyAction::Allow,
            triggered_rule: None,
            message: None,
            modified_content: None,
        }
    }

    /// Create a blocking result.
    pub fn block(rule: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            passed: false,
            action: PolicyAction::Block,
            triggered_rule: Some(rule.into()),
            message: Some(message.into()),
            modified_content: None,
        }
    }

    /// Create a warning result.
    pub fn warn(rule: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            passed: true,
            action: PolicyAction::Warn,
            triggered_rule: Some(rule.into()),
            message: Some(message.into()),
            modified_content: None,
        }
    }

    /// Create a redact result.
    pub fn redact(rule: impl Into<String>, modified: impl Into<String>) -> Self {
        Self {
            passed: true,
            action: PolicyAction::Redact,
            triggered_rule: Some(rule.into()),
            message: None,
            modified_content: Some(modified.into()),
        }
    }
}

// =============================================================================
// POLICY RULE
// =============================================================================

/// A policy rule.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyRule {
    /// Rule name
    pub name: String,
    /// Rule description
    pub description: Option<String>,
    /// Pattern to match (regex)
    pub pattern: Option<String>,
    /// Keywords to match
    pub keywords: Vec<String>,
    /// Action to take
    pub action: PolicyAction,
    /// Whether the rule is enabled
    pub enabled: bool,
    /// Priority (higher = checked first)
    pub priority: i32,
    /// Replacement text for redaction
    pub replacement: Option<String>,
}

impl PolicyRule {
    /// Create a new rule.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: None,
            pattern: None,
            keywords: Vec::new(),
            action: PolicyAction::Block,
            enabled: true,
            priority: 0,
            replacement: None,
        }
    }

    /// Set description.
    pub fn description(mut self, desc: impl Into<String>) -> Self {
        self.description = Some(desc.into());
        self
    }

    /// Set pattern.
    pub fn pattern(mut self, pattern: impl Into<String>) -> Self {
        self.pattern = Some(pattern.into());
        self
    }

    /// Add keyword.
    pub fn keyword(mut self, keyword: impl Into<String>) -> Self {
        self.keywords.push(keyword.into());
        self
    }

    /// Set action.
    pub fn action(mut self, action: PolicyAction) -> Self {
        self.action = action;
        self
    }

    /// Set priority.
    pub fn priority(mut self, priority: i32) -> Self {
        self.priority = priority;
        self
    }

    /// Set replacement.
    pub fn replacement(mut self, replacement: impl Into<String>) -> Self {
        self.replacement = Some(replacement.into());
        self
    }

    /// Enable the rule.
    pub fn enable(&mut self) {
        self.enabled = true;
    }

    /// Disable the rule.
    pub fn disable(&mut self) {
        self.enabled = false;
    }

    /// Check if content matches this rule.
    pub fn matches(&self, content: &str) -> bool {
        if !self.enabled {
            return false;
        }

        // Check pattern
        if let Some(ref pattern) = self.pattern {
            if let Ok(re) = regex::Regex::new(pattern) {
                if re.is_match(content) {
                    return true;
                }
            }
        }

        // Check keywords
        let content_lower = content.to_lowercase();
        for keyword in &self.keywords {
            if content_lower.contains(&keyword.to_lowercase()) {
                return true;
            }
        }

        false
    }

    /// Apply the rule to content.
    pub fn apply(&self, content: &str) -> PolicyResult {
        if !self.matches(content) {
            return PolicyResult::pass();
        }

        match self.action {
            PolicyAction::Block => {
                PolicyResult::block(&self.name, self.description.as_deref().unwrap_or("Policy violation"))
            }
            PolicyAction::Warn => {
                PolicyResult::warn(&self.name, self.description.as_deref().unwrap_or("Policy warning"))
            }
            PolicyAction::Redact => {
                let modified = self.redact_content(content);
                PolicyResult::redact(&self.name, modified)
            }
            PolicyAction::Allow | PolicyAction::Log => PolicyResult::pass(),
            PolicyAction::RequireApproval => {
                let mut result = PolicyResult::block(&self.name, "Requires approval");
                result.action = PolicyAction::RequireApproval;
                result
            }
        }
    }

    /// Redact content based on rule.
    fn redact_content(&self, content: &str) -> String {
        let replacement = self.replacement.as_deref().unwrap_or("[REDACTED]");

        let mut result = content.to_string();

        // Redact pattern matches
        if let Some(ref pattern) = self.pattern {
            if let Ok(re) = regex::Regex::new(pattern) {
                result = re.replace_all(&result, replacement).to_string();
            }
        }

        // Redact keywords
        for keyword in &self.keywords {
            result = result.replace(keyword, replacement);
        }

        result
    }
}

// =============================================================================
// POLICY ENGINE
// =============================================================================

/// Engine for evaluating policies.
#[derive(Debug, Default)]
pub struct PolicyEngine {
    /// Rules
    rules: Vec<PolicyRule>,
    /// Whether the engine is enabled
    enabled: bool,
}

impl PolicyEngine {
    /// Create a new engine.
    pub fn new() -> Self {
        Self {
            rules: Vec::new(),
            enabled: true,
        }
    }

    /// Enable the engine.
    pub fn enable(&mut self) {
        self.enabled = true;
    }

    /// Disable the engine.
    pub fn disable(&mut self) {
        self.enabled = false;
    }

    /// Add a rule.
    pub fn add_rule(&mut self, rule: PolicyRule) {
        self.rules.push(rule);
        self.rules.sort_by(|a, b| b.priority.cmp(&a.priority));
    }

    /// Remove a rule by name.
    pub fn remove_rule(&mut self, name: &str) -> Option<PolicyRule> {
        if let Some(pos) = self.rules.iter().position(|r| r.name == name) {
            Some(self.rules.remove(pos))
        } else {
            None
        }
    }

    /// Get a rule by name.
    pub fn get_rule(&self, name: &str) -> Option<&PolicyRule> {
        self.rules.iter().find(|r| r.name == name)
    }

    /// Get mutable rule by name.
    pub fn get_rule_mut(&mut self, name: &str) -> Option<&mut PolicyRule> {
        self.rules.iter_mut().find(|r| r.name == name)
    }

    /// List all rules.
    pub fn list_rules(&self) -> Vec<&PolicyRule> {
        self.rules.iter().collect()
    }

    /// Check content against all rules.
    pub fn check(&self, content: &str) -> PolicyResult {
        if !self.enabled {
            return PolicyResult::pass();
        }

        for rule in &self.rules {
            let result = rule.apply(content);
            if !result.passed || result.action != PolicyAction::Allow {
                return result;
            }
        }

        PolicyResult::pass()
    }

    /// Check and redact content.
    pub fn check_and_redact(&self, content: &str) -> (PolicyResult, String) {
        if !self.enabled {
            return (PolicyResult::pass(), content.to_string());
        }

        let mut modified = content.to_string();
        let mut final_result = PolicyResult::pass();

        for rule in &self.rules {
            if rule.action == PolicyAction::Redact && rule.matches(&modified) {
                modified = rule.redact_content(&modified);
                final_result = PolicyResult::redact(&rule.name, &modified);
            } else {
                let result = rule.apply(&modified);
                if !result.passed {
                    return (result, modified);
                }
            }
        }

        (final_result, modified)
    }

    /// Get rule count.
    pub fn rule_count(&self) -> usize {
        self.rules.len()
    }

    /// Clear all rules.
    pub fn clear(&mut self) {
        self.rules.clear();
    }
}

// =============================================================================
// BUILT-IN RULES
// =============================================================================

/// Create a rule to block PII (Social Security Numbers).
pub fn ssn_rule() -> PolicyRule {
    PolicyRule::new("no-ssn")
        .description("Block Social Security Numbers")
        .pattern(r"\b\d{3}-\d{2}-\d{4}\b")
        .action(PolicyAction::Redact)
        .replacement("[SSN REDACTED]")
}

/// Create a rule to block credit card numbers.
pub fn credit_card_rule() -> PolicyRule {
    PolicyRule::new("no-credit-card")
        .description("Block credit card numbers")
        .pattern(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")
        .action(PolicyAction::Redact)
        .replacement("[CARD REDACTED]")
}

/// Create a rule to block email addresses.
pub fn email_rule() -> PolicyRule {
    PolicyRule::new("no-email")
        .description("Block email addresses")
        .pattern(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
        .action(PolicyAction::Redact)
        .replacement("[EMAIL REDACTED]")
}

/// Create a rule to block phone numbers.
pub fn phone_rule() -> PolicyRule {
    PolicyRule::new("no-phone")
        .description("Block phone numbers")
        .pattern(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
        .action(PolicyAction::Redact)
        .replacement("[PHONE REDACTED]")
}

/// Create a rule to block profanity.
pub fn profanity_rule(words: Vec<String>) -> PolicyRule {
    let mut rule = PolicyRule::new("no-profanity")
        .description("Block profanity")
        .action(PolicyAction::Block);
    
    for word in words {
        rule = rule.keyword(word);
    }
    
    rule
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_policy_rule_new() {
        let rule = PolicyRule::new("test-rule");
        assert_eq!(rule.name, "test-rule");
        assert!(rule.enabled);
    }

    #[test]
    fn test_policy_rule_pattern() {
        let rule = PolicyRule::new("ssn")
            .pattern(r"\d{3}-\d{2}-\d{4}")
            .action(PolicyAction::Block);

        assert!(rule.matches("My SSN is 123-45-6789"));
        assert!(!rule.matches("No SSN here"));
    }

    #[test]
    fn test_policy_rule_keyword() {
        let rule = PolicyRule::new("bad-word")
            .keyword("secret")
            .action(PolicyAction::Block);

        assert!(rule.matches("This is a secret message"));
        assert!(!rule.matches("This is a public message"));
    }

    #[test]
    fn test_policy_rule_redact() {
        let rule = PolicyRule::new("ssn")
            .pattern(r"\d{3}-\d{2}-\d{4}")
            .action(PolicyAction::Redact)
            .replacement("[REDACTED]");

        let result = rule.apply("My SSN is 123-45-6789");
        assert!(result.passed);
        assert_eq!(result.action, PolicyAction::Redact);
        assert_eq!(result.modified_content, Some("My SSN is [REDACTED]".to_string()));
    }

    #[test]
    fn test_policy_engine() {
        let mut engine = PolicyEngine::new();
        engine.add_rule(PolicyRule::new("test").keyword("blocked").action(PolicyAction::Block));

        let result = engine.check("This is blocked content");
        assert!(!result.passed);

        let result = engine.check("This is allowed content");
        assert!(result.passed);
    }

    #[test]
    fn test_policy_engine_priority() {
        let mut engine = PolicyEngine::new();
        engine.add_rule(PolicyRule::new("low").keyword("test").action(PolicyAction::Warn).priority(1));
        engine.add_rule(PolicyRule::new("high").keyword("test").action(PolicyAction::Block).priority(10));

        let result = engine.check("This is a test");
        assert!(!result.passed);
        assert_eq!(result.triggered_rule, Some("high".to_string()));
    }

    #[test]
    fn test_policy_engine_disabled() {
        let mut engine = PolicyEngine::new();
        engine.add_rule(PolicyRule::new("test").keyword("blocked").action(PolicyAction::Block));
        engine.disable();

        let result = engine.check("This is blocked content");
        assert!(result.passed);
    }

    #[test]
    fn test_ssn_rule() {
        let rule = ssn_rule();
        assert!(rule.matches("SSN: 123-45-6789"));
        assert!(!rule.matches("No SSN here"));
    }

    #[test]
    fn test_credit_card_rule() {
        let rule = credit_card_rule();
        assert!(rule.matches("Card: 1234-5678-9012-3456"));
        assert!(rule.matches("Card: 1234567890123456"));
    }

    #[test]
    fn test_email_rule() {
        let rule = email_rule();
        assert!(rule.matches("Email: test@example.com"));
        assert!(!rule.matches("No email here"));
    }

    #[test]
    fn test_check_and_redact() {
        let mut engine = PolicyEngine::new();
        engine.add_rule(ssn_rule());

        let (result, modified) = engine.check_and_redact("My SSN is 123-45-6789");
        assert!(result.passed);
        assert!(modified.contains("[SSN REDACTED]"));
        assert!(!modified.contains("123-45-6789"));
    }
}
