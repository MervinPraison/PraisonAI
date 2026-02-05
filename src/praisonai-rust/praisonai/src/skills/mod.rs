//! Skills Module for PraisonAI Rust SDK.
//!
//! Provides support for the open Agent Skills standard (agentskills.io),
//! enabling agents to load and use modular capabilities through SKILL.md files.
//!
//! # Example
//!
//! ```ignore
//! use praisonai::skills::{SkillManager, SkillProperties};
//!
//! let mut manager = SkillManager::new();
//! manager.discover(&["./skills"]);
//! let prompt_xml = manager.to_prompt();
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

// =============================================================================
// SKILL PROPERTIES
// =============================================================================

/// Properties of a skill parsed from SKILL.md frontmatter.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillProperties {
    /// Skill name (1-64 chars, lowercase, hyphens only)
    pub name: String,
    /// Skill description (1-1024 chars)
    pub description: String,
    /// License (optional)
    pub license: Option<String>,
    /// Compatibility notes (optional)
    pub compatibility: Option<String>,
    /// Allowed tools (space-delimited)
    pub allowed_tools: Option<String>,
    /// Additional metadata
    pub metadata: HashMap<String, String>,
    /// Path to the skill directory
    pub path: Option<PathBuf>,
    /// Instructions (markdown body)
    pub instructions: Option<String>,
}

impl Default for SkillProperties {
    fn default() -> Self {
        Self {
            name: String::new(),
            description: String::new(),
            license: None,
            compatibility: None,
            allowed_tools: None,
            metadata: HashMap::new(),
            path: None,
            instructions: None,
        }
    }
}

impl SkillProperties {
    /// Create a new SkillProperties with name and description.
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            ..Default::default()
        }
    }

    /// Get allowed tools as a vector.
    pub fn get_allowed_tools(&self) -> Vec<&str> {
        self.allowed_tools
            .as_ref()
            .map(|s| s.split_whitespace().collect())
            .unwrap_or_default()
    }

    /// Validate the skill properties.
    pub fn validate(&self) -> Result<(), ValidationError> {
        // Validate name
        if self.name.is_empty() || self.name.len() > 64 {
            return Err(ValidationError::InvalidName(
                "Name must be 1-64 characters".to_string(),
            ));
        }
        if !self.name.chars().all(|c| c.is_lowercase() || c == '-' || c.is_numeric()) {
            return Err(ValidationError::InvalidName(
                "Name must be lowercase with hyphens only".to_string(),
            ));
        }

        // Validate description
        if self.description.is_empty() || self.description.len() > 1024 {
            return Err(ValidationError::InvalidDescription(
                "Description must be 1-1024 characters".to_string(),
            ));
        }

        // Validate compatibility
        if let Some(ref compat) = self.compatibility {
            if compat.len() > 500 {
                return Err(ValidationError::InvalidCompatibility(
                    "Compatibility must be <= 500 characters".to_string(),
                ));
            }
        }

        Ok(())
    }
}

// =============================================================================
// SKILL METADATA
// =============================================================================

/// Metadata about a skill for lightweight loading.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillMetadata {
    /// Skill name
    pub name: String,
    /// Skill description
    pub description: String,
    /// Path to the skill
    pub path: PathBuf,
    /// Estimated token count for metadata
    pub token_estimate: usize,
}

impl SkillMetadata {
    /// Create from SkillProperties.
    pub fn from_properties(props: &SkillProperties) -> Option<Self> {
        props.path.as_ref().map(|path| Self {
            name: props.name.clone(),
            description: props.description.clone(),
            path: path.clone(),
            token_estimate: (props.name.len() + props.description.len()) / 4,
        })
    }
}

// =============================================================================
// ERRORS
// =============================================================================

/// Error during skill parsing.
#[derive(Debug, Clone)]
pub struct ParseError {
    pub message: String,
    pub line: Option<usize>,
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self.line {
            Some(line) => write!(f, "Parse error at line {}: {}", line, self.message),
            None => write!(f, "Parse error: {}", self.message),
        }
    }
}

impl std::error::Error for ParseError {}

/// Error during skill validation.
#[derive(Debug, Clone)]
pub enum ValidationError {
    InvalidName(String),
    InvalidDescription(String),
    InvalidCompatibility(String),
    MissingRequired(String),
}

impl std::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ValidationError::InvalidName(msg) => write!(f, "Invalid name: {}", msg),
            ValidationError::InvalidDescription(msg) => write!(f, "Invalid description: {}", msg),
            ValidationError::InvalidCompatibility(msg) => write!(f, "Invalid compatibility: {}", msg),
            ValidationError::MissingRequired(msg) => write!(f, "Missing required field: {}", msg),
        }
    }
}

impl std::error::Error for ValidationError {}

// =============================================================================
// SKILL LOADER
// =============================================================================

/// Loader for progressive skill loading.
#[derive(Debug, Default)]
pub struct SkillLoader {
    /// Loaded skills by name
    skills: HashMap<String, SkillProperties>,
    /// Metadata cache (Level 1)
    metadata_cache: HashMap<String, SkillMetadata>,
}

