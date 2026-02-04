//! Memory system for PraisonAI
//!
//! This module provides memory abstractions for agents.
//! Memory stores conversation history and can be extended with long-term storage.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

use crate::error::Result;
use crate::llm::Message;
use crate::config::MemoryConfig;

/// Conversation history storage
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ConversationHistory {
    messages: VecDeque<Message>,
    max_messages: usize,
}

impl ConversationHistory {
    /// Create a new conversation history
    pub fn new(max_messages: usize) -> Self {
        Self {
            messages: VecDeque::new(),
            max_messages,
        }
    }
    
    /// Add a message to the history
    pub fn add(&mut self, message: Message) {
        self.messages.push_back(message);
        
        // Trim if over limit (keep system messages)
        while self.messages.len() > self.max_messages {
            // Find first non-system message to remove
            if let Some(idx) = self.messages.iter().position(|m| {
                m.role != crate::llm::Role::System
            }) {
                self.messages.remove(idx);
            } else {
                break;
            }
        }
    }
    
    /// Get all messages
    pub fn messages(&self) -> Vec<Message> {
        self.messages.iter().cloned().collect()
    }
    
    /// Clear the history
    pub fn clear(&mut self) {
        self.messages.clear();
    }
    
    /// Get the number of messages
    pub fn len(&self) -> usize {
        self.messages.len()
    }
    
    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.messages.is_empty()
    }
}

/// Trait for memory adapters
#[async_trait]
pub trait MemoryAdapter: Send + Sync {
    /// Store a message in short-term memory
    async fn store_short_term(&mut self, message: Message) -> Result<()>;
    
    /// Search short-term memory
    async fn search_short_term(&self, query: &str, limit: usize) -> Result<Vec<Message>>;
    
    /// Get all short-term messages
    async fn get_short_term(&self) -> Result<Vec<Message>>;
    
    /// Clear short-term memory
    async fn clear_short_term(&mut self) -> Result<()>;
    
    /// Store in long-term memory (optional)
    async fn store_long_term(&mut self, _text: &str, _metadata: Option<serde_json::Value>) -> Result<()> {
        Ok(()) // Default no-op
    }
    
    /// Search long-term memory (optional)
    async fn search_long_term(&self, _query: &str, _limit: usize) -> Result<Vec<String>> {
        Ok(vec![]) // Default empty
    }
}

/// In-memory adapter (default)
pub struct InMemoryAdapter {
    history: ConversationHistory,
}

impl InMemoryAdapter {
    /// Create a new in-memory adapter
    pub fn new(max_messages: usize) -> Self {
        Self {
            history: ConversationHistory::new(max_messages),
        }
    }
}

impl Default for InMemoryAdapter {
    fn default() -> Self {
        Self::new(100)
    }
}

#[async_trait]
impl MemoryAdapter for InMemoryAdapter {
    async fn store_short_term(&mut self, message: Message) -> Result<()> {
        self.history.add(message);
        Ok(())
    }
    
    async fn search_short_term(&self, query: &str, limit: usize) -> Result<Vec<Message>> {
        // Simple substring search
        let query_lower = query.to_lowercase();
        let results: Vec<_> = self.history.messages()
            .into_iter()
            .filter(|m| m.content.to_lowercase().contains(&query_lower))
            .take(limit)
            .collect();
        Ok(results)
    }
    
    async fn get_short_term(&self) -> Result<Vec<Message>> {
        Ok(self.history.messages())
    }
    
    async fn clear_short_term(&mut self) -> Result<()> {
        self.history.clear();
        Ok(())
    }
}

/// Memory manager for agents
pub struct Memory {
    adapter: Box<dyn MemoryAdapter>,
    config: MemoryConfig,
}

impl Memory {
    /// Create a new memory with the given adapter
    pub fn new(adapter: impl MemoryAdapter + 'static, config: MemoryConfig) -> Self {
        Self {
            adapter: Box::new(adapter),
            config,
        }
    }
    
    /// Create a new in-memory memory
    pub fn in_memory(config: MemoryConfig) -> Self {
        Self::new(InMemoryAdapter::new(config.max_messages), config)
    }
    
    /// Create with default config
    pub fn default_memory() -> Self {
        Self::in_memory(MemoryConfig::default())
    }
    
    /// Store a message
    pub async fn store(&mut self, message: Message) -> Result<()> {
        if self.config.use_short_term {
            self.adapter.store_short_term(message).await?;
        }
        Ok(())
    }
    
    /// Get conversation history
    pub async fn history(&self) -> Result<Vec<Message>> {
        self.adapter.get_short_term().await
    }
    
    /// Search memory
    pub async fn search(&self, query: &str, limit: usize) -> Result<Vec<Message>> {
        self.adapter.search_short_term(query, limit).await
    }
    
    /// Clear memory
    pub async fn clear(&mut self) -> Result<()> {
        self.adapter.clear_short_term().await
    }
    
    /// Get the config
    pub fn config(&self) -> &MemoryConfig {
        &self.config
    }
}

impl Default for Memory {
    fn default() -> Self {
        Self::default_memory()
    }
}

impl std::fmt::Debug for Memory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Memory")
            .field("config", &self.config)
            .finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::llm::Role;
    
    #[test]
    fn test_conversation_history() {
        let mut history = ConversationHistory::new(5);
        
        history.add(Message::user("Hello"));
        history.add(Message::assistant("Hi there!"));
        
        assert_eq!(history.len(), 2);
        assert!(!history.is_empty());
    }
    
    #[test]
    fn test_history_trimming() {
        let mut history = ConversationHistory::new(3);
        
        history.add(Message::system("You are helpful"));
        history.add(Message::user("1"));
        history.add(Message::assistant("1"));
        history.add(Message::user("2"));
        history.add(Message::assistant("2"));
        
        // Should keep system message and trim oldest non-system
        assert_eq!(history.len(), 3);
        assert_eq!(history.messages()[0].role, Role::System);
    }
    
    #[tokio::test]
    async fn test_in_memory_adapter() {
        let mut adapter = InMemoryAdapter::default();
        
        adapter.store_short_term(Message::user("Hello world")).await.unwrap();
        adapter.store_short_term(Message::assistant("Hi!")).await.unwrap();
        
        let messages = adapter.get_short_term().await.unwrap();
        assert_eq!(messages.len(), 2);
        
        let search = adapter.search_short_term("world", 10).await.unwrap();
        assert_eq!(search.len(), 1);
    }
}
