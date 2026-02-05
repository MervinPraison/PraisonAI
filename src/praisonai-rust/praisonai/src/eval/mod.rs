//! Evaluation Module for PraisonAI Rust SDK.
//!
//! Provides comprehensive evaluation capabilities for AI agents.
//!
//! # Example
//!
//! ```ignore
//! use praisonai::eval::{AccuracyEvaluator, EvaluationScore};
//!
//! let evaluator = AccuracyEvaluator::new()
//!     .input("What is 2+2?")
//!     .expected("4")
//!     .build();
//!
//! let result = evaluator.run().await?;
//! println!("Score: {}", result.score);
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};

// =============================================================================
// EVALUATION SCORE
// =============================================================================

/// Score from an evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvaluationScore {
    /// Score value (0.0 to 1.0)
    pub value: f64,
    /// Score reasoning
    pub reasoning: Option<String>,
    /// Confidence level
    pub confidence: Option<f64>,
}

impl EvaluationScore {
    /// Create a new score.
    pub fn new(value: f64) -> Self {
        Self {
            value: value.clamp(0.0, 1.0),
            reasoning: None,
            confidence: None,
        }
    }

    /// Set reasoning.
    pub fn with_reasoning(mut self, reasoning: impl Into<String>) -> Self {
        self.reasoning = Some(reasoning.into());
        self
    }

    /// Set confidence.
    pub fn with_confidence(mut self, confidence: f64) -> Self {
        self.confidence = Some(confidence.clamp(0.0, 1.0));
        self
    }

    /// Check if passing (>= threshold).
    pub fn is_passing(&self, threshold: f64) -> bool {
        self.value >= threshold
    }

    /// Convert to percentage.
    pub fn as_percentage(&self) -> f64 {
        self.value * 100.0
    }
}

impl Default for EvaluationScore {
    fn default() -> Self {
        Self::new(0.0)
    }
}

// =============================================================================
// PERFORMANCE METRICS
// =============================================================================

/// Performance metrics from an evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PerformanceMetrics {
    /// Total duration
    pub duration: Duration,
    /// Time to first token (if applicable)
    pub ttft: Option<Duration>,
    /// Tokens per second
    pub tokens_per_second: Option<f64>,
    /// Memory usage in bytes
    pub memory_bytes: Option<usize>,
    /// Input tokens
    pub input_tokens: Option<usize>,
    /// Output tokens
    pub output_tokens: Option<usize>,
}

impl Default for PerformanceMetrics {
    fn default() -> Self {
        Self {
            duration: Duration::ZERO,
            ttft: None,
            tokens_per_second: None,
            memory_bytes: None,
            input_tokens: None,
            output_tokens: None,
        }
    }
}

impl PerformanceMetrics {
    /// Create new metrics with duration.
    pub fn new(duration: Duration) -> Self {
        Self {
            duration,
            ..Default::default()
        }
    }

    /// Set TTFT.
    pub fn with_ttft(mut self, ttft: Duration) -> Self {
        self.ttft = Some(ttft);
        self
    }

    /// Set tokens per second.
    pub fn with_tokens_per_second(mut self, tps: f64) -> Self {
        self.tokens_per_second = Some(tps);
        self
    }

    /// Set token counts.
    pub fn with_tokens(mut self, input: usize, output: usize) -> Self {
        self.input_tokens = Some(input);
        self.output_tokens = Some(output);
        self
    }
}

// =============================================================================
// TOOL CALL RESULT
// =============================================================================

/// Result of a tool call during evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallResult {
    /// Tool name
    pub name: String,
    /// Whether the call was expected
    pub expected: bool,
    /// Whether the call was made
    pub called: bool,
    /// Arguments used
    pub arguments: Option<serde_json::Value>,
    /// Result returned
    pub result: Option<serde_json::Value>,
}

impl ToolCallResult {
    /// Create a new tool call result.
    pub fn new(name: impl Into<String>, expected: bool, called: bool) -> Self {
        Self {
            name: name.into(),
            expected,
            called,
            arguments: None,
            result: None,
        }
    }

    /// Check if correct (expected == called).
    pub fn is_correct(&self) -> bool {
        self.expected == self.called
    }
}

// =============================================================================
// CRITERIA SCORE
// =============================================================================

/// Score for a specific criterion.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CriteriaScore {
    /// Criterion name
    pub name: String,
    /// Score value
    pub score: f64,
    /// Weight for this criterion
    pub weight: f64,
    /// Feedback
    pub feedback: Option<String>,
}

