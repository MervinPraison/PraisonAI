//! Specialized Agents Module
//!
//! This module provides specialized agent types for specific tasks:
//! - `AudioAgent` - Text-to-speech and speech-to-text
//! - `VideoAgent` - Video generation
//! - `ImageAgent` - Image generation
//! - `OCRAgent` - Optical character recognition
//! - `CodeAgent` - Code generation and execution
//! - `VisionAgent` - Image analysis and understanding
//!
//! # Example
//!
//! ```ignore
//! use praisonai::agents::{AudioAgent, AudioConfig};
//!
//! let agent = AudioAgent::new()
//!     .model("openai/tts-1")
//!     .voice("alloy")
//!     .build()?;
//!
//! agent.speech("Hello world!", "output.mp3")?;
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::error::{Error, Result};

// =============================================================================
// AUDIO AGENT
// =============================================================================

/// Configuration for audio processing settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioConfig {
    /// Voice for TTS (e.g., "alloy", "echo", "fable", "onyx", "nova", "shimmer")
    pub voice: String,
    /// Speed multiplier (0.25 to 4.0)
    pub speed: f32,
    /// Response format (mp3, opus, aac, flac, wav, pcm)
    pub response_format: String,
    /// Language for STT
    pub language: Option<String>,
    /// Temperature for STT
    pub temperature: f32,
    /// Timeout in seconds
    pub timeout: u32,
    /// API base URL
    pub api_base: Option<String>,
    /// API key
    pub api_key: Option<String>,
}

impl Default for AudioConfig {
    fn default() -> Self {
        Self {
            voice: "alloy".to_string(),
            speed: 1.0,
            response_format: "mp3".to_string(),
            language: None,
            temperature: 0.0,
            timeout: 600,
            api_base: None,
            api_key: None,
        }
    }
}

impl AudioConfig {
    /// Create a new AudioConfig with default values
    pub fn new() -> Self {
        Self::default()
    }

    /// Set the voice
    pub fn voice(mut self, voice: impl Into<String>) -> Self {
        self.voice = voice.into();
        self
    }

    /// Set the speed
    pub fn speed(mut self, speed: f32) -> Self {
        self.speed = speed;
        self
    }

    /// Set the response format
    pub fn response_format(mut self, format: impl Into<String>) -> Self {
        self.response_format = format.into();
        self
    }

    /// Set the language
    pub fn language(mut self, language: impl Into<String>) -> Self {
        self.language = Some(language.into());
        self
    }

    /// Set the timeout
    pub fn timeout(mut self, timeout: u32) -> Self {
        self.timeout = timeout;
        self
    }
}

/// A specialized agent for audio processing using AI models.
///
/// Provides Text-to-Speech (TTS) and Speech-to-Text (STT) capabilities.
#[derive(Debug, Clone)]
pub struct AudioAgent {
    /// Agent name
    pub name: String,
    /// LLM model (e.g., "openai/tts-1", "openai/whisper-1")
    pub model: String,
    /// Audio configuration
    pub config: AudioConfig,
    /// Verbose output
    pub verbose: bool,
}

impl Default for AudioAgent {
    fn default() -> Self {
        Self {
            name: "AudioAgent".to_string(),
            model: "openai/tts-1".to_string(),
            config: AudioConfig::default(),
            verbose: true,
        }
    }
}

impl AudioAgent {
    /// Create a new AudioAgent builder
    pub fn new() -> AudioAgentBuilder {
        AudioAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Get model
    pub fn model(&self) -> &str {
        &self.model
    }

    /// Generate speech from text (placeholder - requires LLM integration)
    pub fn speech(&self, text: &str, output_path: &str) -> Result<String> {
        // This is a placeholder - actual implementation would call LLM API
        Ok(format!(
            "Generated speech for '{}' to '{}' using model '{}'",
            text, output_path, self.model
        ))
    }

    /// Transcribe audio to text (placeholder - requires LLM integration)
    pub fn transcribe(&self, audio_path: &str) -> Result<String> {
        // This is a placeholder - actual implementation would call LLM API
        Ok(format!(
            "Transcribed audio from '{}' using model '{}'",
            audio_path, self.model
        ))
    }
}

/// Builder for AudioAgent
#[derive(Debug, Default)]
pub struct AudioAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    config: AudioConfig,
    verbose: bool,
}

