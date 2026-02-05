//! Sandbox Module for PraisonAI Rust SDK
//!
//! Defines protocols and types for sandbox implementations that enable
//! safe code execution in isolated environments.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::sandbox::{ResourceLimits, SandboxResult, SandboxStatus};
//!
//! let limits = ResourceLimits::minimal();
//! println!("Memory limit: {} MB", limits.memory_mb);
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

use crate::error::Result;

/// Status of a sandbox execution.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SandboxStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Timeout,
    Killed,
}

impl Default for SandboxStatus {
    fn default() -> Self {
        Self::Pending
    }
}

impl std::fmt::Display for SandboxStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Self::Pending => "pending",
            Self::Running => "running",
            Self::Completed => "completed",
            Self::Failed => "failed",
            Self::Timeout => "timeout",
            Self::Killed => "killed",
        };
        write!(f, "{}", s)
    }
}

/// Resource limits for sandbox execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceLimits {
    /// Maximum memory in megabytes (0 = unlimited)
    pub memory_mb: u32,
    /// Maximum CPU percentage (0 = unlimited)
    pub cpu_percent: u32,
    /// Maximum execution time in seconds
    pub timeout_seconds: u32,
    /// Maximum number of processes
    pub max_processes: u32,
    /// Maximum number of open files
    pub max_open_files: u32,
    /// Whether network access is allowed
    pub network_enabled: bool,
    /// Maximum disk write in megabytes (0 = unlimited)
    pub disk_write_mb: u32,
}

impl Default for ResourceLimits {
    fn default() -> Self {
        Self {
            memory_mb: 512,
            cpu_percent: 100,
            timeout_seconds: 60,
            max_processes: 10,
            max_open_files: 100,
            network_enabled: false,
            disk_write_mb: 100,
        }
    }
}

impl ResourceLimits {
    /// Create default resource limits.
    pub fn new() -> Self {
        Self::default()
    }

    /// Create minimal resource limits for untrusted code.
    pub fn minimal() -> Self {
        Self {
            memory_mb: 128,
            cpu_percent: 50,
            timeout_seconds: 30,
            max_processes: 5,
            max_open_files: 50,
            network_enabled: false,
            disk_write_mb: 10,
        }
    }

    /// Create standard resource limits.
    pub fn standard() -> Self {
        Self::default()
    }

    /// Create generous resource limits for trusted code.
    pub fn generous() -> Self {
        Self {
            memory_mb: 2048,
            cpu_percent: 100,
            timeout_seconds: 300,
            max_processes: 50,
            max_open_files: 500,
            network_enabled: true,
            disk_write_mb: 1000,
        }
    }

    /// Set memory limit.
    pub fn memory_mb(mut self, mb: u32) -> Self {
        self.memory_mb = mb;
        self
    }

    /// Set CPU limit.
    pub fn cpu_percent(mut self, percent: u32) -> Self {
        self.cpu_percent = percent;
        self
    }

    /// Set timeout.
    pub fn timeout_seconds(mut self, seconds: u32) -> Self {
        self.timeout_seconds = seconds;
        self
    }

    /// Set max processes.
    pub fn max_processes(mut self, max: u32) -> Self {
        self.max_processes = max;
        self
    }

    /// Set max open files.
    pub fn max_open_files(mut self, max: u32) -> Self {
        self.max_open_files = max;
        self
    }

    /// Enable/disable network access.
    pub fn network_enabled(mut self, enabled: bool) -> Self {
        self.network_enabled = enabled;
        self
    }

    /// Set disk write limit.
    pub fn disk_write_mb(mut self, mb: u32) -> Self {
        self.disk_write_mb = mb;
        self
    }

    /// Convert to dictionary.
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("memory_mb".to_string(), serde_json::json!(self.memory_mb));
        map.insert("cpu_percent".to_string(), serde_json::json!(self.cpu_percent));
        map.insert("timeout_seconds".to_string(), serde_json::json!(self.timeout_seconds));
        map.insert("max_processes".to_string(), serde_json::json!(self.max_processes));
        map.insert("max_open_files".to_string(), serde_json::json!(self.max_open_files));
        map.insert("network_enabled".to_string(), serde_json::json!(self.network_enabled));
        map.insert("disk_write_mb".to_string(), serde_json::json!(self.disk_write_mb));
        map
    }
}

