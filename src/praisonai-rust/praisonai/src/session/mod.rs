//! Session persistence module for PraisonAI Rust SDK.
//!
//! Provides automatic session persistence with zero configuration.
//! When a session_id is provided to an Agent, conversation history
//! is automatically persisted to disk and restored on subsequent runs.
//!
//! # Usage
//!
//! ```rust,ignore
//! use praisonai::{Agent, Session};
//!
//! // With session persistence
//! let session = Session::new("my-session-123");
//! let agent = Agent::new()
//!     .session(session)
//!     .build()?;
//!
//! agent.chat("Hello").await?;
//!
//! // Later, new process - history is restored
//! let session = Session::load("my-session-123")?;
//! let agent = Agent::new()
//!     .session(session)
//!     .build()?;
//!
//! agent.chat("What did I say before?").await?; // Remembers!
//! ```

use crate::error::{Error, Result};
use crate::llm::Message;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, RwLock};
use std::time::{SystemTime, UNIX_EPOCH};

/// Default session directory
fn default_session_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".praisonai")
        .join("sessions")
}

/// Default maximum messages per session
const DEFAULT_MAX_MESSAGES: usize = 100;

/// A single message in a session
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionMessage {
    /// Message role: "user", "assistant", "system"
    pub role: String,
    /// Message content
    pub content: String,
    /// Unix timestamp
    pub timestamp: f64,
    /// Optional metadata
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

impl SessionMessage {
    /// Create a new session message
    pub fn new(role: impl Into<String>, content: impl Into<String>) -> Self {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();

        Self {
            role: role.into(),
            content: content.into(),
            timestamp: now,
            metadata: HashMap::new(),
        }
    }

    /// Create a user message
    pub fn user(content: impl Into<String>) -> Self {
        Self::new("user", content)
    }

    /// Create an assistant message
    pub fn assistant(content: impl Into<String>) -> Self {
        Self::new("assistant", content)
    }

    /// Create a system message
    pub fn system(content: impl Into<String>) -> Self {
        Self::new("system", content)
    }

    /// Add metadata
    pub fn with_metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }

    /// Convert to LLM Message
    pub fn to_message(&self) -> Message {
        match self.role.as_str() {
            "user" => Message::user(&self.content),
            "assistant" => Message::assistant(&self.content),
            "system" => Message::system(&self.content),
            _ => Message::user(&self.content),
        }
    }
}

/// Complete session data structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionData {
    /// Session ID
    pub session_id: String,
    /// Messages in the session
    #[serde(default)]
    pub messages: Vec<SessionMessage>,
    /// Creation timestamp (ISO 8601)
    pub created_at: String,
    /// Last update timestamp (ISO 8601)
    pub updated_at: String,
    /// Agent name (optional)
    #[serde(default)]
    pub agent_name: Option<String>,
    /// User ID (optional)
    #[serde(default)]
    pub user_id: Option<String>,
    /// Additional metadata
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

impl SessionData {
    /// Create new session data
    pub fn new(session_id: impl Into<String>) -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        Self {
            session_id: session_id.into(),
            messages: Vec::new(),
            created_at: now.clone(),
            updated_at: now,
            agent_name: None,
            user_id: None,
            metadata: HashMap::new(),
        }
    }

    /// Get chat history in LLM-compatible format
    pub fn get_chat_history(&self, max_messages: Option<usize>) -> Vec<Message> {
        let messages = if let Some(max) = max_messages {
            if self.messages.len() > max {
                &self.messages[self.messages.len() - max..]
            } else {
                &self.messages[..]
            }
        } else {
            &self.messages[..]
        };

        messages.iter().map(|m| m.to_message()).collect()
    }

    /// Add a message
    pub fn add_message(&mut self, message: SessionMessage) {
        self.messages.push(message);
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    /// Clear all messages
    pub fn clear(&mut self) {
        self.messages.clear();
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }
}

