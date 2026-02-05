//! Conditions Module for PraisonAI Rust SDK
//!
//! Provides condition protocols and implementations for workflow routing.
//! Enables unified condition evaluation across AgentFlow and AgentTeam.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::conditions::{ExpressionCondition, DictCondition};
//!
//! // Expression-based condition
//! let cond = ExpressionCondition::new("score > 80");
//! let result = cond.evaluate(&context);
//!
//! // Dictionary-based condition
//! let cond = DictCondition::new()
//!     .when("approved", vec!["review_task"])
//!     .when("rejected", vec!["revision_task"]);
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Protocol trait for condition implementations.
///
/// This defines the essential interface that any condition must provide.
/// It enables unified condition evaluation across AgentFlow (string-based)
/// and AgentTeam (dict-based) systems.
pub trait ConditionProtocol: Send + Sync {
    /// Evaluate the condition against the given context.
    ///
    /// # Arguments
    ///
    /// * `context` - Dictionary containing variables for evaluation.
    ///               May include workflow variables, previous outputs, etc.
    ///
    /// # Returns
    ///
    /// Boolean result of condition evaluation.
    /// Returns false on evaluation errors (fail-safe).
    fn evaluate(&self, context: &HashMap<String, serde_json::Value>) -> bool;
}

/// Extended protocol for conditions that support routing to targets.
///
/// This extends ConditionProtocol with the ability to return target
/// tasks/steps based on the condition evaluation.
pub trait RoutingConditionProtocol: ConditionProtocol {
    /// Get the target tasks/steps based on condition evaluation.
    ///
    /// # Arguments
    ///
    /// * `context` - Dictionary containing variables for evaluation.
    ///
    /// # Returns
    ///
    /// List of target task/step names to route to.
    /// Returns empty list if no match found.
    fn get_target(&self, context: &HashMap<String, serde_json::Value>) -> Vec<String>;
}

/// Simple expression-based condition.
///
/// Evaluates simple expressions like "score > 80" or "status == 'approved'".
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExpressionCondition {
    /// The expression to evaluate
    pub expression: String,
}

impl ExpressionCondition {
    /// Create a new expression condition.
    pub fn new(expression: impl Into<String>) -> Self {
        Self {
            expression: expression.into(),
        }
    }

    /// Parse and evaluate a simple comparison expression.
    fn evaluate_expression(&self, context: &HashMap<String, serde_json::Value>) -> bool {
        let expr = self.expression.trim();

        // Handle simple boolean variable
        if !expr.contains('>') && !expr.contains('<') && !expr.contains('=') && !expr.contains("!=") {
            return context
                .get(expr)
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
        }

        // Parse comparison operators
        let operators = [">=", "<=", "!=", "==", ">", "<"];
        for op in operators {
            if let Some(pos) = expr.find(op) {
                let left = expr[..pos].trim();
                let right = expr[pos + op.len()..].trim();
                return self.compare(left, op, right, context);
            }
        }

        false
    }

    /// Compare two values with an operator.
    fn compare(
        &self,
        left: &str,
        op: &str,
        right: &str,
        context: &HashMap<String, serde_json::Value>,
    ) -> bool {
        // Get left value from context
        let left_val = context.get(left);

        // Parse right value (could be literal or variable)
        let right_val = if right.starts_with('\'') || right.starts_with('"') {
            // String literal
            let s = right.trim_matches(|c| c == '\'' || c == '"');
            Some(serde_json::json!(s))
        } else if let Ok(n) = right.parse::<f64>() {
            // Number literal
            Some(serde_json::json!(n))
        } else if right == "true" {
            Some(serde_json::json!(true))
        } else if right == "false" {
            Some(serde_json::json!(false))
        } else {
            // Variable reference
            context.get(right).cloned()
        };

        match (left_val, right_val) {
            (Some(l), Some(r)) => {
                // Try numeric comparison first
                if let (Some(ln), Some(rn)) = (l.as_f64(), r.as_f64()) {
                    return match op {
                        ">" => ln > rn,
                        "<" => ln < rn,
                        ">=" => ln >= rn,
                        "<=" => ln <= rn,
                        "==" => (ln - rn).abs() < f64::EPSILON,
                        "!=" => (ln - rn).abs() >= f64::EPSILON,
                        _ => false,
                    };
                }

                // String comparison
                if let (Some(ls), Some(rs)) = (l.as_str(), r.as_str()) {
                    return match op {
                        "==" => ls == rs,
                        "!=" => ls != rs,
                        ">" => ls > rs,
                        "<" => ls < rs,
                        ">=" => ls >= rs,
                        "<=" => ls <= rs,
                        _ => false,
                    };
                }

                // Boolean comparison
                if let (Some(lb), Some(rb)) = (l.as_bool(), r.as_bool()) {
                    return match op {
                        "==" => lb == rb,
                        "!=" => lb != rb,
                        _ => false,
                    };
                }

                // Generic equality
                match op {
                    "==" => l == &r,
                    "!=" => l != &r,
                    _ => false,
                }
            }
            _ => false,
        }
    }
}