/// Get current timestamp in seconds since UNIX epoch.
fn current_timestamp() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Result of a sandbox execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxResult {
    /// Unique execution identifier
    pub execution_id: String,
    /// Execution status
    pub status: SandboxStatus,
    /// Process exit code (None if not completed)
    pub exit_code: Option<i32>,
    /// Standard output
    pub stdout: String,
    /// Standard error
    pub stderr: String,
    /// Execution duration in seconds
    pub duration_seconds: f64,
    /// Start timestamp
    pub started_at: Option<f64>,
    /// Completion timestamp
    pub completed_at: Option<f64>,
    /// Error message if failed
    pub error: Option<String>,
    /// Additional execution metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl Default for SandboxResult {
    fn default() -> Self {
        Self {
            execution_id: Uuid::new_v4().to_string(),
            status: SandboxStatus::Pending,
            exit_code: None,
            stdout: String::new(),
            stderr: String::new(),
            duration_seconds: 0.0,
            started_at: None,
            completed_at: None,
            error: None,
            metadata: HashMap::new(),
        }
    }
}

impl SandboxResult {
    /// Create a new sandbox result.
    pub fn new() -> Self {
        Self::default()
    }

    /// Check if execution was successful.
    pub fn success(&self) -> bool {
        self.status == SandboxStatus::Completed && self.exit_code == Some(0)
    }

    /// Get combined output (stdout + stderr).
    pub fn output(&self) -> String {
        let mut parts = Vec::new();
        if !self.stdout.is_empty() {
            parts.push(self.stdout.clone());
        }
        if !self.stderr.is_empty() {
            parts.push(format!("[stderr]\n{}", self.stderr));
        }
        parts.join("\n")
    }

    /// Mark as started.
    pub fn start(&mut self) {
        self.status = SandboxStatus::Running;
        self.started_at = Some(current_timestamp());
    }

    /// Mark as completed.
    pub fn complete(&mut self, exit_code: i32, stdout: String, stderr: String) {
        self.status = SandboxStatus::Completed;
        self.exit_code = Some(exit_code);
        self.stdout = stdout;
        self.stderr = stderr;
        self.completed_at = Some(current_timestamp());
        if let Some(started) = self.started_at {
            self.duration_seconds = self.completed_at.unwrap_or(0.0) - started;
        }
    }

    /// Mark as failed.
    pub fn fail(&mut self, error: impl Into<String>) {
        self.status = SandboxStatus::Failed;
        self.error = Some(error.into());
        self.completed_at = Some(current_timestamp());
        if let Some(started) = self.started_at {
            self.duration_seconds = self.completed_at.unwrap_or(0.0) - started;
        }
    }

    /// Mark as timed out.
    pub fn timeout(&mut self) {
        self.status = SandboxStatus::Timeout;
        self.error = Some("Execution timed out".to_string());
        self.completed_at = Some(current_timestamp());
        if let Some(started) = self.started_at {
            self.duration_seconds = self.completed_at.unwrap_or(0.0) - started;
        }
    }

    /// Convert to dictionary.
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("execution_id".to_string(), serde_json::json!(self.execution_id));
        map.insert("status".to_string(), serde_json::json!(self.status.to_string()));
        map.insert("exit_code".to_string(), serde_json::json!(self.exit_code));
        map.insert("stdout".to_string(), serde_json::json!(self.stdout));
        map.insert("stderr".to_string(), serde_json::json!(self.stderr));
        map.insert("duration_seconds".to_string(), serde_json::json!(self.duration_seconds));
        map.insert("started_at".to_string(), serde_json::json!(self.started_at));
        map.insert("completed_at".to_string(), serde_json::json!(self.completed_at));
        map.insert("error".to_string(), serde_json::json!(self.error));
        map.insert("metadata".to_string(), serde_json::json!(self.metadata));
        map
    }
}