impl CriteriaScore {
    /// Create a new criteria score.
    pub fn new(name: impl Into<String>, score: f64) -> Self {
        Self {
            name: name.into(),
            score: score.clamp(0.0, 1.0),
            weight: 1.0,
            feedback: None,
        }
    }

    /// Set weight.
    pub fn with_weight(mut self, weight: f64) -> Self {
        self.weight = weight;
        self
    }

    /// Set feedback.
    pub fn with_feedback(mut self, feedback: impl Into<String>) -> Self {
        self.feedback = Some(feedback.into());
        self
    }

    /// Get weighted score.
    pub fn weighted_score(&self) -> f64 {
        self.score * self.weight
    }
}

// =============================================================================
// EVALUATION RESULTS
// =============================================================================

/// Result from an accuracy evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccuracyResult {
    /// Overall score
    pub score: EvaluationScore,
    /// Input text
    pub input: String,
    /// Expected output
    pub expected: String,
    /// Actual output
    pub actual: String,
    /// Whether it passed
    pub passed: bool,
}

/// Result from a performance evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PerformanceResult {
    /// Overall score
    pub score: EvaluationScore,
    /// Performance metrics
    pub metrics: PerformanceMetrics,
    /// Whether it passed
    pub passed: bool,
}

/// Result from a reliability evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReliabilityResult {
    /// Overall score
    pub score: EvaluationScore,
    /// Tool call results
    pub tool_calls: Vec<ToolCallResult>,
    /// Whether it passed
    pub passed: bool,
}

/// Result from a criteria evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CriteriaResult {
    /// Overall score
    pub score: EvaluationScore,
    /// Individual criteria scores
    pub criteria: Vec<CriteriaScore>,
    /// Whether it passed
    pub passed: bool,
}

// =============================================================================
// BASE EVALUATOR
// =============================================================================

/// Base trait for evaluators.
pub trait Evaluator {
    /// Result type for this evaluator.
    type Result;

    /// Run the evaluation.
    fn evaluate(&self) -> Self::Result;
}

/// Configuration for evaluators.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvaluatorConfig {
    /// Passing threshold
    pub threshold: f64,
    /// Whether to print summary
    pub print_summary: bool,
    /// Model to use for LLM-based evaluation
    pub model: Option<String>,
    /// Maximum retries
    pub max_retries: usize,
}

impl Default for EvaluatorConfig {
    fn default() -> Self {
        Self {
            threshold: 0.7,
            print_summary: false,
            model: None,
            max_retries: 3,
        }
    }
}

// =============================================================================
// ACCURACY EVALUATOR
// =============================================================================

/// Evaluator for accuracy (comparing output to expected).
#[derive(Debug, Clone)]
pub struct AccuracyEvaluator {
    /// Input text
    input: String,
    /// Expected output
    expected: String,
    /// Actual output (if already available)
    actual: Option<String>,
    /// Configuration
    config: EvaluatorConfig,
}

impl AccuracyEvaluator {
    /// Create a new builder.
    pub fn new() -> AccuracyEvaluatorBuilder {
        AccuracyEvaluatorBuilder::default()
    }

    /// Evaluate accuracy using simple string comparison.
    pub fn evaluate_simple(&self, actual: &str) -> AccuracyResult {
        let similarity = self.calculate_similarity(&self.expected, actual);
        let score = EvaluationScore::new(similarity);
        let passed = score.is_passing(self.config.threshold);

        AccuracyResult {
            score,
            input: self.input.clone(),
            expected: self.expected.clone(),
            actual: actual.to_string(),
            passed,
        }
    }

    /// Calculate string similarity (Jaccard).
    fn calculate_similarity(&self, a: &str, b: &str) -> f64 {
        let a_words: std::collections::HashSet<_> = a.split_whitespace().collect();
        let b_words: std::collections::HashSet<_> = b.split_whitespace().collect();

        if a_words.is_empty() && b_words.is_empty() {
            return 1.0;
        }

        let intersection = a_words.intersection(&b_words).count();
        let union = a_words.union(&b_words).count();

        if union == 0 {
            0.0
        } else {
            intersection as f64 / union as f64
        }
    }
}

impl Default for AccuracyEvaluator {
    fn default() -> Self {
        Self {
            input: String::new(),
            expected: String::new(),
            actual: None,
            config: EvaluatorConfig::default(),
        }
    }
}

