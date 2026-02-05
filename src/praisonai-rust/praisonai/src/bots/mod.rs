//! Bots Module for PraisonAI Rust SDK
//!
//! Defines protocols and types for messaging bot implementations.
//! Enables agents to communicate through messaging platforms like
//! Telegram, Discord, Slack, etc.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::bots::{BotMessage, BotUser, BotChannel, MessageType};
//!
//! let user = BotUser::new("user-123")
//!     .username("john_doe")
//!     .display_name("John Doe");
//!
//! let message = BotMessage::text("Hello!", user.clone(), "channel-1");
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

use crate::agent::Agent;
use crate::error::Result;

/// Types of bot messages.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageType {
    Text,
    Image,
    Audio,
    Video,
    File,
    Location,
    Sticker,
    Command,
    Callback,
    Reaction,
    Reply,
    Edit,
    Delete,
}

impl Default for MessageType {
    fn default() -> Self {
        Self::Text
    }
}

impl std::fmt::Display for MessageType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Self::Text => "text",
            Self::Image => "image",
            Self::Audio => "audio",
            Self::Video => "video",
            Self::File => "file",
            Self::Location => "location",
            Self::Sticker => "sticker",
            Self::Command => "command",
            Self::Callback => "callback",
            Self::Reaction => "reaction",
            Self::Reply => "reply",
            Self::Edit => "edit",
            Self::Delete => "delete",
        };
        write!(f, "{}", s)
    }
}

/// Get current timestamp in seconds since UNIX epoch.
fn current_timestamp() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Represents a user in a messaging platform.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotUser {
    /// Platform-specific user identifier
    pub user_id: String,
    /// User's username (if available)
    pub username: Option<String>,
    /// User's display name
    pub display_name: Option<String>,
    /// Whether this user is a bot
    pub is_bot: bool,
    /// Additional platform-specific metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl BotUser {
    /// Create a new bot user.
    pub fn new(user_id: impl Into<String>) -> Self {
        Self {
            user_id: user_id.into(),
            username: None,
            display_name: None,
            is_bot: false,
            metadata: HashMap::new(),
        }
    }

    /// Set username.
    pub fn username(mut self, username: impl Into<String>) -> Self {
        self.username = Some(username.into());
        self
    }

    /// Set display name.
    pub fn display_name(mut self, name: impl Into<String>) -> Self {
        self.display_name = Some(name.into());
        self
    }

    /// Set is_bot flag.
    pub fn is_bot(mut self, is_bot: bool) -> Self {
        self.is_bot = is_bot;
        self
    }

    /// Add metadata.
    pub fn metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }

    /// Convert to dictionary.
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("user_id".to_string(), serde_json::json!(self.user_id));
        map.insert("username".to_string(), serde_json::json!(self.username));
        map.insert("display_name".to_string(), serde_json::json!(self.display_name));
        map.insert("is_bot".to_string(), serde_json::json!(self.is_bot));
        map.insert("metadata".to_string(), serde_json::json!(self.metadata));
        map
    }
}

/// Represents a channel/chat in a messaging platform.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotChannel {
    /// Platform-specific channel identifier
    pub channel_id: String,
    /// Channel name (if available)
    pub name: Option<String>,
    /// Type of channel (dm, group, channel, thread)
    pub channel_type: String,
    /// Additional platform-specific metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl BotChannel {
    /// Create a new bot channel.
    pub fn new(channel_id: impl Into<String>) -> Self {
        Self {
            channel_id: channel_id.into(),
            name: None,
            channel_type: "dm".to_string(),
            metadata: HashMap::new(),
        }
    }

    /// Set channel name.
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set channel type.
    pub fn channel_type(mut self, channel_type: impl Into<String>) -> Self {
        self.channel_type = channel_type.into();
        self
    }

    /// Add metadata.
    pub fn metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }

    /// Convert to dictionary.
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("channel_id".to_string(), serde_json::json!(self.channel_id));
        map.insert("name".to_string(), serde_json::json!(self.name));
        map.insert("channel_type".to_string(), serde_json::json!(self.channel_type));
        map.insert("metadata".to_string(), serde_json::json!(self.metadata));
        map
    }
}