impl ConditionProtocol for ExpressionCondition {
    fn evaluate(&self, context: &HashMap<String, serde_json::Value>) -> bool {
        self.evaluate_expression(context)
    }
}

/// Dictionary-based condition for routing.
///
/// Maps values to target tasks/steps.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DictCondition {
    /// Variable name to check
    pub variable: String,
    /// Mapping of values to target tasks
    pub routes: HashMap<String, Vec<String>>,
    /// Default targets if no match
    pub default: Vec<String>,
}

impl DictCondition {
    /// Create a new dict condition.
    pub fn new(variable: impl Into<String>) -> Self {
        Self {
            variable: variable.into(),
            routes: HashMap::new(),
            default: Vec::new(),
        }
    }

    /// Add a route for a value.
    pub fn when(mut self, value: impl Into<String>, targets: Vec<String>) -> Self {
        self.routes.insert(value.into(), targets);
        self
    }

    /// Set default targets.
    pub fn default_targets(mut self, targets: Vec<String>) -> Self {
        self.default = targets;
        self
    }
}

impl ConditionProtocol for DictCondition {
    fn evaluate(&self, context: &HashMap<String, serde_json::Value>) -> bool {
        if let Some(value) = context.get(&self.variable) {
            let key = match value {
                serde_json::Value::String(s) => s.clone(),
                serde_json::Value::Bool(b) => b.to_string(),
                serde_json::Value::Number(n) => n.to_string(),
                _ => return !self.default.is_empty(),
            };
            self.routes.contains_key(&key) || !self.default.is_empty()
        } else {
            !self.default.is_empty()
        }
    }
}

impl RoutingConditionProtocol for DictCondition {
    fn get_target(&self, context: &HashMap<String, serde_json::Value>) -> Vec<String> {
        if let Some(value) = context.get(&self.variable) {
            let key = match value {
                serde_json::Value::String(s) => s.clone(),
                serde_json::Value::Bool(b) => b.to_string(),
                serde_json::Value::Number(n) => n.to_string(),
                _ => return self.default.clone(),
            };
            self.routes.get(&key).cloned().unwrap_or_else(|| self.default.clone())
        } else {
            self.default.clone()
        }
    }
}

/// Closure-based condition.
///
/// Wraps a closure for custom condition logic.
pub struct ClosureCondition<F>
where
    F: Fn(&HashMap<String, serde_json::Value>) -> bool + Send + Sync,
{
    condition: F,
}

impl<F> ClosureCondition<F>
where
    F: Fn(&HashMap<String, serde_json::Value>) -> bool + Send + Sync,
{
    /// Create a new closure condition.
    pub fn new(condition: F) -> Self {
        Self { condition }
    }
}

impl<F> ConditionProtocol for ClosureCondition<F>
where
    F: Fn(&HashMap<String, serde_json::Value>) -> bool + Send + Sync,
{
    fn evaluate(&self, context: &HashMap<String, serde_json::Value>) -> bool {
        (self.condition)(context)
    }
}

/// Evaluate a condition expression against a context.
///
/// Convenience function for simple condition evaluation.
pub fn evaluate_condition(
    expression: &str,
    context: &HashMap<String, serde_json::Value>,
) -> bool {
    ExpressionCondition::new(expression).evaluate(context)
}

/// Builder for creating conditions.
pub struct If;

impl If {
    /// Create an expression condition.
    pub fn expr(expression: impl Into<String>) -> ExpressionCondition {
        ExpressionCondition::new(expression)
    }

    /// Create a dict condition.
    pub fn dict(variable: impl Into<String>) -> DictCondition {
        DictCondition::new(variable)
    }

