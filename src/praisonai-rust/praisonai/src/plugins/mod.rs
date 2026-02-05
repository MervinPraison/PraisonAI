//! Plugin Module for PraisonAI Agents.
//!
//! Provides dynamic plugin loading and hook-based extension system.
//!
//! # Features
//!
//! - Dynamic plugin discovery and loading
//! - Hook-based extension points
//! - Protocol-driven plugin interfaces
//! - Plugin SDK for easy plugin development
//!
//! # Example
//!
//! ```ignore
//! use praisonai::{PluginManager, Plugin, PluginHook};
//!
//! let mut manager = PluginManager::new();
//! manager.register(MyPlugin::new());
//! manager.enable("my_plugin");
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use crate::error::Result;

// =============================================================================
// PLUGIN HOOK
// =============================================================================

/// Hook points for plugin execution.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PluginHook {
    /// Before agent starts processing
    BeforeAgent,
    /// After agent completes processing
    AfterAgent,
    /// Before tool execution
    BeforeTool,
    /// After tool execution
    AfterTool,
    /// Before LLM call
    BeforeLlm,
    /// After LLM call
    AfterLlm,
    /// Before memory operation
    BeforeMemory,
    /// After memory operation
    AfterMemory,
    /// On error
    OnError,
    /// On workflow start
    OnWorkflowStart,
    /// On workflow end
    OnWorkflowEnd,
    /// On handoff
    OnHandoff,
}

impl PluginHook {
    /// Get all hook types
    pub fn all() -> Vec<PluginHook> {
        vec![
            PluginHook::BeforeAgent,
            PluginHook::AfterAgent,
            PluginHook::BeforeTool,
            PluginHook::AfterTool,
            PluginHook::BeforeLlm,
            PluginHook::AfterLlm,
            PluginHook::BeforeMemory,
            PluginHook::AfterMemory,
            PluginHook::OnError,
            PluginHook::OnWorkflowStart,
            PluginHook::OnWorkflowEnd,
            PluginHook::OnHandoff,
        ]
    }
}

// =============================================================================
// PLUGIN TYPE
// =============================================================================

/// Type of plugin.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PluginType {
    /// Hook-based plugin
    #[default]
    Hook,
    /// Tool plugin
    Tool,
    /// LLM plugin
    Llm,
    /// Agent plugin
    Agent,
}

// =============================================================================
// PLUGIN INFO
// =============================================================================

/// Information about a plugin.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginInfo {
    /// Plugin name
    pub name: String,
    /// Plugin version
    pub version: String,
    /// Plugin description
    pub description: String,
    /// Plugin type
    pub plugin_type: PluginType,
    /// Hooks this plugin listens to
    pub hooks: Vec<PluginHook>,
    /// Whether the plugin is enabled
    pub enabled: bool,
}

impl PluginInfo {
    /// Create new plugin info
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            version: "1.0.0".to_string(),
            description: String::new(),
            plugin_type: PluginType::Hook,
            hooks: Vec::new(),
            enabled: false,
        }
    }

    /// Set version
    pub fn version(mut self, version: impl Into<String>) -> Self {
        self.version = version.into();
        self
    }

    /// Set description
    pub fn description(mut self, description: impl Into<String>) -> Self {
        self.description = description.into();
        self
    }

    /// Set plugin type
    pub fn plugin_type(mut self, plugin_type: PluginType) -> Self {
        self.plugin_type = plugin_type;
        self
    }

    /// Add hook
    pub fn hook(mut self, hook: PluginHook) -> Self {
        self.hooks.push(hook);
        self
    }

    /// Add multiple hooks
    pub fn hooks(mut self, hooks: Vec<PluginHook>) -> Self {
        self.hooks.extend(hooks);
        self
    }
}

// =============================================================================
// PLUGIN TRAIT
// =============================================================================

/// Trait for implementing plugins.
pub trait Plugin: Send + Sync {
    /// Get plugin info
    fn info(&self) -> PluginInfo;

    /// Get plugin name
    fn name(&self) -> &str {
        // This is a workaround since we can't return &str from info()
        // Implementations should override this
        "unknown"
    }

    /// Initialize the plugin
    fn init(&mut self) -> Result<()> {
        Ok(())
    }