impl SkillLoader {
    /// Create a new loader.
    pub fn new() -> Self {
        Self::default()
    }

    /// Load skill metadata (Level 1 - lightweight).
    pub fn load_metadata(&mut self, path: &Path) -> Result<SkillMetadata, ParseError> {
        let skill_md = path.join("SKILL.md");
        if !skill_md.exists() {
            return Err(ParseError {
                message: format!("SKILL.md not found in {:?}", path),
                line: None,
            });
        }

        let content = std::fs::read_to_string(&skill_md).map_err(|e| ParseError {
            message: e.to_string(),
            line: None,
        })?;

        let props = self.parse_frontmatter(&content)?;
        let mut props = props;
        props.path = Some(path.to_path_buf());

        let metadata = SkillMetadata::from_properties(&props).ok_or_else(|| ParseError {
            message: "Failed to create metadata".to_string(),
            line: None,
        })?;

        self.metadata_cache.insert(props.name.clone(), metadata.clone());
        Ok(metadata)
    }

    /// Load full skill (Level 2 - instructions).
    pub fn load_full(&mut self, name: &str) -> Result<&SkillProperties, ParseError> {
        if self.skills.contains_key(name) {
            return Ok(self.skills.get(name).unwrap());
        }

        let metadata = self.metadata_cache.get(name).ok_or_else(|| ParseError {
            message: format!("Skill '{}' not found in cache", name),
            line: None,
        })?;

        let skill_md = metadata.path.join("SKILL.md");
        let content = std::fs::read_to_string(&skill_md).map_err(|e| ParseError {
            message: e.to_string(),
            line: None,
        })?;

        let mut props = self.parse_frontmatter(&content)?;
        props.path = Some(metadata.path.clone());
        props.instructions = self.parse_body(&content);

        self.skills.insert(name.to_string(), props);
        Ok(self.skills.get(name).unwrap())
    }

    /// Parse YAML frontmatter from SKILL.md content.
    fn parse_frontmatter(&self, content: &str) -> Result<SkillProperties, ParseError> {
        let lines: Vec<&str> = content.lines().collect();
        
        if lines.is_empty() || lines[0].trim() != "---" {
            return Err(ParseError {
                message: "Missing frontmatter delimiter".to_string(),
                line: Some(1),
            });
        }

        let mut end_idx = None;
        for (i, line) in lines.iter().enumerate().skip(1) {
            if line.trim() == "---" {
                end_idx = Some(i);
                break;
            }
        }

        let end_idx = end_idx.ok_or_else(|| ParseError {
            message: "Missing closing frontmatter delimiter".to_string(),
            line: None,
        })?;

        let yaml_content = lines[1..end_idx].join("\n");
        
        serde_yaml::from_str(&yaml_content).map_err(|e| ParseError {
            message: e.to_string(),
            line: None,
        })
    }

    /// Parse markdown body from SKILL.md content.
    fn parse_body(&self, content: &str) -> Option<String> {
        let lines: Vec<&str> = content.lines().collect();
        
        let mut in_frontmatter = false;
        let mut body_start = 0;

        for (i, line) in lines.iter().enumerate() {
            if line.trim() == "---" {
                if !in_frontmatter {
                    in_frontmatter = true;
                } else {
                    body_start = i + 1;
                    break;
                }
            }
        }

        if body_start < lines.len() {
            let body = lines[body_start..].join("\n").trim().to_string();
            if !body.is_empty() {
                return Some(body);
            }
        }

        None
    }

    /// Get loaded skill count.
    pub fn skill_count(&self) -> usize {
        self.skills.len()
    }

    /// Get metadata count.
    pub fn metadata_count(&self) -> usize {
        self.metadata_cache.len()
    }
}

// =============================================================================
// SKILL MANAGER
// =============================================================================

/// Manager for discovering and using skills.
#[derive(Debug, Default)]
pub struct SkillManager {
    /// Skill loader
    loader: SkillLoader,
    /// Discovered skill directories
    skill_dirs: Vec<PathBuf>,
}

impl SkillManager {
    /// Create a new manager.
    pub fn new() -> Self {
        Self::default()
    }

    /// Discover skills in the given directories.
    pub fn discover(&mut self, dirs: &[impl AsRef<Path>]) -> Vec<SkillMetadata> {
        let mut discovered = Vec::new();

        for dir in dirs {
            let dir = dir.as_ref();
            if !dir.exists() {
                continue;
            }

            self.skill_dirs.push(dir.to_path_buf());

            // Look for subdirectories with SKILL.md
            if let Ok(entries) = std::fs::read_dir(dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_dir() && path.join("SKILL.md").exists() {
                        if let Ok(metadata) = self.loader.load_metadata(&path) {
                            discovered.push(metadata);
                        }
                    }
                }
            }
        }