/// Represents a message in a messaging platform.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotMessage {
    /// Platform-specific message identifier
    pub message_id: String,
    /// Message content (text or structured data)
    pub content: serde_json::Value,
    /// Type of message
    pub message_type: MessageType,
    /// User who sent the message
    pub sender: Option<BotUser>,
    /// Channel where the message was sent
    pub channel: Option<BotChannel>,
    /// Message timestamp
    pub timestamp: f64,
    /// ID of message being replied to
    pub reply_to: Option<String>,
    /// Thread identifier (for threaded conversations)
    pub thread_id: Option<String>,
    /// List of attachment URLs or data
    pub attachments: Vec<serde_json::Value>,
    /// Additional platform-specific metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl BotMessage {
    /// Create a new bot message.
    pub fn new(content: serde_json::Value) -> Self {
        Self {
            message_id: Uuid::new_v4().to_string(),
            content,
            message_type: MessageType::Text,
            sender: None,
            channel: None,
            timestamp: current_timestamp(),
            reply_to: None,
            thread_id: None,
            attachments: Vec::new(),
            metadata: HashMap::new(),
        }
    }

    /// Create a text message.
    pub fn text(
        text: impl Into<String>,
        sender: BotUser,
        channel_id: impl Into<String>,
    ) -> Self {
        Self {
            message_id: Uuid::new_v4().to_string(),
            content: serde_json::json!(text.into()),
            message_type: MessageType::Text,
            sender: Some(sender),
            channel: Some(BotChannel::new(channel_id)),
            timestamp: current_timestamp(),
            reply_to: None,
            thread_id: None,
            attachments: Vec::new(),
            metadata: HashMap::new(),
        }
    }

    /// Set message type.
    pub fn message_type(mut self, msg_type: MessageType) -> Self {
        self.message_type = msg_type;
        self
    }

    /// Set sender.
    pub fn sender(mut self, sender: BotUser) -> Self {
        self.sender = Some(sender);
        self
    }

    /// Set channel.
    pub fn channel(mut self, channel: BotChannel) -> Self {
        self.channel = Some(channel);
        self
    }

    /// Set reply_to.
    pub fn reply_to(mut self, message_id: impl Into<String>) -> Self {
        self.reply_to = Some(message_id.into());
        self
    }

    /// Set thread_id.
    pub fn thread_id(mut self, thread_id: impl Into<String>) -> Self {
        self.thread_id = Some(thread_id.into());
        self
    }

    /// Add attachment.
    pub fn attachment(mut self, attachment: serde_json::Value) -> Self {
        self.attachments.push(attachment);
        self
    }

    /// Add metadata.
    pub fn metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }

    /// Get text content if available.
    pub fn text_content(&self) -> Option<&str> {
        self.content.as_str()
    }

    /// Check if message is a command.
    pub fn is_command(&self) -> bool {
        self.message_type == MessageType::Command
            || self
                .content
                .as_str()
                .map(|s| s.starts_with('/'))
                .unwrap_or(false)
    }

    /// Extract command name if this is a command message.
    pub fn command(&self) -> Option<String> {
        if !self.is_command() {
            return None;
        }
        self.content.as_str().and_then(|text| {
            if text.starts_with('/') {
                text.split_whitespace()
                    .next()
                    .map(|s| s[1..].to_string())
            } else {
                None
            }
        })
    }

    /// Extract command arguments if this is a command message.
    pub fn command_args(&self) -> Vec<String> {
        if !self.is_command() {
            return Vec::new();
        }
        self.content
            .as_str()
            .map(|text| {
                text.split_whitespace()
                    .skip(1)
                    .map(String::from)
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Convert to dictionary.
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("message_id".to_string(), serde_json::json!(self.message_id));
        map.insert("content".to_string(), self.content.clone());
        map.insert("message_type".to_string(), serde_json::json!(self.message_type.to_string()));
        map.insert("sender".to_string(), serde_json::json!(self.sender.as_ref().map(|s| s.to_dict())));
        map.insert("channel".to_string(), serde_json::json!(self.channel.as_ref().map(|c| c.to_dict())));
        map.insert("timestamp".to_string(), serde_json::json!(self.timestamp));
        map.insert("reply_to".to_string(), serde_json::json!(self.reply_to));
        map.insert("thread_id".to_string(), serde_json::json!(self.thread_id));
        map.insert("attachments".to_string(), serde_json::json!(self.attachments));
        map.insert("metadata".to_string(), serde_json::json!(self.metadata));
        map
    }
}

impl Default for BotMessage {
    fn default() -> Self {
        Self::new(serde_json::json!(""))
    }
}

/// Configuration for a bot.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotConfig {
    /// Bot token for authentication
    pub token: String,
    /// Platform name (telegram, discord, slack, etc.)
    pub platform: String,
    /// Whether to use webhooks (vs polling)
    pub use_webhooks: bool,
    /// Webhook URL (if use_webhooks is true)
    pub webhook_url: Option<String>,
    /// Polling interval in seconds
    pub polling_interval: u64,
    /// Command prefix (default: "/")
    pub command_prefix: String,
    /// Additional platform-specific configuration
    pub extra: HashMap<String, serde_json::Value>,
}

