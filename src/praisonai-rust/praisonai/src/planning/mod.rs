//! Planning Module for PraisonAI Rust SDK.
//!
//! Provides Planning Mode functionality similar to:
//! - Cursor Plan Mode
//! - Windsurf Planning Mode
//! - Claude Code Plan Mode
//!
//! # Example
//!
//! ```ignore
//! use praisonai::planning::{Plan, PlanStep, TodoList, PlanStorage};
//!
//! let mut plan = Plan::new("Implement feature X");
//! plan.add_step(PlanStep::new("Research requirements"));
//! plan.add_step(PlanStep::new("Write tests"));
//! plan.add_step(PlanStep::new("Implement code"));
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

// =============================================================================
// PLAN STEP
// =============================================================================

/// Status of a plan step.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StepStatus {
    Pending,
    InProgress,
    Completed,
    Failed,
    Skipped,
}

impl Default for StepStatus {
    fn default() -> Self {
        StepStatus::Pending
    }
}

/// A single step in a plan.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanStep {
    /// Step ID
    pub id: String,
    /// Step description
    pub description: String,
    /// Step status
    pub status: StepStatus,
    /// Dependencies (step IDs)
    pub dependencies: Vec<String>,
    /// Output from this step
    pub output: Option<String>,
    /// Error message if failed
    pub error: Option<String>,
    /// Estimated duration in seconds
    pub estimated_duration: Option<u64>,
    /// Actual duration in seconds
    pub actual_duration: Option<u64>,
}

impl PlanStep {
    /// Create a new plan step.
    pub fn new(description: impl Into<String>) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            description: description.into(),
            status: StepStatus::Pending,
            dependencies: Vec::new(),
            output: None,
            error: None,
            estimated_duration: None,
            actual_duration: None,
        }
    }

    /// Add a dependency.
    pub fn depends_on(mut self, step_id: impl Into<String>) -> Self {
        self.dependencies.push(step_id.into());
        self
    }

    /// Set estimated duration.
    pub fn estimated(mut self, seconds: u64) -> Self {
        self.estimated_duration = Some(seconds);
        self
    }

    /// Mark as in progress.
    pub fn start(&mut self) {
        self.status = StepStatus::InProgress;
    }

    /// Mark as completed.
    pub fn complete(&mut self, output: Option<String>) {
        self.status = StepStatus::Completed;
        self.output = output;
    }

    /// Mark as failed.
    pub fn fail(&mut self, error: impl Into<String>) {
        self.status = StepStatus::Failed;
        self.error = Some(error.into());
    }

    /// Mark as skipped.
    pub fn skip(&mut self) {
        self.status = StepStatus::Skipped;
    }

    /// Check if step is ready to execute.
    pub fn is_ready(&self, completed_steps: &[String]) -> bool {
        self.status == StepStatus::Pending
            && self.dependencies.iter().all(|d| completed_steps.contains(d))
    }
}

// =============================================================================
// PLAN
// =============================================================================

/// A plan consisting of multiple steps.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    /// Plan ID
    pub id: String,
    /// Plan name/goal
    pub name: String,
    /// Plan description
    pub description: Option<String>,
    /// Steps in the plan
    pub steps: Vec<PlanStep>,
    /// Created timestamp
    pub created_at: chrono::DateTime<chrono::Utc>,
    /// Updated timestamp
    pub updated_at: chrono::DateTime<chrono::Utc>,
    /// Plan metadata
    pub metadata: HashMap<String, String>,
}