/// Configuration for a sandbox.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxConfig {
    /// Sandbox type (docker, subprocess, etc.)
    pub sandbox_type: String,
    /// Docker image to use (if docker type)
    pub image: Option<String>,
    /// Working directory
    pub working_dir: Option<String>,
    /// Environment variables
    pub env: HashMap<String, String>,
    /// Resource limits
    pub limits: ResourceLimits,
    /// Whether to auto-cleanup after execution
    pub auto_cleanup: bool,
}

impl Default for SandboxConfig {
    fn default() -> Self {
        Self {
            sandbox_type: "subprocess".to_string(),
            image: None,
            working_dir: None,
            env: HashMap::new(),
            limits: ResourceLimits::default(),
            auto_cleanup: true,
        }
    }
}

impl SandboxConfig {
    /// Create a new config with defaults.
    pub fn new() -> Self {
        Self::default()
    }

    /// Create a Docker sandbox config.
    pub fn docker(image: impl Into<String>) -> Self {
        Self {
            sandbox_type: "docker".to_string(),
            image: Some(image.into()),
            ..Default::default()
        }
    }

    /// Create a subprocess sandbox config.
    pub fn subprocess() -> Self {
        Self {
            sandbox_type: "subprocess".to_string(),
            ..Default::default()
        }
    }

    /// Set working directory.
    pub fn working_dir(mut self, dir: impl Into<String>) -> Self {
        self.working_dir = Some(dir.into());
        self
    }

    /// Add environment variable.
    pub fn env(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.env.insert(key.into(), value.into());
        self
    }

    /// Set resource limits.
    pub fn limits(mut self, limits: ResourceLimits) -> Self {
        self.limits = limits;
        self
    }

    /// Set auto-cleanup.
    pub fn auto_cleanup(mut self, cleanup: bool) -> Self {
        self.auto_cleanup = cleanup;
        self
    }
}

/// Protocol for sandbox implementations.
///
/// Sandboxes provide isolated environments for safe code execution.
/// Implementations can use Docker, subprocess isolation, or other
/// containerization technologies.
#[async_trait]
pub trait SandboxProtocol: Send + Sync {
    /// Whether the sandbox backend is available.
    fn is_available(&self) -> bool;

    /// Type of sandbox (docker, subprocess, etc.).
    fn sandbox_type(&self) -> &str;

    /// Start/initialize the sandbox environment.
    async fn start(&mut self) -> Result<()>;

    /// Stop/cleanup the sandbox environment.
    async fn stop(&mut self) -> Result<()>;

    /// Execute code in the sandbox.
    async fn execute(
        &self,
        code: &str,
        language: &str,
        limits: Option<ResourceLimits>,
        env: Option<HashMap<String, String>>,
        working_dir: Option<String>,
    ) -> Result<SandboxResult>;

    /// Execute a file in the sandbox.
    async fn execute_file(
        &self,
        file_path: &str,
        args: Option<Vec<String>>,
        limits: Option<ResourceLimits>,
        env: Option<HashMap<String, String>>,
    ) -> Result<SandboxResult>;

    /// Run a shell command in the sandbox.
    async fn run_command(
        &self,
        command: &str,
        limits: Option<ResourceLimits>,
        env: Option<HashMap<String, String>>,
        working_dir: Option<String>,
    ) -> Result<SandboxResult>;

    /// Write a file to the sandbox.
    async fn write_file(&self, path: &str, content: &[u8]) -> Result<bool>;

    /// Read a file from the sandbox.
    async fn read_file(&self, path: &str) -> Result<Option<Vec<u8>>>;

    /// List files in a sandbox directory.
    async fn list_files(&self, path: &str) -> Result<Vec<String>>;

    /// Get sandbox status information.
    fn get_status(&self) -> SandboxStatusInfo;

    /// Clean up sandbox resources.
    async fn cleanup(&mut self) -> Result<()>;

    /// Reset sandbox to initial state.
    async fn reset(&mut self) -> Result<()>;
}

/// Sandbox status information.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxStatusInfo {
    /// Whether sandbox is available
    pub available: bool,
    /// Sandbox type
    pub sandbox_type: String,
    /// Whether sandbox is running
    pub running: bool,
    /// Current resource usage
    pub resource_usage: Option<ResourceUsage>,
}