impl Default for BotConfig {
    fn default() -> Self {
        Self {
            token: String::new(),
            platform: "telegram".to_string(),
            use_webhooks: false,
            webhook_url: None,
            polling_interval: 1,
            command_prefix: "/".to_string(),
            extra: HashMap::new(),
        }
    }
}

impl BotConfig {
    /// Create a new bot config.
    pub fn new(token: impl Into<String>, platform: impl Into<String>) -> Self {
        Self {
            token: token.into(),
            platform: platform.into(),
            ..Default::default()
        }
    }

    /// Enable webhooks.
    pub fn webhooks(mut self, url: impl Into<String>) -> Self {
        self.use_webhooks = true;
        self.webhook_url = Some(url.into());
        self
    }

    /// Set polling interval.
    pub fn polling_interval(mut self, seconds: u64) -> Self {
        self.polling_interval = seconds;
        self
    }

    /// Set command prefix.
    pub fn command_prefix(mut self, prefix: impl Into<String>) -> Self {
        self.command_prefix = prefix.into();
        self
    }

    /// Add extra configuration.
    pub fn extra(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.extra.insert(key.into(), value);
        self
    }
}

/// Protocol for messaging bot implementations.
///
/// Bots connect agents to messaging platforms, handling:
/// - Message receiving and sending
/// - Command handling
/// - Webhook/polling management
/// - User and channel management
#[async_trait]
pub trait BotProtocol: Send + Sync {
    /// Whether the bot is currently running.
    fn is_running(&self) -> bool;

    /// Platform name (telegram, discord, slack, etc.).
    fn platform(&self) -> &str;

    /// The bot's user information.
    fn bot_user(&self) -> Option<&BotUser>;

    /// Start the bot (begin receiving messages).
    async fn start(&mut self) -> Result<()>;

    /// Stop the bot.
    async fn stop(&mut self) -> Result<()>;

    /// Set the agent that handles messages.
    fn set_agent(&mut self, agent: Arc<Agent>);

    /// Get the current agent.
    fn get_agent(&self) -> Option<Arc<Agent>>;

    /// Send a message to a channel.
    async fn send_message(
        &self,
        channel_id: &str,
        content: serde_json::Value,
        reply_to: Option<String>,
        thread_id: Option<String>,
    ) -> Result<BotMessage>;

    /// Edit an existing message.
    async fn edit_message(
        &self,
        channel_id: &str,
        message_id: &str,
        content: serde_json::Value,
    ) -> Result<BotMessage>;

    /// Delete a message.
    async fn delete_message(&self, channel_id: &str, message_id: &str) -> Result<bool>;

    /// Send typing indicator to a channel.
    async fn send_typing(&self, channel_id: &str) -> Result<()>;

    /// Get user information.
    async fn get_user(&self, user_id: &str) -> Result<Option<BotUser>>;

    /// Get channel information.
    async fn get_channel(&self, channel_id: &str) -> Result<Option<BotChannel>>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_message_type() {
        assert_eq!(MessageType::default(), MessageType::Text);
        assert_eq!(MessageType::Command.to_string(), "command");
        assert_eq!(MessageType::Image.to_string(), "image");
    }