        discovered
    }

    /// Get default skill directories.
    pub fn get_default_dirs() -> Vec<PathBuf> {
        let mut dirs = Vec::new();

        // Project-level
        dirs.push(PathBuf::from("./.praison/skills"));
        dirs.push(PathBuf::from("./.claude/skills"));

        // User-level
        if let Some(home) = dirs::home_dir() {
            dirs.push(home.join(".praison/skills"));
        }

        dirs
    }

    /// Load a skill by name.
    pub fn load(&mut self, name: &str) -> Result<&SkillProperties, ParseError> {
        self.loader.load_full(name)
    }

    /// Generate XML prompt for all discovered skills.
    pub fn to_prompt(&self) -> String {
        let mut xml = String::from("<skills>\n");

        for metadata in self.loader.metadata_cache.values() {
            xml.push_str(&format!(
                "  <skill name=\"{}\">\n    <description>{}</description>\n  </skill>\n",
                metadata.name, metadata.description
            ));
        }

        xml.push_str("</skills>");
        xml
    }

    /// Get skill count.
    pub fn skill_count(&self) -> usize {
        self.loader.metadata_count()
    }

    /// List all discovered skill names.
    pub fn list_skills(&self) -> Vec<&str> {
        self.loader.metadata_cache.keys().map(|s| s.as_str()).collect()
    }
}

/// Generate skills XML for prompt.
pub fn generate_skills_xml(skills: &[SkillProperties]) -> String {
    let mut xml = String::from("<skills>\n");

    for skill in skills {
        xml.push_str(&format!(
            "  <skill name=\"{}\">\n    <description>{}</description>\n",
            skill.name, skill.description
        ));
        if let Some(ref instructions) = skill.instructions {
            xml.push_str(&format!("    <instructions>{}</instructions>\n", instructions));
        }
        xml.push_str("  </skill>\n");
    }

    xml.push_str("</skills>");
    xml
}

/// Format a single skill for prompt.
pub fn format_skill_for_prompt(skill: &SkillProperties) -> String {
    let mut output = format!("# {}\n\n{}\n", skill.name, skill.description);
    
    if let Some(ref instructions) = skill.instructions {
        output.push_str(&format!("\n## Instructions\n\n{}\n", instructions));
    }

    output
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_skill_properties_new() {
        let props = SkillProperties::new("my-skill", "A test skill");
        assert_eq!(props.name, "my-skill");
        assert_eq!(props.description, "A test skill");
    }

    #[test]
    fn test_skill_properties_validate() {
        let props = SkillProperties::new("my-skill", "A test skill");
        assert!(props.validate().is_ok());
    }

    #[test]
    fn test_skill_properties_validate_invalid_name() {
        let props = SkillProperties::new("My Skill", "A test skill");
        assert!(props.validate().is_err());
    }

    #[test]
    fn test_skill_properties_validate_empty_name() {
        let props = SkillProperties::new("", "A test skill");
        assert!(props.validate().is_err());
    }

    #[test]
    fn test_skill_properties_get_allowed_tools() {
        let mut props = SkillProperties::new("my-skill", "A test skill");
        props.allowed_tools = Some("Read Grep Search".to_string());
        
        let tools = props.get_allowed_tools();
        assert_eq!(tools, vec!["Read", "Grep", "Search"]);
    }

    #[test]
    fn test_skill_metadata_from_properties() {
        let mut props = SkillProperties::new("my-skill", "A test skill");
        props.path = Some(PathBuf::from("/path/to/skill"));
        
        let metadata = SkillMetadata::from_properties(&props).unwrap();
        assert_eq!(metadata.name, "my-skill");
        assert_eq!(metadata.path, PathBuf::from("/path/to/skill"));
    }

    #[test]
    fn test_skill_manager_new() {
        let manager = SkillManager::new();
        assert_eq!(manager.skill_count(), 0);
    }

    #[test]
    fn test_generate_skills_xml() {
        let skills = vec![
            SkillProperties::new("skill-1", "First skill"),
            SkillProperties::new("skill-2", "Second skill"),
        ];
        
        let xml = generate_skills_xml(&skills);
        assert!(xml.contains("<skills>"));
        assert!(xml.contains("skill-1"));
        assert!(xml.contains("skill-2"));
        assert!(xml.contains("</skills>"));
    }

    #[test]
    fn test_format_skill_for_prompt() {
        let mut skill = SkillProperties::new("my-skill", "A test skill");
        skill.instructions = Some("Do something useful".to_string());
        
        let output = format_skill_for_prompt(&skill);
        assert!(output.contains("# my-skill"));
        assert!(output.contains("A test skill"));
        assert!(output.contains("Do something useful"));
    }

    #[test]
    fn test_skill_loader_new() {
        let loader = SkillLoader::new();
        assert_eq!(loader.skill_count(), 0);
        assert_eq!(loader.metadata_count(), 0);
    }

    #[test]
    fn test_get_default_dirs() {
        let dirs = SkillManager::get_default_dirs();
        assert!(!dirs.is_empty());
        assert!(dirs.iter().any(|d| d.to_string_lossy().contains("praison")));
    }
}