/// Current resource usage.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceUsage {
    /// Memory usage in MB
    pub memory_mb: f64,
    /// CPU usage percentage
    pub cpu_percent: f64,
    /// Disk usage in MB
    pub disk_mb: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sandbox_status() {
        assert_eq!(SandboxStatus::default(), SandboxStatus::Pending);
        assert_eq!(SandboxStatus::Completed.to_string(), "completed");
        assert_eq!(SandboxStatus::Timeout.to_string(), "timeout");
    }

    #[test]
    fn test_resource_limits_default() {
        let limits = ResourceLimits::default();
        assert_eq!(limits.memory_mb, 512);
        assert_eq!(limits.timeout_seconds, 60);
        assert!(!limits.network_enabled);
    }

    #[test]
    fn test_resource_limits_minimal() {
        let limits = ResourceLimits::minimal();
        assert_eq!(limits.memory_mb, 128);
        assert_eq!(limits.cpu_percent, 50);
        assert_eq!(limits.timeout_seconds, 30);
    }

    #[test]
    fn test_resource_limits_generous() {
        let limits = ResourceLimits::generous();
        assert_eq!(limits.memory_mb, 2048);
        assert!(limits.network_enabled);
        assert_eq!(limits.timeout_seconds, 300);
    }

    #[test]
    fn test_resource_limits_builder() {
        let limits = ResourceLimits::new()
            .memory_mb(1024)
            .timeout_seconds(120)
            .network_enabled(true);

        assert_eq!(limits.memory_mb, 1024);
        assert_eq!(limits.timeout_seconds, 120);
        assert!(limits.network_enabled);
    }

    #[test]
    fn test_sandbox_result_new() {
        let result = SandboxResult::new();
        assert_eq!(result.status, SandboxStatus::Pending);
        assert!(!result.execution_id.is_empty());
        assert!(!result.success());
    }

    #[test]
    fn test_sandbox_result_complete() {
        let mut result = SandboxResult::new();
        result.start();
        assert_eq!(result.status, SandboxStatus::Running);

        result.complete(0, "output".to_string(), "".to_string());
        assert_eq!(result.status, SandboxStatus::Completed);
        assert_eq!(result.exit_code, Some(0));
        assert!(result.success());
        assert_eq!(result.stdout, "output");
    }

    #[test]
    fn test_sandbox_result_fail() {
        let mut result = SandboxResult::new();
        result.start();
        result.fail("Something went wrong");

        assert_eq!(result.status, SandboxStatus::Failed);
        assert!(!result.success());
        assert_eq!(result.error, Some("Something went wrong".to_string()));
    }

    #[test]
    fn test_sandbox_result_timeout() {
        let mut result = SandboxResult::new();
        result.start();
        result.timeout();

        assert_eq!(result.status, SandboxStatus::Timeout);
        assert!(!result.success());
    }

    #[test]
    fn test_sandbox_result_output() {
        let mut result = SandboxResult::new();
        result.stdout = "stdout content".to_string();
        result.stderr = "stderr content".to_string();

        let output = result.output();
        assert!(output.contains("stdout content"));
        assert!(output.contains("[stderr]"));
        assert!(output.contains("stderr content"));
    }

    #[test]
    fn test_sandbox_config_default() {
        let config = SandboxConfig::default();
        assert_eq!(config.sandbox_type, "subprocess");
        assert!(config.auto_cleanup);
    }

    #[test]
    fn test_sandbox_config_docker() {
        let config = SandboxConfig::docker("python:3.11-slim");
        assert_eq!(config.sandbox_type, "docker");
        assert_eq!(config.image, Some("python:3.11-slim".to_string()));
    }

    #[test]
    fn test_sandbox_config_builder() {
        let config = SandboxConfig::subprocess()
            .working_dir("/tmp")
            .env("PATH", "/usr/bin")
            .limits(ResourceLimits::minimal())
            .auto_cleanup(false);

        assert_eq!(config.working_dir, Some("/tmp".to_string()));
        assert_eq!(config.env.get("PATH"), Some(&"/usr/bin".to_string()));
        assert_eq!(config.limits.memory_mb, 128);
        assert!(!config.auto_cleanup);
    }
}