/// Session store trait for different storage backends
pub trait SessionStore: Send + Sync {
    /// Load session data
    fn load(&self, session_id: &str) -> Result<SessionData>;

    /// Save session data
    fn save(&self, session: &SessionData) -> Result<()>;

    /// Check if session exists
    fn exists(&self, session_id: &str) -> bool;

    /// Delete a session
    fn delete(&self, session_id: &str) -> Result<()>;

    /// List all sessions
    fn list(&self, limit: usize) -> Result<Vec<SessionInfo>>;
}

/// Brief session info for listing
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub session_id: String,
    pub agent_name: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub message_count: usize,
}

/// File-based session store (default)
pub struct FileSessionStore {
    session_dir: PathBuf,
    max_messages: usize,
    cache: Arc<RwLock<HashMap<String, SessionData>>>,
}

impl FileSessionStore {
    /// Create a new file session store
    pub fn new() -> Self {
        let session_dir = default_session_dir();
        fs::create_dir_all(&session_dir).ok();

        Self {
            session_dir,
            max_messages: DEFAULT_MAX_MESSAGES,
            cache: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Create with custom directory
    pub fn with_dir(dir: impl Into<PathBuf>) -> Self {
        let session_dir = dir.into();
        fs::create_dir_all(&session_dir).ok();

        Self {
            session_dir,
            max_messages: DEFAULT_MAX_MESSAGES,
            cache: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Set max messages
    pub fn max_messages(mut self, max: usize) -> Self {
        self.max_messages = max;
        self
    }

    /// Get session file path
    fn get_path(&self, session_id: &str) -> PathBuf {
        let safe_id: String = session_id
            .chars()
            .map(|c| {
                if c.is_alphanumeric() || c == '-' || c == '_' {
                    c
                } else {
                    '_'
                }
            })
            .collect();
        self.session_dir.join(format!("{}.json", safe_id))
    }
}

impl Default for FileSessionStore {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionStore for FileSessionStore {
    fn load(&self, session_id: &str) -> Result<SessionData> {
        // Check cache first
        if let Ok(cache) = self.cache.read() {
            if let Some(session) = cache.get(session_id) {
                return Ok(session.clone());
            }
        }

        let path = self.get_path(session_id);

        if !path.exists() {
            let session = SessionData::new(session_id);
            if let Ok(mut cache) = self.cache.write() {
                cache.insert(session_id.to_string(), session.clone());
            }
            return Ok(session);
        }

        let content = fs::read_to_string(&path)
            .map_err(|e| Error::io(format!("Failed to read session file: {}", e)))?;

        let session: SessionData = serde_json::from_str(&content)
            .map_err(|e| Error::config(format!("Failed to parse session file: {}", e)))?;

        if let Ok(mut cache) = self.cache.write() {
            cache.insert(session_id.to_string(), session.clone());
        }

        Ok(session)
    }

    fn save(&self, session: &SessionData) -> Result<()> {
        let path = self.get_path(&session.session_id);

        // Ensure directory exists
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| Error::io(format!("Failed to create session directory: {}", e)))?;
        }

        // Trim messages if over limit
        let mut session = session.clone();
        if session.messages.len() > self.max_messages {
            session.messages =
                session.messages[session.messages.len() - self.max_messages..].to_vec();
        }

        let content = serde_json::to_string_pretty(&session)
            .map_err(|e| Error::config(format!("Failed to serialize session: {}", e)))?;

        fs::write(&path, content)
            .map_err(|e| Error::io(format!("Failed to write session file: {}", e)))?;

        // Update cache
        if let Ok(mut cache) = self.cache.write() {
            cache.insert(session.session_id.clone(), session);
        }

        Ok(())
    }

    fn exists(&self, session_id: &str) -> bool {
        self.get_path(session_id).exists()
    }

    fn delete(&self, session_id: &str) -> Result<()> {
        let path = self.get_path(session_id);

        if let Ok(mut cache) = self.cache.write() {
            cache.remove(session_id);
        }

        if path.exists() {
            fs::remove_file(&path)
                .map_err(|e| Error::io(format!("Failed to delete session file: {}", e)))?;
        }

        Ok(())
    }

    fn list(&self, limit: usize) -> Result<Vec<SessionInfo>> {
        let mut sessions = Vec::new();

        let entries = fs::read_dir(&self.session_dir)
            .map_err(|e| Error::io(format!("Failed to read session directory: {}", e)))?;

        for entry in entries.flatten() {
            let path: std::path::PathBuf = entry.path();
            if path.extension().is_some_and(|ext| ext == "json") {
                if let Ok(content) = fs::read_to_string(&path) {
                    if let Ok(data) = serde_json::from_str::<SessionData>(&content) {
                        sessions.push(SessionInfo {
                            session_id: data.session_id,
                            agent_name: data.agent_name,
                            created_at: data.created_at,
                            updated_at: data.updated_at,
                            message_count: data.messages.len(),
                        });
                    }
                }
            }
        }

        // Sort by updated_at descending
        sessions.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
        sessions.truncate(limit);

        Ok(sessions)
    }
}

/// In-memory session store (for testing)
pub struct InMemorySessionStore {
    sessions: Arc<RwLock<HashMap<String, SessionData>>>,
}

impl InMemorySessionStore {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
        }
    }
}

impl Default for InMemorySessionStore {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionStore for InMemorySessionStore {
    fn load(&self, session_id: &str) -> Result<SessionData> {
        let sessions = self.sessions.read().unwrap();
        Ok(sessions
            .get(session_id)
            .cloned()
            .unwrap_or_else(|| SessionData::new(session_id)))
    }