    #[test]
    fn test_bot_user_new() {
        let user = BotUser::new("user-123");
        assert_eq!(user.user_id, "user-123");
        assert!(user.username.is_none());
        assert!(!user.is_bot);
    }

    #[test]
    fn test_bot_user_builder() {
        let user = BotUser::new("user-123")
            .username("john_doe")
            .display_name("John Doe")
            .is_bot(false)
            .metadata("role", serde_json::json!("admin"));

        assert_eq!(user.username, Some("john_doe".to_string()));
        assert_eq!(user.display_name, Some("John Doe".to_string()));
        assert_eq!(user.metadata.get("role").unwrap(), "admin");
    }

    #[test]
    fn test_bot_channel_new() {
        let channel = BotChannel::new("channel-1");
        assert_eq!(channel.channel_id, "channel-1");
        assert_eq!(channel.channel_type, "dm");
    }

    #[test]
    fn test_bot_channel_builder() {
        let channel = BotChannel::new("channel-1")
            .name("General")
            .channel_type("group");

        assert_eq!(channel.name, Some("General".to_string()));
        assert_eq!(channel.channel_type, "group");
    }

    #[test]
    fn test_bot_message_text() {
        let user = BotUser::new("user-1");
        let msg = BotMessage::text("Hello world", user, "channel-1");

        assert_eq!(msg.text_content(), Some("Hello world"));
        assert_eq!(msg.message_type, MessageType::Text);
        assert!(msg.sender.is_some());
        assert!(msg.channel.is_some());
    }

    #[test]
    fn test_bot_message_command() {
        let user = BotUser::new("user-1");
        let msg = BotMessage::text("/help arg1 arg2", user, "channel-1");

        assert!(msg.is_command());
        assert_eq!(msg.command(), Some("help".to_string()));
        assert_eq!(msg.command_args(), vec!["arg1", "arg2"]);
    }

    #[test]
    fn test_bot_message_not_command() {
        let user = BotUser::new("user-1");
        let msg = BotMessage::text("Hello world", user, "channel-1");

        assert!(!msg.is_command());
        assert!(msg.command().is_none());
        assert!(msg.command_args().is_empty());
    }

    #[test]
    fn test_bot_message_builder() {
        let msg = BotMessage::new(serde_json::json!("Hello"))
            .message_type(MessageType::Text)
            .reply_to("msg-123")
            .thread_id("thread-1")
            .attachment(serde_json::json!({"url": "https://example.com/image.png"}));

        assert_eq!(msg.reply_to, Some("msg-123".to_string()));
        assert_eq!(msg.thread_id, Some("thread-1".to_string()));
        assert_eq!(msg.attachments.len(), 1);
    }

    #[test]
    fn test_bot_config_default() {
        let config = BotConfig::default();
        assert_eq!(config.platform, "telegram");
        assert!(!config.use_webhooks);
        assert_eq!(config.command_prefix, "/");
    }

    #[test]
    fn test_bot_config_builder() {
        let config = BotConfig::new("token-123", "discord")
            .webhooks("https://example.com/webhook")
            .command_prefix("!")
            .polling_interval(5);

        assert_eq!(config.token, "token-123");
        assert_eq!(config.platform, "discord");
        assert!(config.use_webhooks);
        assert_eq!(config.webhook_url, Some("https://example.com/webhook".to_string()));
        assert_eq!(config.command_prefix, "!");
        assert_eq!(config.polling_interval, 5);
    }

    #[test]
    fn test_bot_user_to_dict() {
        let user = BotUser::new("user-1").username("test");
        let dict = user.to_dict();

        assert_eq!(dict.get("user_id").unwrap(), "user-1");
        assert_eq!(dict.get("username").unwrap(), "test");
    }

    #[test]
    fn test_bot_message_to_dict() {
        let user = BotUser::new("user-1");
        let msg = BotMessage::text("Hello", user, "channel-1");
        let dict = msg.to_dict();

        assert!(dict.contains_key("message_id"));
        assert_eq!(dict.get("content").unwrap(), "Hello");
        assert_eq!(dict.get("message_type").unwrap(), "text");
    }
}