impl Plan {
    /// Create a new plan.
    pub fn new(name: impl Into<String>) -> Self {
        let now = chrono::Utc::now();
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            name: name.into(),
            description: None,
            steps: Vec::new(),
            created_at: now,
            updated_at: now,
            metadata: HashMap::new(),
        }
    }

    /// Set description.
    pub fn description(mut self, desc: impl Into<String>) -> Self {
        self.description = Some(desc.into());
        self
    }

    /// Add a step.
    pub fn add_step(&mut self, step: PlanStep) {
        self.steps.push(step);
        self.updated_at = chrono::Utc::now();
    }

    /// Get step by ID.
    pub fn get_step(&self, id: &str) -> Option<&PlanStep> {
        self.steps.iter().find(|s| s.id == id)
    }

    /// Get mutable step by ID.
    pub fn get_step_mut(&mut self, id: &str) -> Option<&mut PlanStep> {
        self.steps.iter_mut().find(|s| s.id == id)
    }

    /// Get completed step IDs.
    pub fn completed_steps(&self) -> Vec<String> {
        self.steps
            .iter()
            .filter(|s| s.status == StepStatus::Completed)
            .map(|s| s.id.clone())
            .collect()
    }

    /// Get next ready step.
    pub fn next_step(&self) -> Option<&PlanStep> {
        let completed = self.completed_steps();
        self.steps.iter().find(|s| s.is_ready(&completed))
    }

    /// Get progress percentage.
    pub fn progress(&self) -> f64 {
        if self.steps.is_empty() {
            return 0.0;
        }
        let completed = self.steps.iter().filter(|s| s.status == StepStatus::Completed).count();
        completed as f64 / self.steps.len() as f64 * 100.0
    }

    /// Check if plan is complete.
    pub fn is_complete(&self) -> bool {
        self.steps.iter().all(|s| {
            s.status == StepStatus::Completed || s.status == StepStatus::Skipped
        })
    }

    /// Check if plan has failed.
    pub fn has_failed(&self) -> bool {
        self.steps.iter().any(|s| s.status == StepStatus::Failed)
    }

    /// Get step count.
    pub fn step_count(&self) -> usize {
        self.steps.len()
    }
}

// =============================================================================
// TODO LIST
// =============================================================================

/// Priority of a todo item.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TodoPriority {
    Low,
    Medium,
    High,
    Critical,
}

impl Default for TodoPriority {
    fn default() -> Self {
        TodoPriority::Medium
    }
}

/// A todo item.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TodoItem {
    /// Item ID
    pub id: String,
    /// Item content
    pub content: String,
    /// Item status
    pub status: StepStatus,
    /// Priority
    pub priority: TodoPriority,
    /// Tags
    pub tags: Vec<String>,
    /// Due date
    pub due_date: Option<chrono::DateTime<chrono::Utc>>,
    /// Created timestamp
    pub created_at: chrono::DateTime<chrono::Utc>,
}

impl TodoItem {
    /// Create a new todo item.
    pub fn new(content: impl Into<String>) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            content: content.into(),
            status: StepStatus::Pending,
            priority: TodoPriority::Medium,
            tags: Vec::new(),
            due_date: None,
            created_at: chrono::Utc::now(),
        }
    }

    /// Set priority.
    pub fn priority(mut self, priority: TodoPriority) -> Self {
        self.priority = priority;
        self
    }

    /// Add a tag.
    pub fn tag(mut self, tag: impl Into<String>) -> Self {
        self.tags.push(tag.into());
        self
    }

    /// Set due date.
    pub fn due(mut self, date: chrono::DateTime<chrono::Utc>) -> Self {
        self.due_date = Some(date);
        self
    }

    /// Mark as completed.
    pub fn complete(&mut self) {
        self.status = StepStatus::Completed;
    }

    /// Check if overdue.
    pub fn is_overdue(&self) -> bool {
        if let Some(due) = self.due_date {
            chrono::Utc::now() > due && self.status != StepStatus::Completed
        } else {
            false
        }
    }
}

/// A todo list.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TodoList {
    /// List name
    pub name: String,
    /// Items in the list
    pub items: Vec<TodoItem>,
}