impl AudioAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set the voice
    pub fn voice(mut self, voice: impl Into<String>) -> Self {
        self.config.voice = voice.into();
        self
    }

    /// Set the speed
    pub fn speed(mut self, speed: f32) -> Self {
        self.config.speed = speed;
        self
    }

    /// Set verbose mode
    pub fn verbose(mut self, verbose: bool) -> Self {
        self.verbose = verbose;
        self
    }

    /// Set the config
    pub fn config(mut self, config: AudioConfig) -> Self {
        self.config = config;
        self
    }

    /// Build the AudioAgent
    pub fn build(self) -> Result<AudioAgent> {
        Ok(AudioAgent {
            name: self.name.unwrap_or_else(|| "AudioAgent".to_string()),
            model: self.model.unwrap_or_else(|| "openai/tts-1".to_string()),
            config: self.config,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// IMAGE AGENT
// =============================================================================

/// Configuration for image generation settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageConfig {
    /// Style of the generated image
    pub style: String,
    /// Response format (url or b64_json)
    pub response_format: String,
    /// Timeout in seconds
    pub timeout: u32,
    /// Image size (e.g., "1024x1024", "1792x1024")
    pub size: Option<String>,
    /// Image quality (standard or hd)
    pub quality: Option<String>,
    /// API base URL
    pub api_base: Option<String>,
    /// API key
    pub api_key: Option<String>,
}

impl Default for ImageConfig {
    fn default() -> Self {
        Self {
            style: "natural".to_string(),
            response_format: "url".to_string(),
            timeout: 600,
            size: Some("1024x1024".to_string()),
            quality: Some("standard".to_string()),
            api_base: None,
            api_key: None,
        }
    }
}

impl ImageConfig {
    /// Create a new ImageConfig
    pub fn new() -> Self {
        Self::default()
    }

    /// Set the style
    pub fn style(mut self, style: impl Into<String>) -> Self {
        self.style = style.into();
        self
    }

    /// Set the size
    pub fn size(mut self, size: impl Into<String>) -> Self {
        self.size = Some(size.into());
        self
    }

    /// Set the quality
    pub fn quality(mut self, quality: impl Into<String>) -> Self {
        self.quality = Some(quality.into());
        self
    }
}

/// A specialized agent for generating images using AI models.
#[derive(Debug, Clone)]
pub struct ImageAgent {
    /// Agent name
    pub name: String,
    /// LLM model (e.g., "dall-e-3", "dall-e-2")
    pub model: String,
    /// Image configuration
    pub config: ImageConfig,
    /// Verbose output
    pub verbose: bool,
}

impl Default for ImageAgent {
    fn default() -> Self {
        Self {
            name: "ImageAgent".to_string(),
            model: "dall-e-3".to_string(),
            config: ImageConfig::default(),
            verbose: true,
        }
    }
}

impl ImageAgent {
    /// Create a new ImageAgent builder
    pub fn new() -> ImageAgentBuilder {
        ImageAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Generate an image from a prompt (placeholder)
    pub fn generate(&self, prompt: &str) -> Result<ImageResult> {
        Ok(ImageResult {
            url: Some(format!("https://example.com/generated-image-{}.png", uuid::Uuid::new_v4())),
            b64_json: None,
            revised_prompt: Some(prompt.to_string()),
        })
    }
}

/// Result of image generation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageResult {
    /// URL of the generated image
    pub url: Option<String>,
    /// Base64-encoded image data
    pub b64_json: Option<String>,
    /// Revised prompt used for generation
    pub revised_prompt: Option<String>,
}

/// Builder for ImageAgent
#[derive(Debug, Default)]
pub struct ImageAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    config: ImageConfig,
    verbose: bool,
}

impl ImageAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set the config
    pub fn config(mut self, config: ImageConfig) -> Self {
        self.config = config;
        self
    }

    /// Set verbose mode
    pub fn verbose(mut self, verbose: bool) -> Self {
        self.verbose = verbose;
        self
    }

    /// Build the ImageAgent
    pub fn build(self) -> Result<ImageAgent> {
        Ok(ImageAgent {
            name: self.name.unwrap_or_else(|| "ImageAgent".to_string()),
            model: self.model.unwrap_or_else(|| "dall-e-3".to_string()),
            config: self.config,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// VIDEO AGENT
// =============================================================================

/// Configuration for video generation settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoConfig {
    /// Video duration in seconds
    pub seconds: String,
    /// Video dimensions (e.g., "720x1280", "1280x720")
    pub size: Option<String>,
    /// Timeout in seconds
    pub timeout: u32,
    /// Poll interval for status checks
    pub poll_interval: u32,
    /// Maximum wait time
    pub max_wait_time: u32,
    /// API base URL
    pub api_base: Option<String>,
    /// API key
    pub api_key: Option<String>,
}

impl Default for VideoConfig {
    fn default() -> Self {
        Self {
            seconds: "8".to_string(),
            size: None,
            timeout: 600,
            poll_interval: 10,
            max_wait_time: 600,
            api_base: None,
            api_key: None,
        }
    }
}

impl VideoConfig {
    /// Create a new VideoConfig
    pub fn new() -> Self {
        Self::default()
    }

    /// Set the duration
    pub fn seconds(mut self, seconds: impl Into<String>) -> Self {
        self.seconds = seconds.into();
        self
    }

    /// Set the size
    pub fn size(mut self, size: impl Into<String>) -> Self {
        self.size = Some(size.into());
        self
    }
}

/// A specialized agent for generating videos using AI models.
#[derive(Debug, Clone)]
pub struct VideoAgent {
    /// Agent name
    pub name: String,
    /// LLM model (e.g., "openai/sora-2")
    pub model: String,
    /// Video configuration
    pub config: VideoConfig,
    /// Verbose output
    pub verbose: bool,
}

impl Default for VideoAgent {
    fn default() -> Self {
        Self {
            name: "VideoAgent".to_string(),
            model: "openai/sora-2".to_string(),
            config: VideoConfig::default(),
            verbose: true,
        }
    }
}

impl VideoAgent {
    /// Create a new VideoAgent builder
    pub fn new() -> VideoAgentBuilder {
        VideoAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Generate a video from a prompt (placeholder)
    pub fn generate(&self, _prompt: &str) -> Result<VideoResult> {
        Ok(VideoResult {
            id: uuid::Uuid::new_v4().to_string(),
            status: VideoStatus::Pending,
            url: None,
            error: None,
        })
    }
}

/// Status of video generation
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum VideoStatus {
    /// Video is being generated
    Pending,
    /// Video generation in progress
    Processing,
    /// Video generation completed
    Completed,
    /// Video generation failed
    Failed,
}

/// Result of video generation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoResult {
    /// Generation ID
    pub id: String,
    /// Current status
    pub status: VideoStatus,
    /// URL of the generated video
    pub url: Option<String>,
    /// Error message if failed
    pub error: Option<String>,
}

/// Builder for VideoAgent
#[derive(Debug, Default)]
pub struct VideoAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    config: VideoConfig,
    verbose: bool,
}

impl VideoAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set the config
    pub fn config(mut self, config: VideoConfig) -> Self {
        self.config = config;
        self
    }

    /// Build the VideoAgent
    pub fn build(self) -> Result<VideoAgent> {
        Ok(VideoAgent {
            name: self.name.unwrap_or_else(|| "VideoAgent".to_string()),
            model: self.model.unwrap_or_else(|| "openai/sora-2".to_string()),
            config: self.config,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// OCR AGENT
// =============================================================================

/// Configuration for OCR settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OCRConfig {
    /// Include base64 image data in response
    pub include_image_base64: bool,
    /// Specific pages to process
    pub pages: Option<Vec<u32>>,
    /// Maximum number of images to process
    pub image_limit: Option<u32>,
    /// Timeout in seconds
    pub timeout: u32,
    /// API base URL
    pub api_base: Option<String>,
    /// API key
    pub api_key: Option<String>,
}

impl Default for OCRConfig {
    fn default() -> Self {
        Self {
            include_image_base64: false,
            pages: None,
            image_limit: None,
            timeout: 600,
            api_base: None,
            api_key: None,
        }
    }
}

impl OCRConfig {
    /// Create a new OCRConfig
    pub fn new() -> Self {
        Self::default()
    }

    /// Set pages to process
    pub fn pages(mut self, pages: Vec<u32>) -> Self {
        self.pages = Some(pages);
        self
    }

    /// Set image limit
    pub fn image_limit(mut self, limit: u32) -> Self {
        self.image_limit = Some(limit);
        self
    }
}

/// A specialized agent for OCR (Optical Character Recognition).
#[derive(Debug, Clone)]
pub struct OCRAgent {
    /// Agent name
    pub name: String,
    /// LLM model (e.g., "mistral/mistral-ocr-latest")
    pub model: String,
    /// OCR configuration
    pub config: OCRConfig,
    /// Verbose output
    pub verbose: bool,
}

impl Default for OCRAgent {
    fn default() -> Self {
        Self {
            name: "OCRAgent".to_string(),
            model: "mistral/mistral-ocr-latest".to_string(),
            config: OCRConfig::default(),
            verbose: true,
        }
    }
}

impl OCRAgent {
    /// Create a new OCRAgent builder
    pub fn new() -> OCRAgentBuilder {
        OCRAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Extract text from a document or image (placeholder)
    pub fn extract(&self, source: &str) -> Result<OCRResult> {
        Ok(OCRResult {
            text: format!("Extracted text from {}", source),
            pages: vec![OCRPage {
                page_number: 1,
                markdown: "# Extracted Content\n\nSample extracted text.".to_string(),
                images: vec![],
            }],
        })
    }
}

/// Result of OCR extraction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OCRResult {
    /// Full extracted text
    pub text: String,
    /// Pages with extracted content
    pub pages: Vec<OCRPage>,
}

/// A page of OCR results
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OCRPage {
    /// Page number
    pub page_number: u32,
    /// Markdown content
    pub markdown: String,
    /// Extracted images
    pub images: Vec<String>,
}

/// Builder for OCRAgent
#[derive(Debug, Default)]
pub struct OCRAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    config: OCRConfig,
    verbose: bool,
}

impl OCRAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set the config
    pub fn config(mut self, config: OCRConfig) -> Self {
        self.config = config;
        self
    }

    /// Build the OCRAgent
    pub fn build(self) -> Result<OCRAgent> {
        Ok(OCRAgent {
            name: self.name.unwrap_or_else(|| "OCRAgent".to_string()),
            model: self.model.unwrap_or_else(|| "mistral/mistral-ocr-latest".to_string()),
            config: self.config,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// CODE AGENT
// =============================================================================

/// Configuration for code execution settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeConfig {
    /// Enable sandboxed execution
    pub sandbox: bool,
    /// Execution timeout in seconds
    pub timeout: u32,
    /// Allowed programming languages
    pub allowed_languages: Vec<String>,
    /// Maximum output length
    pub max_output_length: usize,
    /// Working directory
    pub working_directory: Option<String>,
    /// Environment variables
    pub environment: HashMap<String, String>,
}

impl Default for CodeConfig {
    fn default() -> Self {
        Self {
            sandbox: true,
            timeout: 30,
            allowed_languages: vec!["python".to_string()],
            max_output_length: 10000,
            working_directory: None,
            environment: HashMap::new(),
        }
    }
}

impl CodeConfig {
    /// Create a new CodeConfig
    pub fn new() -> Self {
        Self::default()
    }

    /// Set sandbox mode
    pub fn sandbox(mut self, sandbox: bool) -> Self {
        self.sandbox = sandbox;
        self
    }

    /// Set timeout
    pub fn timeout(mut self, timeout: u32) -> Self {
        self.timeout = timeout;
        self
    }

    /// Set allowed languages
    pub fn allowed_languages(mut self, languages: Vec<String>) -> Self {
        self.allowed_languages = languages;
        self
    }
}

/// A specialized agent for code generation and execution.
#[derive(Debug, Clone)]
pub struct CodeAgent {
    /// Agent name
    pub name: String,
    /// LLM model
    pub model: String,
    /// Code configuration
    pub config: CodeConfig,
    /// System instructions
    pub instructions: Option<String>,
    /// Verbose output
    pub verbose: bool,
}

impl Default for CodeAgent {
    fn default() -> Self {
        Self {
            name: "CodeAgent".to_string(),
            model: "gpt-4o-mini".to_string(),
            config: CodeConfig::default(),
            instructions: None,
            verbose: true,
        }
    }
}

impl CodeAgent {
    /// Create a new CodeAgent builder
    pub fn new() -> CodeAgentBuilder {
        CodeAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Generate code from a description (placeholder)
    pub fn generate(&self, description: &str) -> Result<String> {
        Ok(format!("# Generated code for: {}\ndef main():\n    pass", description))
    }

    /// Execute code (placeholder - would require sandbox)
    pub fn execute(&self, _code: &str) -> Result<CodeExecutionResult> {
        if !self.config.sandbox {
            return Err(Error::config("Code execution requires sandbox mode"));
        }
        Ok(CodeExecutionResult {
            output: "Execution output".to_string(),
            exit_code: 0,
            error: None,
        })
    }

    /// Review code (placeholder)
    pub fn review(&self, code: &str) -> Result<String> {
        Ok(format!("Code review for:\n{}\n\nNo issues found.", code))
    }
}

/// Result of code execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeExecutionResult {
    /// Standard output
    pub output: String,
    /// Exit code
    pub exit_code: i32,
    /// Error message if any
    pub error: Option<String>,
}

/// Builder for CodeAgent
#[derive(Debug, Default)]
pub struct CodeAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    config: CodeConfig,
    instructions: Option<String>,
    verbose: bool,
}

impl CodeAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set the config
    pub fn config(mut self, config: CodeConfig) -> Self {
        self.config = config;
        self
    }

    /// Set instructions
    pub fn instructions(mut self, instructions: impl Into<String>) -> Self {
        self.instructions = Some(instructions.into());
        self
    }

    /// Build the CodeAgent
    pub fn build(self) -> Result<CodeAgent> {
        Ok(CodeAgent {
            name: self.name.unwrap_or_else(|| "CodeAgent".to_string()),
            model: self.model.unwrap_or_else(|| "gpt-4o-mini".to_string()),
            config: self.config,
            instructions: self.instructions,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// VISION AGENT
// =============================================================================

/// Configuration for vision processing settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VisionConfig {
    /// Detail level (low, high, auto)
    pub detail: String,
    /// Maximum tokens for response
    pub max_tokens: u32,
    /// Timeout in seconds
    pub timeout: u32,
    /// API base URL
    pub api_base: Option<String>,
    /// API key
    pub api_key: Option<String>,
}

impl Default for VisionConfig {
    fn default() -> Self {
        Self {
            detail: "auto".to_string(),
            max_tokens: 4096,
            timeout: 60,
            api_base: None,
            api_key: None,
        }
    }
}

impl VisionConfig {
    /// Create a new VisionConfig
    pub fn new() -> Self {
        Self::default()
    }

    /// Set detail level
    pub fn detail(mut self, detail: impl Into<String>) -> Self {
        self.detail = detail.into();
        self
    }

    /// Set max tokens
    pub fn max_tokens(mut self, max_tokens: u32) -> Self {
        self.max_tokens = max_tokens;
        self
    }
}

/// A specialized agent for image analysis and understanding.
#[derive(Debug, Clone)]
pub struct VisionAgent {
    /// Agent name
    pub name: String,
    /// LLM model (e.g., "gpt-4o", "claude-3-5-sonnet")
    pub model: String,
    /// Vision configuration
    pub config: VisionConfig,
    /// Verbose output
    pub verbose: bool,
}

impl Default for VisionAgent {
    fn default() -> Self {
        Self {
            name: "VisionAgent".to_string(),
            model: "gpt-4o".to_string(),
            config: VisionConfig::default(),
            verbose: true,
        }
    }
}

impl VisionAgent {
    /// Create a new VisionAgent builder
    pub fn new() -> VisionAgentBuilder {
        VisionAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Describe an image (placeholder)
    pub fn describe(&self, image_source: &str) -> Result<String> {
        Ok(format!("Description of image at: {}", image_source))
    }

    /// Analyze an image with a custom prompt (placeholder)
    pub fn analyze(&self, image_source: &str, prompt: &str) -> Result<String> {
        Ok(format!("Analysis of {} with prompt: {}", image_source, prompt))
    }

    /// Compare multiple images (placeholder)
    pub fn compare(&self, images: &[&str]) -> Result<String> {
        Ok(format!("Comparison of {} images", images.len()))
    }
}

/// Builder for VisionAgent
#[derive(Debug, Default)]
pub struct VisionAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    config: VisionConfig,
    verbose: bool,
}

impl VisionAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set the config
    pub fn config(mut self, config: VisionConfig) -> Self {
        self.config = config;
        self
    }

    /// Build the VisionAgent
    pub fn build(self) -> Result<VisionAgent> {
        Ok(VisionAgent {
            name: self.name.unwrap_or_else(|| "VisionAgent".to_string()),
            model: self.model.unwrap_or_else(|| "gpt-4o".to_string()),
            config: self.config,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// DEEP RESEARCH AGENT
// =============================================================================

/// Configuration for deep research settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeepResearchConfig {
    /// Maximum number of sources to include
    pub max_sources: usize,
    /// Include citations in output
    pub include_citations: bool,
    /// Maximum research depth
    pub max_depth: usize,
    /// Timeout in seconds
    pub timeout: u32,
    /// API base URL
    pub api_base: Option<String>,
    /// API key
    pub api_key: Option<String>,
}

impl Default for DeepResearchConfig {
    fn default() -> Self {
        Self {
            max_sources: 10,
            include_citations: true,
            max_depth: 3,
            timeout: 600,
            api_base: None,
            api_key: None,
        }
    }
}

impl DeepResearchConfig {
    /// Create a new config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set max sources
    pub fn max_sources(mut self, max: usize) -> Self {
        self.max_sources = max;
        self
    }

    /// Set include citations
    pub fn include_citations(mut self, include: bool) -> Self {
        self.include_citations = include;
        self
    }

    /// Set max depth
    pub fn max_depth(mut self, depth: usize) -> Self {
        self.max_depth = depth;
        self
    }

    /// Set timeout
    pub fn timeout(mut self, timeout: u32) -> Self {
        self.timeout = timeout;
        self
    }
}

/// Citation in a research result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResearchCitation {
    /// Citation title
    pub title: String,
    /// Citation URL
    pub url: String,
    /// Start index in text
    pub start_index: usize,
    /// End index in text
    pub end_index: usize,
}

/// Result of deep research.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeepResearchResult {
    /// Research report
    pub report: String,
    /// Citations
    pub citations: Vec<ResearchCitation>,
    /// Sources used
    pub sources_count: usize,
    /// Time taken in ms
    pub time_ms: u64,
}

/// Agent for deep research using specialized APIs.
#[derive(Debug)]
pub struct DeepResearchAgent {
    name: String,
    /// Model to use
    pub model: String,
    /// Instructions
    pub instructions: Option<String>,
    /// Configuration
    pub config: DeepResearchConfig,
    verbose: bool,
}

impl DeepResearchAgent {
    /// Create a new builder
    pub fn new() -> DeepResearchAgentBuilder {
        DeepResearchAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Perform deep research
    pub fn research(&self, query: &str) -> Result<DeepResearchResult> {
        // Placeholder implementation
        Ok(DeepResearchResult {
            report: format!("Research report for: {}", query),
            citations: vec![],
            sources_count: 0,
            time_ms: 0,
        })
    }
}

impl Default for DeepResearchAgent {
    fn default() -> Self {
        Self {
            name: "DeepResearchAgent".to_string(),
            model: "o3-deep-research".to_string(),
            instructions: None,
            config: DeepResearchConfig::default(),
            verbose: false,
        }
    }
}

/// Builder for DeepResearchAgent.
#[derive(Debug, Default)]
pub struct DeepResearchAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    instructions: Option<String>,
    config: DeepResearchConfig,
    verbose: bool,
}

impl DeepResearchAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set instructions
    pub fn instructions(mut self, instructions: impl Into<String>) -> Self {
        self.instructions = Some(instructions.into());
        self
    }

    /// Set config
    pub fn config(mut self, config: DeepResearchConfig) -> Self {
        self.config = config;
        self
    }

    /// Build the agent
    pub fn build(self) -> Result<DeepResearchAgent> {
        Ok(DeepResearchAgent {
            name: self.name.unwrap_or_else(|| "DeepResearchAgent".to_string()),
            model: self.model.unwrap_or_else(|| "o3-deep-research".to_string()),
            instructions: self.instructions,
            config: self.config,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// REALTIME AGENT
// =============================================================================

/// Configuration for realtime voice settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RealtimeConfig {
    /// Voice for audio output
    pub voice: String,
    /// Modalities (text, audio)
    pub modalities: Vec<String>,
    /// Turn detection mode
    pub turn_detection: String,
    /// Input audio format
    pub input_audio_format: String,
    /// Output audio format
    pub output_audio_format: String,
    /// Temperature
    pub temperature: f32,
    /// Max response tokens
    pub max_response_output_tokens: Option<usize>,
    /// System instructions
    pub instructions: Option<String>,
}

impl Default for RealtimeConfig {
    fn default() -> Self {
        Self {
            voice: "alloy".to_string(),
            modalities: vec!["text".to_string(), "audio".to_string()],
            turn_detection: "server_vad".to_string(),
            input_audio_format: "pcm16".to_string(),
            output_audio_format: "pcm16".to_string(),
            temperature: 0.8,
            max_response_output_tokens: None,
            instructions: None,
        }
    }
}

impl RealtimeConfig {
    /// Create a new config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set voice
    pub fn voice(mut self, voice: impl Into<String>) -> Self {
        self.voice = voice.into();
        self
    }

    /// Set modalities
    pub fn modalities(mut self, modalities: Vec<String>) -> Self {
        self.modalities = modalities;
        self
    }

    /// Set turn detection
    pub fn turn_detection(mut self, mode: impl Into<String>) -> Self {
        self.turn_detection = mode.into();
        self
    }

    /// Set temperature
    pub fn temperature(mut self, temp: f32) -> Self {
        self.temperature = temp;
        self
    }

    /// Set max tokens
    pub fn max_response_output_tokens(mut self, tokens: usize) -> Self {
        self.max_response_output_tokens = Some(tokens);
        self
    }

    /// Set instructions
    pub fn instructions(mut self, instructions: impl Into<String>) -> Self {
        self.instructions = Some(instructions.into());
        self
    }
}

/// Agent for real-time voice conversations.
#[derive(Debug)]
pub struct RealtimeAgent {
    name: String,
    /// Model to use
    pub model: String,
    /// Configuration
    pub config: RealtimeConfig,
    verbose: bool,
}

impl RealtimeAgent {
    /// Create a new builder
    pub fn new() -> RealtimeAgentBuilder {
        RealtimeAgentBuilder::default()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Send text message (placeholder)
    pub fn send_text(&self, text: &str) -> Result<String> {
        Ok(format!("Sent: {}", text))
    }
}

impl Default for RealtimeAgent {
    fn default() -> Self {
        Self {
            name: "RealtimeAgent".to_string(),
            model: "gpt-4o-realtime-preview".to_string(),
            config: RealtimeConfig::default(),
            verbose: false,
        }
    }
}

/// Builder for RealtimeAgent.
#[derive(Debug, Default)]
pub struct RealtimeAgentBuilder {
    name: Option<String>,
    model: Option<String>,
    config: RealtimeConfig,
    verbose: bool,
}

impl RealtimeAgentBuilder {
    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Set voice
    pub fn voice(mut self, voice: impl Into<String>) -> Self {
        self.config.voice = voice.into();
        self
    }

    /// Set config
    pub fn config(mut self, config: RealtimeConfig) -> Self {
        self.config = config;
        self
    }

    /// Build the agent
    pub fn build(self) -> Result<RealtimeAgent> {
        Ok(RealtimeAgent {
            name: self.name.unwrap_or_else(|| "RealtimeAgent".to_string()),
            model: self.model.unwrap_or_else(|| "gpt-4o-realtime-preview".to_string()),
            config: self.config,
            verbose: self.verbose,
        })
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audio_agent_builder() {
        let agent = AudioAgent::new()
            .name("TestAudio")
            .model("openai/tts-1-hd")
            .voice("nova")
            .speed(1.5)
            .build()
            .unwrap();

        assert_eq!(agent.name(), "TestAudio");
        assert_eq!(agent.model(), "openai/tts-1-hd");
        assert_eq!(agent.config.voice, "nova");
        assert_eq!(agent.config.speed, 1.5);
    }

    #[test]
    fn test_audio_config_defaults() {
        let config = AudioConfig::default();
        assert_eq!(config.voice, "alloy");
        assert_eq!(config.speed, 1.0);
        assert_eq!(config.response_format, "mp3");
    }

    #[test]
    fn test_image_agent_builder() {
        let agent = ImageAgent::new()
            .name("TestImage")
            .model("dall-e-3")
            .build()
            .unwrap();

        assert_eq!(agent.name(), "TestImage");
        assert_eq!(agent.model, "dall-e-3");
    }

    #[test]
    fn test_image_config_builder() {
        let config = ImageConfig::new()
            .style("vivid")
            .size("1792x1024")
            .quality("hd");

        assert_eq!(config.style, "vivid");
        assert_eq!(config.size, Some("1792x1024".to_string()));
        assert_eq!(config.quality, Some("hd".to_string()));
    }

    #[test]
    fn test_video_agent_builder() {
        let agent = VideoAgent::new()
            .name("TestVideo")
            .model("openai/sora-2-pro")
            .build()
            .unwrap();

        assert_eq!(agent.name(), "TestVideo");
        assert_eq!(agent.model, "openai/sora-2-pro");
    }

    #[test]
    fn test_video_config_defaults() {
        let config = VideoConfig::default();
        assert_eq!(config.seconds, "8");
        assert_eq!(config.timeout, 600);
        assert_eq!(config.poll_interval, 10);
    }

    #[test]
    fn test_ocr_agent_builder() {
        let agent = OCRAgent::new()
            .name("TestOCR")
            .model("mistral/mistral-ocr-latest")
            .build()
            .unwrap();

        assert_eq!(agent.name(), "TestOCR");
        assert_eq!(agent.model, "mistral/mistral-ocr-latest");
    }

    #[test]
    fn test_ocr_config_builder() {
        let config = OCRConfig::new()
            .pages(vec![1, 2, 3])
            .image_limit(10);

        assert_eq!(config.pages, Some(vec![1, 2, 3]));
        assert_eq!(config.image_limit, Some(10));
    }

    #[test]
    fn test_code_agent_builder() {
        let agent = CodeAgent::new()
            .name("TestCode")
            .model("gpt-4o")
            .instructions("Write clean code")
            .build()
            .unwrap();

        assert_eq!(agent.name(), "TestCode");
        assert_eq!(agent.model, "gpt-4o");
        assert_eq!(agent.instructions, Some("Write clean code".to_string()));
    }

    #[test]
    fn test_code_config_defaults() {
        let config = CodeConfig::default();
        assert!(config.sandbox);
        assert_eq!(config.timeout, 30);
        assert_eq!(config.allowed_languages, vec!["python".to_string()]);
    }

    #[test]
    fn test_vision_agent_builder() {
        let agent = VisionAgent::new()
            .name("TestVision")
            .model("gpt-4o")
            .build()
            .unwrap();

        assert_eq!(agent.name(), "TestVision");
        assert_eq!(agent.model, "gpt-4o");
    }

    #[test]
    fn test_vision_config_builder() {
        let config = VisionConfig::new()
            .detail("high")
            .max_tokens(8192);

        assert_eq!(config.detail, "high");
        assert_eq!(config.max_tokens, 8192);
    }

    #[test]
    fn test_image_generate() {
        let agent = ImageAgent::new().build().unwrap();
        let result = agent.generate("A sunset over mountains").unwrap();
        assert!(result.url.is_some());
    }

    #[test]
    fn test_video_generate() {
        let agent = VideoAgent::new().build().unwrap();
        let result = agent.generate("A cat playing").unwrap();
        assert_eq!(result.status, VideoStatus::Pending);
    }

    #[test]
    fn test_ocr_extract() {
        let agent = OCRAgent::new().build().unwrap();
        let result = agent.extract("document.pdf").unwrap();
        assert!(!result.text.is_empty());
        assert!(!result.pages.is_empty());
    }

    #[test]
    fn test_code_generate() {
        let agent = CodeAgent::new().build().unwrap();
        let code = agent.generate("Calculate fibonacci").unwrap();
        assert!(code.contains("def main"));
    }

    #[test]
    fn test_vision_describe() {
        let agent = VisionAgent::new().build().unwrap();
        let description = agent.describe("image.jpg").unwrap();
        assert!(description.contains("image.jpg"));
    }

    #[test]
    fn test_deep_research_agent_builder() {
        let agent = DeepResearchAgent::new()
            .name("Researcher")
            .model("o3-deep-research")
            .instructions("Research thoroughly")
            .build()
            .unwrap();

        assert_eq!(agent.name(), "Researcher");
        assert_eq!(agent.model, "o3-deep-research");
    }

    #[test]
    fn test_deep_research_config() {
        let config = DeepResearchConfig::new()
            .max_sources(20)
            .include_citations(true);

        assert_eq!(config.max_sources, 20);
        assert!(config.include_citations);
    }

    #[test]
    fn test_realtime_agent_builder() {
        let agent = RealtimeAgent::new()
            .name("VoiceAssistant")
            .voice("nova")
            .build()
            .unwrap();

        assert_eq!(agent.name(), "VoiceAssistant");
        assert_eq!(agent.config.voice, "nova");
    }

    #[test]
    fn test_realtime_config() {
        let config = RealtimeConfig::new()
            .voice("shimmer")
            .temperature(0.7);

        assert_eq!(config.voice, "shimmer");
        assert_eq!(config.temperature, 0.7);
    }
}