/// Builder for AccuracyEvaluator.
#[derive(Debug, Default)]
pub struct AccuracyEvaluatorBuilder {
    input: Option<String>,
    expected: Option<String>,
    actual: Option<String>,
    config: EvaluatorConfig,
}

impl AccuracyEvaluatorBuilder {
    /// Set input text.
    pub fn input(mut self, input: impl Into<String>) -> Self {
        self.input = Some(input.into());
        self
    }

    /// Set expected output.
    pub fn expected(mut self, expected: impl Into<String>) -> Self {
        self.expected = Some(expected.into());
        self
    }

    /// Set actual output.
    pub fn actual(mut self, actual: impl Into<String>) -> Self {
        self.actual = Some(actual.into());
        self
    }

    /// Set threshold.
    pub fn threshold(mut self, threshold: f64) -> Self {
        self.config.threshold = threshold;
        self
    }

    /// Build the evaluator.
    pub fn build(self) -> AccuracyEvaluator {
        AccuracyEvaluator {
            input: self.input.unwrap_or_default(),
            expected: self.expected.unwrap_or_default(),
            actual: self.actual,
            config: self.config,
        }
    }
}

// =============================================================================
// PERFORMANCE EVALUATOR
// =============================================================================

/// Evaluator for performance metrics.
#[derive(Debug, Clone)]
pub struct PerformanceEvaluator {
    /// Maximum allowed duration
    max_duration: Duration,
    /// Maximum allowed TTFT
    max_ttft: Option<Duration>,
    /// Configuration
    config: EvaluatorConfig,
}

impl PerformanceEvaluator {
    /// Create a new builder.
    pub fn new() -> PerformanceEvaluatorBuilder {
        PerformanceEvaluatorBuilder::default()
    }

    /// Evaluate performance metrics.
    pub fn evaluate(&self, metrics: &PerformanceMetrics) -> PerformanceResult {
        let mut score = 1.0;

        // Penalize for duration
        if metrics.duration > self.max_duration {
            let ratio = self.max_duration.as_secs_f64() / metrics.duration.as_secs_f64();
            score *= ratio;
        }

        // Penalize for TTFT
        if let (Some(max_ttft), Some(ttft)) = (self.max_ttft, metrics.ttft) {
            if ttft > max_ttft {
                let ratio = max_ttft.as_secs_f64() / ttft.as_secs_f64();
                score *= ratio;
            }
        }

        let eval_score = EvaluationScore::new(score);
        let passed = eval_score.is_passing(self.config.threshold);

        PerformanceResult {
            score: eval_score,
            metrics: metrics.clone(),
            passed,
        }
    }
}

impl Default for PerformanceEvaluator {
    fn default() -> Self {
        Self {
            max_duration: Duration::from_secs(30),
            max_ttft: None,
            config: EvaluatorConfig::default(),
        }
    }
}

/// Builder for PerformanceEvaluator.
#[derive(Debug, Default)]
pub struct PerformanceEvaluatorBuilder {
    max_duration: Option<Duration>,
    max_ttft: Option<Duration>,
    config: EvaluatorConfig,
}

impl PerformanceEvaluatorBuilder {
    /// Set maximum duration.
    pub fn max_duration(mut self, duration: Duration) -> Self {
        self.max_duration = Some(duration);
        self
    }

    /// Set maximum TTFT.
    pub fn max_ttft(mut self, ttft: Duration) -> Self {
        self.max_ttft = Some(ttft);
        self
    }

    /// Set threshold.
    pub fn threshold(mut self, threshold: f64) -> Self {
        self.config.threshold = threshold;
        self
    }

    /// Build the evaluator.
    pub fn build(self) -> PerformanceEvaluator {
        PerformanceEvaluator {
            max_duration: self.max_duration.unwrap_or(Duration::from_secs(30)),
            max_ttft: self.max_ttft,
            config: self.config,
        }
    }
}

// =============================================================================
// RELIABILITY EVALUATOR
// =============================================================================

/// Evaluator for reliability (tool call verification).
#[derive(Debug, Clone)]
pub struct ReliabilityEvaluator {
    /// Expected tool calls
    expected_tools: Vec<String>,
    /// Configuration
    config: EvaluatorConfig,
}

impl ReliabilityEvaluator {
    /// Create a new builder.
    pub fn new() -> ReliabilityEvaluatorBuilder {
        ReliabilityEvaluatorBuilder::default()
    }