impl TodoList {
    /// Create a new todo list.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            items: Vec::new(),
        }
    }

    /// Add an item.
    pub fn add(&mut self, item: TodoItem) {
        self.items.push(item);
    }

    /// Get item by ID.
    pub fn get(&self, id: &str) -> Option<&TodoItem> {
        self.items.iter().find(|i| i.id == id)
    }

    /// Get mutable item by ID.
    pub fn get_mut(&mut self, id: &str) -> Option<&mut TodoItem> {
        self.items.iter_mut().find(|i| i.id == id)
    }

    /// Remove item by ID.
    pub fn remove(&mut self, id: &str) -> Option<TodoItem> {
        if let Some(pos) = self.items.iter().position(|i| i.id == id) {
            Some(self.items.remove(pos))
        } else {
            None
        }
    }

    /// Get pending items.
    pub fn pending(&self) -> Vec<&TodoItem> {
        self.items.iter().filter(|i| i.status == StepStatus::Pending).collect()
    }

    /// Get completed items.
    pub fn completed(&self) -> Vec<&TodoItem> {
        self.items.iter().filter(|i| i.status == StepStatus::Completed).collect()
    }

    /// Get overdue items.
    pub fn overdue(&self) -> Vec<&TodoItem> {
        self.items.iter().filter(|i| i.is_overdue()).collect()
    }

    /// Get items by tag.
    pub fn by_tag(&self, tag: &str) -> Vec<&TodoItem> {
        self.items.iter().filter(|i| i.tags.contains(&tag.to_string())).collect()
    }

    /// Get items by priority.
    pub fn by_priority(&self, priority: TodoPriority) -> Vec<&TodoItem> {
        self.items.iter().filter(|i| i.priority == priority).collect()
    }

    /// Get item count.
    pub fn len(&self) -> usize {
        self.items.len()
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    /// Get progress percentage.
    pub fn progress(&self) -> f64 {
        if self.items.is_empty() {
            return 0.0;
        }
        let completed = self.items.iter().filter(|i| i.status == StepStatus::Completed).count();
        completed as f64 / self.items.len() as f64 * 100.0
    }
}

// =============================================================================
// PLAN STORAGE
// =============================================================================

/// Storage for plans.
#[derive(Debug, Default)]
pub struct PlanStorage {
    /// Plans by ID
    plans: HashMap<String, Plan>,
    /// Storage path
    path: Option<PathBuf>,
}

impl PlanStorage {
    /// Create a new storage.
    pub fn new() -> Self {
        Self::default()
    }

    /// Create with file path.
    pub fn with_path(path: impl Into<PathBuf>) -> Self {
        Self {
            plans: HashMap::new(),
            path: Some(path.into()),
        }
    }

    /// Save a plan.
    pub fn save(&mut self, plan: Plan) {
        self.plans.insert(plan.id.clone(), plan);
    }

    /// Load a plan by ID.
    pub fn load(&self, id: &str) -> Option<&Plan> {
        self.plans.get(id)
    }

    /// Load mutable plan by ID.
    pub fn load_mut(&mut self, id: &str) -> Option<&mut Plan> {
        self.plans.get_mut(id)
    }

    /// Delete a plan.
    pub fn delete(&mut self, id: &str) -> Option<Plan> {
        self.plans.remove(id)
    }

    /// List all plans.
    pub fn list(&self) -> Vec<&Plan> {
        self.plans.values().collect()
    }

    /// Get plan count.
    pub fn count(&self) -> usize {
        self.plans.len()
    }

    /// Save to file.
    pub fn persist(&self) -> std::io::Result<()> {
        if let Some(ref path) = self.path {
            let json = serde_json::to_string_pretty(&self.plans)?;
            std::fs::write(path, json)?;
        }
        Ok(())
    }

    /// Load from file.
    pub fn restore(&mut self) -> std::io::Result<()> {
        if let Some(ref path) = self.path {
            if path.exists() {
                let json = std::fs::read_to_string(path)?;
                self.plans = serde_json::from_str(&json)?;
            }
        }
        Ok(())
    }
}

// =============================================================================
// READ-ONLY TOOLS
// =============================================================================

/// Read-only tools allowed in plan mode.
pub const READ_ONLY_TOOLS: &[&str] = &[
    "read_file",
    "list_directory",
    "search_codebase",
    "search_files",
    "grep_search",
    "find_files",
    "web_search",
    "get_file_content",
    "list_files",
    "read_document",
    "search_web",
    "fetch_url",
    "get_context",
];

/// Restricted tools blocked in plan mode.
pub const RESTRICTED_TOOLS: &[&str] = &[
    "write_file",
    "create_file",
    "delete_file",
    "execute_command",
    "run_command",
    "shell_command",
    "modify_file",
    "edit_file",
    "remove_file",
    "move_file",
    "copy_file",
    "mkdir",
    "rmdir",
    "git_commit",
    "git_push",
    "npm_install",
    "pip_install",
];

/// Research tools safe for planning.
pub const RESEARCH_TOOLS: &[&str] = &[
    "web_search",
    "search_web",
    "duckduckgo_search",
    "tavily_search",
    "brave_search",
    "google_search",
    "read_url",
    "fetch_url",
    "read_file",
    "list_directory",
    "search_codebase",
    "grep_search",
    "find_files",
];