    /// Shutdown the plugin
    fn shutdown(&mut self) -> Result<()> {
        Ok(())
    }

    /// Execute hook
    fn execute(
        &self,
        hook: PluginHook,
        data: serde_json::Value,
    ) -> Result<Option<serde_json::Value>> {
        // Default: pass through
        Ok(Some(data))
    }

    /// Check if plugin handles a specific hook
    fn handles(&self, hook: PluginHook) -> bool {
        self.info().hooks.contains(&hook)
    }
}

// =============================================================================
// FUNCTION PLUGIN
// =============================================================================

/// A simple function-based plugin.
pub struct FunctionPlugin {
    info: PluginInfo,
    handler: Box<dyn Fn(PluginHook, serde_json::Value) -> Result<Option<serde_json::Value>> + Send + Sync>,
}

impl FunctionPlugin {
    /// Create a new function plugin
    pub fn new<F>(name: impl Into<String>, hooks: Vec<PluginHook>, handler: F) -> Self
    where
        F: Fn(PluginHook, serde_json::Value) -> Result<Option<serde_json::Value>> + Send + Sync + 'static,
    {
        Self {
            info: PluginInfo::new(name).hooks(hooks),
            handler: Box::new(handler),
        }
    }
}

impl Plugin for FunctionPlugin {
    fn info(&self) -> PluginInfo {
        self.info.clone()
    }

    fn name(&self) -> &str {
        &self.info.name
    }

    fn execute(
        &self,
        hook: PluginHook,
        data: serde_json::Value,
    ) -> Result<Option<serde_json::Value>> {
        (self.handler)(hook, data)
    }

    fn handles(&self, hook: PluginHook) -> bool {
        self.info.hooks.contains(&hook)
    }
}

// =============================================================================
// PLUGIN MANAGER
// =============================================================================

/// Manages plugin registration and execution.
pub struct PluginManager {
    /// Registered plugins
    plugins: HashMap<String, Arc<RwLock<Box<dyn Plugin>>>>,
    /// Enabled plugins
    enabled: HashMap<String, bool>,
    /// Hook to plugin mapping
    hook_map: HashMap<PluginHook, Vec<String>>,
}

impl Default for PluginManager {
    fn default() -> Self {
        Self::new()
    }
}

impl PluginManager {
    /// Create a new plugin manager
    pub fn new() -> Self {
        Self {
            plugins: HashMap::new(),
            enabled: HashMap::new(),
            hook_map: HashMap::new(),
        }
    }

    /// Register a plugin
    pub fn register(&mut self, plugin: impl Plugin + 'static) {
        let info = plugin.info();
        let name = info.name.clone();

        // Add to hook map
        for hook in &info.hooks {
            self.hook_map
                .entry(*hook)
                .or_default()
                .push(name.clone());
        }

        self.plugins
            .insert(name.clone(), Arc::new(RwLock::new(Box::new(plugin))));
        self.enabled.insert(name, false);
    }

    /// Enable a plugin
    pub fn enable(&mut self, name: &str) -> bool {
        if let Some(enabled) = self.enabled.get_mut(name) {
            *enabled = true;
            // Initialize plugin
            if let Some(plugin) = self.plugins.get(name) {
                if let Ok(mut p) = plugin.write() {
                    let _ = p.init();
                }
            }
            true
        } else {
            false
        }
    }

    /// Disable a plugin
    pub fn disable(&mut self, name: &str) -> bool {
        if let Some(enabled) = self.enabled.get_mut(name) {
            *enabled = false;
            // Shutdown plugin
            if let Some(plugin) = self.plugins.get(name) {
                if let Ok(mut p) = plugin.write() {
                    let _ = p.shutdown();
                }
            }
            true
        } else {
            false
        }
    }

    /// Check if a plugin is enabled
    pub fn is_enabled(&self, name: &str) -> bool {
        self.enabled.get(name).copied().unwrap_or(false)
    }

    /// List all plugins
    pub fn list_plugins(&self) -> Vec<PluginInfo> {
        self.plugins
            .iter()
            .filter_map(|(name, plugin)| {
                plugin.read().ok().map(|p| {
                    let mut info = p.info();
                    info.enabled = self.is_enabled(name);
                    info
                })
            })
            .collect()
    }