    /// Evaluate tool calls.
    pub fn evaluate(&self, called_tools: &[String]) -> ReliabilityResult {
        let mut results = Vec::new();
        let mut correct = 0;

        for expected in &self.expected_tools {
            let called = called_tools.contains(expected);
            if called {
                correct += 1;
            }
            results.push(ToolCallResult::new(expected, true, called));
        }

        let score = if self.expected_tools.is_empty() {
            1.0
        } else {
            correct as f64 / self.expected_tools.len() as f64
        };

        let eval_score = EvaluationScore::new(score);
        let passed = eval_score.is_passing(self.config.threshold);

        ReliabilityResult {
            score: eval_score,
            tool_calls: results,
            passed,
        }
    }
}

impl Default for ReliabilityEvaluator {
    fn default() -> Self {
        Self {
            expected_tools: Vec::new(),
            config: EvaluatorConfig::default(),
        }
    }
}

/// Builder for ReliabilityEvaluator.
#[derive(Debug, Default)]
pub struct ReliabilityEvaluatorBuilder {
    expected_tools: Vec<String>,
    config: EvaluatorConfig,
}

impl ReliabilityEvaluatorBuilder {
    /// Add expected tool.
    pub fn expect_tool(mut self, tool: impl Into<String>) -> Self {
        self.expected_tools.push(tool.into());
        self
    }

    /// Set threshold.
    pub fn threshold(mut self, threshold: f64) -> Self {
        self.config.threshold = threshold;
        self
    }

    /// Build the evaluator.
    pub fn build(self) -> ReliabilityEvaluator {
        ReliabilityEvaluator {
            expected_tools: self.expected_tools,
            config: self.config,
        }
    }
}

// =============================================================================
// CRITERIA EVALUATOR
// =============================================================================

/// Evaluator for custom criteria.
#[derive(Debug, Clone)]
pub struct CriteriaEvaluator {
    /// Criteria to evaluate
    criteria: Vec<String>,
    /// Configuration
    config: EvaluatorConfig,
}

impl CriteriaEvaluator {
    /// Create a new builder.
    pub fn new() -> CriteriaEvaluatorBuilder {
        CriteriaEvaluatorBuilder::default()
    }

    /// Evaluate with provided scores.
    pub fn evaluate(&self, scores: &HashMap<String, f64>) -> CriteriaResult {
        let mut criteria_scores = Vec::new();
        let mut total_score = 0.0;
        let mut total_weight = 0.0;

        for criterion in &self.criteria {
            let score = scores.get(criterion).copied().unwrap_or(0.0);
            criteria_scores.push(CriteriaScore::new(criterion, score));
            total_score += score;
            total_weight += 1.0;
        }

        let avg_score = if total_weight > 0.0 {
            total_score / total_weight
        } else {
            0.0
        };

        let eval_score = EvaluationScore::new(avg_score);
        let passed = eval_score.is_passing(self.config.threshold);

        CriteriaResult {
            score: eval_score,
            criteria: criteria_scores,
            passed,
        }
    }
}

impl Default for CriteriaEvaluator {
    fn default() -> Self {
        Self {
            criteria: Vec::new(),
            config: EvaluatorConfig::default(),
        }
    }
}

/// Builder for CriteriaEvaluator.
#[derive(Debug, Default)]
pub struct CriteriaEvaluatorBuilder {
    criteria: Vec<String>,
    config: EvaluatorConfig,
}

impl CriteriaEvaluatorBuilder {
    /// Add a criterion.
    pub fn criterion(mut self, criterion: impl Into<String>) -> Self {
        self.criteria.push(criterion.into());
        self
    }

    /// Set threshold.
    pub fn threshold(mut self, threshold: f64) -> Self {
        self.config.threshold = threshold;
        self
    }

    /// Build the evaluator.
    pub fn build(self) -> CriteriaEvaluator {
        CriteriaEvaluator {
            criteria: self.criteria,
            config: self.config,
        }
    }
}

// =============================================================================
// JUDGE
// =============================================================================

/// Configuration for a judge.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JudgeConfig {
    /// Model to use
    pub model: String,
    /// Temperature
    pub temperature: f64,
    /// System prompt
    pub system_prompt: Option<String>,
}

impl Default for JudgeConfig {
    fn default() -> Self {
        Self {
            model: "gpt-4o-mini".to_string(),
            temperature: 0.0,
            system_prompt: None,
        }
    }
}

/// Result from a judge.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JudgeResult {
    /// Score
    pub score: f64,
    /// Reasoning
    pub reasoning: String,
    /// Pass/fail
    pub passed: bool,
    /// Metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl JudgeResult {
    /// Create a new result.
    pub fn new(score: f64, reasoning: impl Into<String>, passed: bool) -> Self {
        Self {
            score,
            reasoning: reasoning.into(),
            passed,
            metadata: HashMap::new(),
        }
    }
}