/// Check if a tool is read-only.
pub fn is_read_only_tool(name: &str) -> bool {
    READ_ONLY_TOOLS.contains(&name)
}

/// Check if a tool is restricted.
pub fn is_restricted_tool(name: &str) -> bool {
    RESTRICTED_TOOLS.contains(&name)
}

/// Check if a tool is a research tool.
pub fn is_research_tool(name: &str) -> bool {
    RESEARCH_TOOLS.contains(&name)
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_plan_step_new() {
        let step = PlanStep::new("Test step");
        assert_eq!(step.description, "Test step");
        assert_eq!(step.status, StepStatus::Pending);
    }

    #[test]
    fn test_plan_step_lifecycle() {
        let mut step = PlanStep::new("Test step");
        
        step.start();
        assert_eq!(step.status, StepStatus::InProgress);
        
        step.complete(Some("Done".to_string()));
        assert_eq!(step.status, StepStatus::Completed);
        assert_eq!(step.output, Some("Done".to_string()));
    }

    #[test]
    fn test_plan_step_fail() {
        let mut step = PlanStep::new("Test step");
        step.fail("Something went wrong");
        assert_eq!(step.status, StepStatus::Failed);
        assert!(step.error.is_some());
    }

    #[test]
    fn test_plan_new() {
        let plan = Plan::new("Test plan");
        assert_eq!(plan.name, "Test plan");
        assert!(plan.steps.is_empty());
    }

    #[test]
    fn test_plan_add_steps() {
        let mut plan = Plan::new("Test plan");
        plan.add_step(PlanStep::new("Step 1"));
        plan.add_step(PlanStep::new("Step 2"));
        
        assert_eq!(plan.step_count(), 2);
    }

    #[test]
    fn test_plan_progress() {
        let mut plan = Plan::new("Test plan");
        plan.add_step(PlanStep::new("Step 1"));
        plan.add_step(PlanStep::new("Step 2"));
        
        assert!((plan.progress() - 0.0).abs() < 0.001);
        
        if let Some(step) = plan.steps.get_mut(0) {
            step.complete(None);
        }
        
        assert!((plan.progress() - 50.0).abs() < 0.001);
    }

    #[test]
    fn test_todo_item_new() {
        let item = TodoItem::new("Test item");
        assert_eq!(item.content, "Test item");
        assert_eq!(item.priority, TodoPriority::Medium);
    }

    #[test]
    fn test_todo_item_priority() {
        let item = TodoItem::new("Test item").priority(TodoPriority::High);
        assert_eq!(item.priority, TodoPriority::High);
    }

    #[test]
    fn test_todo_list_new() {
        let list = TodoList::new("My List");
        assert_eq!(list.name, "My List");
        assert!(list.is_empty());
    }

    #[test]
    fn test_todo_list_add() {
        let mut list = TodoList::new("My List");
        list.add(TodoItem::new("Item 1"));
        list.add(TodoItem::new("Item 2"));
        
        assert_eq!(list.len(), 2);
    }

    #[test]
    fn test_todo_list_progress() {
        let mut list = TodoList::new("My List");
        list.add(TodoItem::new("Item 1"));
        list.add(TodoItem::new("Item 2"));
        
        assert!((list.progress() - 0.0).abs() < 0.001);
        
        if let Some(item) = list.items.get_mut(0) {
            item.complete();
        }
        
        assert!((list.progress() - 50.0).abs() < 0.001);
    }

    #[test]
    fn test_plan_storage() {
        let mut storage = PlanStorage::new();
        let plan = Plan::new("Test plan");
        let id = plan.id.clone();
        
        storage.save(plan);
        assert_eq!(storage.count(), 1);
        
        let loaded = storage.load(&id);
        assert!(loaded.is_some());
        assert_eq!(loaded.unwrap().name, "Test plan");
    }

    #[test]
    fn test_is_read_only_tool() {
        assert!(is_read_only_tool("read_file"));
        assert!(!is_read_only_tool("write_file"));
    }

    #[test]
    fn test_is_restricted_tool() {
        assert!(is_restricted_tool("write_file"));
        assert!(!is_restricted_tool("read_file"));
    }
}