    /// Get plugin by name
    pub fn get(&self, name: &str) -> Option<Arc<RwLock<Box<dyn Plugin>>>> {
        self.plugins.get(name).cloned()
    }

    /// Execute hooks for a specific hook type
    pub fn execute_hook(
        &self,
        hook: PluginHook,
        data: serde_json::Value,
    ) -> Result<serde_json::Value> {
        let mut current_data = data;

        if let Some(plugin_names) = self.hook_map.get(&hook) {
            for name in plugin_names {
                if !self.is_enabled(name) {
                    continue;
                }

                if let Some(plugin) = self.plugins.get(name) {
                    if let Ok(p) = plugin.read() {
                        if p.handles(hook) {
                            if let Ok(Some(new_data)) = p.execute(hook, current_data.clone()) {
                                current_data = new_data;
                            }
                        }
                    }
                }
            }
        }

        Ok(current_data)
    }

    /// Get plugins that handle a specific hook
    pub fn get_hook_plugins(&self, hook: PluginHook) -> Vec<String> {
        self.hook_map
            .get(&hook)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .filter(|name| self.is_enabled(name))
            .collect()
    }

    /// Count registered plugins
    pub fn len(&self) -> usize {
        self.plugins.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.plugins.is_empty()
    }

    /// Count enabled plugins
    pub fn enabled_count(&self) -> usize {
        self.enabled.values().filter(|&&e| e).count()
    }
}

// =============================================================================
// GLOBAL PLUGIN MANAGER
// =============================================================================

use std::sync::OnceLock;

static GLOBAL_PLUGIN_MANAGER: OnceLock<RwLock<PluginManager>> = OnceLock::new();

/// Get the global plugin manager
pub fn get_plugin_manager() -> &'static RwLock<PluginManager> {
    GLOBAL_PLUGIN_MANAGER.get_or_init(|| RwLock::new(PluginManager::new()))
}

/// Enable plugins globally
pub fn enable_plugins(plugins: Option<Vec<&str>>) {
    if let Ok(mut manager) = get_plugin_manager().write() {
        match plugins {
            Some(names) => {
                for name in names {
                    manager.enable(name);
                }
            }
            None => {
                // Enable all
                let names: Vec<_> = manager.plugins.keys().cloned().collect();
                for name in names {
                    manager.enable(&name);
                }
            }
        }
    }
}

/// Disable plugins globally
pub fn disable_plugins(plugins: Option<Vec<&str>>) {
    if let Ok(mut manager) = get_plugin_manager().write() {
        match plugins {
            Some(names) => {
                for name in names {
                    manager.disable(name);
                }
            }
            None => {
                // Disable all
                let names: Vec<_> = manager.plugins.keys().cloned().collect();
                for name in names {
                    manager.disable(&name);
                }
            }
        }
    }
}

/// List all plugins
pub fn list_plugins() -> Vec<PluginInfo> {
    get_plugin_manager()
        .read()
        .map(|m| m.list_plugins())
        .unwrap_or_default()
}