/// A judge for evaluating outputs.
#[derive(Debug, Clone)]
pub struct Judge {
    /// Judge name
    pub name: String,
    /// Configuration
    pub config: JudgeConfig,
    /// Threshold for passing
    pub threshold: f64,
}

impl Judge {
    /// Create a new judge.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            config: JudgeConfig::default(),
            threshold: 0.7,
        }
    }

    /// Set configuration.
    pub fn with_config(mut self, config: JudgeConfig) -> Self {
        self.config = config;
        self
    }

    /// Set threshold.
    pub fn with_threshold(mut self, threshold: f64) -> Self {
        self.threshold = threshold;
        self
    }

    /// Judge an output (placeholder - would use LLM in real implementation).
    pub fn judge(&self, _input: &str, _output: &str, _expected: Option<&str>) -> JudgeResult {
        // Placeholder implementation
        JudgeResult::new(0.8, "Placeholder evaluation", true)
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_evaluation_score() {
        let score = EvaluationScore::new(0.85);
        assert!((score.value - 0.85).abs() < 0.001);
        assert!(score.is_passing(0.7));
        assert!(!score.is_passing(0.9));
    }

    #[test]
    fn test_evaluation_score_clamp() {
        let score = EvaluationScore::new(1.5);
        assert!((score.value - 1.0).abs() < 0.001);

        let score = EvaluationScore::new(-0.5);
        assert!((score.value - 0.0).abs() < 0.001);
    }

    #[test]
    fn test_accuracy_evaluator() {
        let evaluator = AccuracyEvaluator::new()
            .input("What is 2+2?")
            .expected("The answer is 4")
            .threshold(0.5)
            .build();

        let result = evaluator.evaluate_simple("The answer is 4");
        assert!(result.passed);
        assert!((result.score.value - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_accuracy_evaluator_partial() {
        let evaluator = AccuracyEvaluator::new()
            .input("What is 2+2?")
            .expected("The answer is 4")
            .threshold(0.3)
            .build();

        let result = evaluator.evaluate_simple("The answer is 5");
        assert!(result.score.value > 0.0);
        assert!(result.score.value < 1.0);
    }

    #[test]
    fn test_performance_evaluator() {
        let evaluator = PerformanceEvaluator::new()
            .max_duration(Duration::from_secs(10))
            .threshold(0.5)
            .build();

        let metrics = PerformanceMetrics::new(Duration::from_secs(5));
        let result = evaluator.evaluate(&metrics);
        assert!(result.passed);
    }

    #[test]
    fn test_performance_evaluator_slow() {
        let evaluator = PerformanceEvaluator::new()
            .max_duration(Duration::from_secs(10))
            .threshold(0.9)
            .build();

        let metrics = PerformanceMetrics::new(Duration::from_secs(20));
        let result = evaluator.evaluate(&metrics);
        assert!(!result.passed);
    }

    #[test]
    fn test_reliability_evaluator() {
        let evaluator = ReliabilityEvaluator::new()
            .expect_tool("search")
            .expect_tool("calculate")
            .threshold(0.5)
            .build();

        let called = vec!["search".to_string()];
        let result = evaluator.evaluate(&called);
        assert!((result.score.value - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_criteria_evaluator() {
        let evaluator = CriteriaEvaluator::new()
            .criterion("accuracy")
            .criterion("clarity")
            .threshold(0.6)
            .build();

        let mut scores = HashMap::new();
        scores.insert("accuracy".to_string(), 0.8);
        scores.insert("clarity".to_string(), 0.7);

        let result = evaluator.evaluate(&scores);
        assert!(result.passed);
        assert!((result.score.value - 0.75).abs() < 0.001);
    }

    #[test]
    fn test_judge() {
        let judge = Judge::new("test-judge").with_threshold(0.5);
        let result = judge.judge("input", "output", Some("expected"));
        assert!(result.passed);
    }

    #[test]
    fn test_tool_call_result() {
        let result = ToolCallResult::new("search", true, true);
        assert!(result.is_correct());

        let result = ToolCallResult::new("search", true, false);
        assert!(!result.is_correct());
    }

    #[test]
    fn test_criteria_score() {
        let score = CriteriaScore::new("accuracy", 0.8).with_weight(2.0);
        assert!((score.weighted_score() - 1.6).abs() < 0.001);
    }
}