    /// Create a closure condition.
    pub fn closure<F>(f: F) -> ClosureCondition<F>
    where
        F: Fn(&HashMap<String, serde_json::Value>) -> bool + Send + Sync,
    {
        ClosureCondition::new(f)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_context(pairs: &[(&str, serde_json::Value)]) -> HashMap<String, serde_json::Value> {
        pairs.iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
    }

    #[test]
    fn test_expression_condition_numeric_greater() {
        let cond = ExpressionCondition::new("score > 80");
        
        let ctx = make_context(&[("score", serde_json::json!(90))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("score", serde_json::json!(70))]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_expression_condition_numeric_equal() {
        let cond = ExpressionCondition::new("count == 5");
        
        let ctx = make_context(&[("count", serde_json::json!(5))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("count", serde_json::json!(3))]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_expression_condition_string_equal() {
        let cond = ExpressionCondition::new("status == 'approved'");
        
        let ctx = make_context(&[("status", serde_json::json!("approved"))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("status", serde_json::json!("rejected"))]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_expression_condition_not_equal() {
        let cond = ExpressionCondition::new("status != 'pending'");
        
        let ctx = make_context(&[("status", serde_json::json!("approved"))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("status", serde_json::json!("pending"))]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_expression_condition_boolean() {
        let cond = ExpressionCondition::new("is_valid");
        
        let ctx = make_context(&[("is_valid", serde_json::json!(true))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("is_valid", serde_json::json!(false))]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_expression_condition_missing_variable() {
        let cond = ExpressionCondition::new("score > 80");
        let ctx = make_context(&[]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_dict_condition_basic() {
        let cond = DictCondition::new("decision")
            .when("approved", vec!["process_task".to_string()])
            .when("rejected", vec!["revision_task".to_string()]);

        let ctx = make_context(&[("decision", serde_json::json!("approved"))]);
        assert!(cond.evaluate(&ctx));
        assert_eq!(cond.get_target(&ctx), vec!["process_task"]);

        let ctx = make_context(&[("decision", serde_json::json!("rejected"))]);
        assert!(cond.evaluate(&ctx));
        assert_eq!(cond.get_target(&ctx), vec!["revision_task"]);
    }

    #[test]
    fn test_dict_condition_default() {
        let cond = DictCondition::new("decision")
            .when("approved", vec!["process_task".to_string()])
            .default_targets(vec!["fallback_task".to_string()]);

        let ctx = make_context(&[("decision", serde_json::json!("unknown"))]);
        assert!(cond.evaluate(&ctx));
        assert_eq!(cond.get_target(&ctx), vec!["fallback_task"]);
    }

    #[test]
    fn test_dict_condition_no_match_no_default() {
        let cond = DictCondition::new("decision")
            .when("approved", vec!["process_task".to_string()]);

        let ctx = make_context(&[("decision", serde_json::json!("unknown"))]);
        assert!(!cond.evaluate(&ctx));
        assert!(cond.get_target(&ctx).is_empty());
    }

    #[test]
    fn test_closure_condition() {
        let cond = ClosureCondition::new(|ctx| {
            ctx.get("score")
                .and_then(|v| v.as_f64())
                .map(|s| s > 80.0)
                .unwrap_or(false)
        });

        let ctx = make_context(&[("score", serde_json::json!(90))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("score", serde_json::json!(70))]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_evaluate_condition_function() {
        let ctx = make_context(&[("score", serde_json::json!(90))]);
        assert!(evaluate_condition("score > 80", &ctx));
        assert!(!evaluate_condition("score < 80", &ctx));
    }

    #[test]
    fn test_if_builder() {
        let expr_cond = If::expr("score > 80");
        let ctx = make_context(&[("score", serde_json::json!(90))]);
        assert!(expr_cond.evaluate(&ctx));

        let dict_cond = If::dict("status")
            .when("ok", vec!["proceed".to_string()]);
        let ctx = make_context(&[("status", serde_json::json!("ok"))]);
        assert!(dict_cond.evaluate(&ctx));
    }

    #[test]
    fn test_expression_condition_greater_equal() {
        let cond = ExpressionCondition::new("score >= 80");
        
        let ctx = make_context(&[("score", serde_json::json!(80))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("score", serde_json::json!(79))]);
        assert!(!cond.evaluate(&ctx));
    }

    #[test]
    fn test_expression_condition_less_than() {
        let cond = ExpressionCondition::new("score < 50");
        
        let ctx = make_context(&[("score", serde_json::json!(30))]);
        assert!(cond.evaluate(&ctx));

        let ctx = make_context(&[("score", serde_json::json!(60))]);
        assert!(!cond.evaluate(&ctx));
    }
}