/// Check if a plugin is enabled
pub fn is_plugin_enabled(name: &str) -> bool {
    get_plugin_manager()
        .read()
        .map(|m| m.is_enabled(name))
        .unwrap_or(false)
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    struct TestPlugin {
        name: String,
        hooks: Vec<PluginHook>,
    }

    impl TestPlugin {
        fn new(name: &str, hooks: Vec<PluginHook>) -> Self {
            Self {
                name: name.to_string(),
                hooks,
            }
        }
    }

    impl Plugin for TestPlugin {
        fn info(&self) -> PluginInfo {
            PluginInfo::new(&self.name).hooks(self.hooks.clone())
        }

        fn name(&self) -> &str {
            &self.name
        }

        fn execute(
            &self,
            _hook: PluginHook,
            mut data: serde_json::Value,
        ) -> Result<Option<serde_json::Value>> {
            // Add a marker to show plugin was executed
            if let Some(obj) = data.as_object_mut() {
                obj.insert(
                    format!("{}_executed", self.name),
                    serde_json::Value::Bool(true),
                );
            }
            Ok(Some(data))
        }
    }

    #[test]
    fn test_plugin_info() {
        let info = PluginInfo::new("test_plugin")
            .version("2.0.0")
            .description("A test plugin")
            .plugin_type(PluginType::Hook)
            .hook(PluginHook::BeforeAgent)
            .hook(PluginHook::AfterAgent);

        assert_eq!(info.name, "test_plugin");
        assert_eq!(info.version, "2.0.0");
        assert_eq!(info.hooks.len(), 2);
    }

    #[test]
    fn test_plugin_manager_register() {
        let mut manager = PluginManager::new();
        let plugin = TestPlugin::new("test", vec![PluginHook::BeforeAgent]);

        manager.register(plugin);
        assert_eq!(manager.len(), 1);
        assert!(!manager.is_enabled("test"));
    }

    #[test]
    fn test_plugin_manager_enable_disable() {
        let mut manager = PluginManager::new();
        let plugin = TestPlugin::new("test", vec![PluginHook::BeforeAgent]);

        manager.register(plugin);
        assert!(!manager.is_enabled("test"));

        manager.enable("test");
        assert!(manager.is_enabled("test"));

        manager.disable("test");
        assert!(!manager.is_enabled("test"));
    }

    #[test]
    fn test_plugin_manager_execute_hook() {
        let mut manager = PluginManager::new();
        let plugin = TestPlugin::new("test", vec![PluginHook::BeforeAgent]);

        manager.register(plugin);
        manager.enable("test");

        let data = serde_json::json!({"input": "hello"});
        let result = manager.execute_hook(PluginHook::BeforeAgent, data).unwrap();

        assert!(result.get("test_executed").is_some());
        assert_eq!(result.get("test_executed").unwrap(), &serde_json::Value::Bool(true));
    }

    #[test]
    fn test_plugin_manager_disabled_not_executed() {
        let mut manager = PluginManager::new();
        let plugin = TestPlugin::new("test", vec![PluginHook::BeforeAgent]);

        manager.register(plugin);
        // Don't enable

        let data = serde_json::json!({"input": "hello"});
        let result = manager.execute_hook(PluginHook::BeforeAgent, data).unwrap();

        // Plugin should not have been executed
        assert!(result.get("test_executed").is_none());
    }

    #[test]
    fn test_function_plugin() {
        let plugin = FunctionPlugin::new(
            "func_plugin",
            vec![PluginHook::BeforeTool],
            |_hook, mut data| {
                if let Some(obj) = data.as_object_mut() {
                    obj.insert("modified".to_string(), serde_json::Value::Bool(true));
                }
                Ok(Some(data))
            },
        );

        assert_eq!(plugin.name(), "func_plugin");
        assert!(plugin.handles(PluginHook::BeforeTool));
        assert!(!plugin.handles(PluginHook::AfterTool));
    }

    #[test]
    fn test_list_plugins() {
        let mut manager = PluginManager::new();
        manager.register(TestPlugin::new("plugin_a", vec![PluginHook::BeforeAgent]));
        manager.register(TestPlugin::new("plugin_b", vec![PluginHook::AfterAgent]));
        manager.enable("plugin_a");

        let plugins = manager.list_plugins();
        assert_eq!(plugins.len(), 2);

        let plugin_a = plugins.iter().find(|p| p.name == "plugin_a").unwrap();
        assert!(plugin_a.enabled);

        let plugin_b = plugins.iter().find(|p| p.name == "plugin_b").unwrap();
        assert!(!plugin_b.enabled);
    }

    #[test]
    fn test_get_hook_plugins() {
        let mut manager = PluginManager::new();
        manager.register(TestPlugin::new("plugin_a", vec![PluginHook::BeforeAgent]));
        manager.register(TestPlugin::new("plugin_b", vec![PluginHook::BeforeAgent, PluginHook::AfterAgent]));
        manager.enable("plugin_a");
        manager.enable("plugin_b");

        let before_plugins = manager.get_hook_plugins(PluginHook::BeforeAgent);
        assert_eq!(before_plugins.len(), 2);

        let after_plugins = manager.get_hook_plugins(PluginHook::AfterAgent);
        assert_eq!(after_plugins.len(), 1);
    }

    #[test]
    fn test_plugin_hook_all() {
        let all_hooks = PluginHook::all();
        assert!(all_hooks.len() >= 10);
        assert!(all_hooks.contains(&PluginHook::BeforeAgent));
        assert!(all_hooks.contains(&PluginHook::OnError));
    }
}