    fn save(&self, session: &SessionData) -> Result<()> {
        let mut sessions = self.sessions.write().unwrap();
        sessions.insert(session.session_id.clone(), session.clone());
        Ok(())
    }

    fn exists(&self, session_id: &str) -> bool {
        self.sessions.read().unwrap().contains_key(session_id)
    }

    fn delete(&self, session_id: &str) -> Result<()> {
        self.sessions.write().unwrap().remove(session_id);
        Ok(())
    }

    fn list(&self, limit: usize) -> Result<Vec<SessionInfo>> {
        let sessions = self.sessions.read().unwrap();
        let mut infos: Vec<_> = sessions
            .values()
            .map(|s| SessionInfo {
                session_id: s.session_id.clone(),
                agent_name: s.agent_name.clone(),
                created_at: s.created_at.clone(),
                updated_at: s.updated_at.clone(),
                message_count: s.messages.len(),
            })
            .collect();

        infos.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
        infos.truncate(limit);
        Ok(infos)
    }
}

/// Session manager - main API for session persistence
pub struct Session {
    session_id: String,
    data: SessionData,
    store: Arc<dyn SessionStore>,
}

impl Session {
    /// Create a new session with default file store
    pub fn new(session_id: impl Into<String>) -> Self {
        let session_id = session_id.into();
        let store = Arc::new(FileSessionStore::new());
        let data = store
            .load(&session_id)
            .unwrap_or_else(|_| SessionData::new(&session_id));

        Self {
            session_id,
            data,
            store,
        }
    }

    /// Create with custom store
    pub fn with_store(session_id: impl Into<String>, store: Arc<dyn SessionStore>) -> Self {
        let session_id = session_id.into();
        let data = store
            .load(&session_id)
            .unwrap_or_else(|_| SessionData::new(&session_id));

        Self {
            session_id,
            data,
            store,
        }
    }

    /// Load an existing session
    pub fn load(session_id: impl Into<String>) -> Result<Self> {
        let session_id = session_id.into();
        let store = Arc::new(FileSessionStore::new());
        let data = store.load(&session_id)?;

        Ok(Self {
            session_id,
            data,
            store,
        })
    }

    /// Get session ID
    pub fn id(&self) -> &str {
        &self.session_id
    }

    /// Add a user message
    pub fn add_user_message(&mut self, content: impl Into<String>) -> Result<()> {
        self.data.add_message(SessionMessage::user(content));
        self.store.save(&self.data)
    }

    /// Add an assistant message
    pub fn add_assistant_message(&mut self, content: impl Into<String>) -> Result<()> {
        self.data.add_message(SessionMessage::assistant(content));
        self.store.save(&self.data)
    }

    /// Add a message with role
    pub fn add_message(&mut self, role: &str, content: impl Into<String>) -> Result<()> {
        self.data.add_message(SessionMessage::new(role, content));
        self.store.save(&self.data)
    }

    /// Get chat history as LLM messages
    pub fn get_history(&self, max_messages: Option<usize>) -> Vec<Message> {
        self.data.get_chat_history(max_messages)
    }

    /// Get all messages
    pub fn messages(&self) -> &[SessionMessage] {
        &self.data.messages
    }

    /// Get message count
    pub fn message_count(&self) -> usize {
        self.data.messages.len()
    }

    /// Set agent name
    pub fn set_agent_name(&mut self, name: impl Into<String>) -> Result<()> {
        self.data.agent_name = Some(name.into());
        self.store.save(&self.data)
    }

    /// Set user ID
    pub fn set_user_id(&mut self, user_id: impl Into<String>) -> Result<()> {
        self.data.user_id = Some(user_id.into());
        self.store.save(&self.data)
    }

    /// Clear all messages
    pub fn clear(&mut self) -> Result<()> {
        self.data.clear();
        self.store.save(&self.data)
    }

    /// Delete the session
    pub fn delete(self) -> Result<()> {
        self.store.delete(&self.session_id)
    }

    /// Check if session exists on disk
    pub fn exists(&self) -> bool {
        self.store.exists(&self.session_id)
    }

    /// Save current state
    pub fn save(&self) -> Result<()> {
        self.store.save(&self.data)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_message_creation() {
        let msg = SessionMessage::user("Hello");
        assert_eq!(msg.role, "user");
        assert_eq!(msg.content, "Hello");
        assert!(msg.timestamp > 0.0);
    }

    #[test]
    fn test_session_data() {
        let mut data = SessionData::new("test-session");
        assert_eq!(data.session_id, "test-session");
        assert!(data.messages.is_empty());

        data.add_message(SessionMessage::user("Hello"));
        data.add_message(SessionMessage::assistant("Hi there!"));

        assert_eq!(data.messages.len(), 2);

        let history = data.get_chat_history(None);
        assert_eq!(history.len(), 2);
    }

    #[test]
    fn test_in_memory_store() {
        let store = InMemorySessionStore::new();

        let mut session = SessionData::new("test");
        session.add_message(SessionMessage::user("Hello"));

        store.save(&session).unwrap();
        assert!(store.exists("test"));

        let loaded = store.load("test").unwrap();
        assert_eq!(loaded.messages.len(), 1);

        store.delete("test").unwrap();
        assert!(!store.exists("test"));
    }

    #[test]
    fn test_session_api() {
        let store = Arc::new(InMemorySessionStore::new());
        let mut session = Session::with_store("test-api", store);

        session.add_user_message("Hello").unwrap();
        session.add_assistant_message("Hi!").unwrap();

        assert_eq!(session.message_count(), 2);

        let history = session.get_history(None);
        assert_eq!(history.len(), 2);

        session.clear().unwrap();
        assert_eq!(session.message_count(), 0);
    }

    #[test]
    fn test_session_history_limit() {
        let mut data = SessionData::new("test");
        for i in 0..10 {
            data.add_message(SessionMessage::user(format!("Message {}", i)));
        }

        let history = data.get_chat_history(Some(5));
        assert_eq!(history.len(), 5);
    }
}
