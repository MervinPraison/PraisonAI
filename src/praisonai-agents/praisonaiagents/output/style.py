"""
Output Style for PraisonAI Agents.

Defines output style configurations.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class StylePreset(str, Enum):
    """Predefined output styles."""
    CONCISE = "concise"
    DETAILED = "detailed"
    TECHNICAL = "technical"
    CONVERSATIONAL = "conversational"
    STRUCTURED = "structured"
    MINIMAL = "minimal"


@dataclass
class OutputStyle:
    """
    Output style configuration.
    
    Controls how agent responses are formatted.
    """
    name: str = "default"
    preset: Optional[StylePreset] = None
    
    # Length control
    max_length: Optional[int] = None
    target_length: Optional[int] = None  # Soft target
    
    # Format settings
    format: str = "markdown"  # markdown, plain, json, html
    use_headers: bool = True
    use_lists: bool = True
    use_code_blocks: bool = True
    
    # Tone settings
    tone: str = "professional"  # professional, casual, technical, friendly
    verbosity: str = "normal"  # minimal, normal, verbose
    
    # Content settings
    include_examples: bool = True
    include_explanations: bool = True
    include_caveats: bool = True
    
    # Custom instructions
    custom_instructions: Optional[str] = None
    
    def __post_init__(self):
        if self.preset:
            self._apply_preset(self.preset)
    
    def _apply_preset(self, preset: StylePreset):
        """Apply preset settings."""
        if preset == StylePreset.CONCISE:
            self.verbosity = "minimal"
            self.include_examples = False
            self.include_caveats = False
            self.target_length = 500
        
        elif preset == StylePreset.DETAILED:
            self.verbosity = "verbose"
            self.include_examples = True
            self.include_explanations = True
            self.include_caveats = True
        
        elif preset == StylePreset.TECHNICAL:
            self.tone = "technical"
            self.use_code_blocks = True
            self.include_examples = True
        
        elif preset == StylePreset.CONVERSATIONAL:
            self.tone = "friendly"
            self.use_headers = False
            self.format = "plain"
        
        elif preset == StylePreset.STRUCTURED:
            self.use_headers = True
            self.use_lists = True
            self.format = "markdown"
        
        elif preset == StylePreset.MINIMAL:
            self.verbosity = "minimal"
            self.use_headers = False
            self.use_lists = False
            self.include_examples = False
            self.include_explanations = False
            self.include_caveats = False
            self.target_length = 200
    
    @classmethod
    def concise(cls) -> "OutputStyle":
        """Create a concise style."""
        return cls(name="concise", preset=StylePreset.CONCISE)
    
    @classmethod
    def detailed(cls) -> "OutputStyle":
        """Create a detailed style."""
        return cls(name="detailed", preset=StylePreset.DETAILED)
    
    @classmethod
    def technical(cls) -> "OutputStyle":
        """Create a technical style."""
        return cls(name="technical", preset=StylePreset.TECHNICAL)
    
    @classmethod
    def conversational(cls) -> "OutputStyle":
        """Create a conversational style."""
        return cls(name="conversational", preset=StylePreset.CONVERSATIONAL)
    
    @classmethod
    def structured(cls) -> "OutputStyle":
        """Create a structured style."""
        return cls(name="structured", preset=StylePreset.STRUCTURED)
    
    @classmethod
    def minimal(cls) -> "OutputStyle":
        """Create a minimal style."""
        return cls(name="minimal", preset=StylePreset.MINIMAL)
    
    def get_system_prompt_addition(self) -> str:
        """Generate system prompt addition for this style."""
        parts = []
        
        # Verbosity
        if self.verbosity == "minimal":
            parts.append("Be concise and direct. Avoid unnecessary elaboration.")
        elif self.verbosity == "verbose":
            parts.append("Provide detailed explanations with thorough coverage.")
        
        # Tone
        if self.tone == "technical":
            parts.append("Use technical language appropriate for developers.")
        elif self.tone == "friendly":
            parts.append("Use a friendly, conversational tone.")
        elif self.tone == "casual":
            parts.append("Keep the tone casual and approachable.")
        
        # Format
        if self.format == "markdown":
            parts.append("Format responses using Markdown.")
        elif self.format == "plain":
            parts.append("Use plain text without special formatting.")
        elif self.format == "json":
            parts.append("Return responses as JSON when appropriate.")
        
        # Length
        if self.target_length:
            parts.append(f"Target response length: ~{self.target_length} characters.")
        if self.max_length:
            parts.append(f"Maximum response length: {self.max_length} characters.")
        
        # Content
        if not self.include_examples:
            parts.append("Skip examples unless specifically requested.")
        if not self.include_caveats:
            parts.append("Skip caveats and warnings unless critical.")
        
        # Custom
        if self.custom_instructions:
            parts.append(self.custom_instructions)
        
        return " ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "preset": self.preset.value if self.preset else None,
            "max_length": self.max_length,
            "target_length": self.target_length,
            "format": self.format,
            "tone": self.tone,
            "verbosity": self.verbosity,
            "use_headers": self.use_headers,
            "use_lists": self.use_lists,
            "use_code_blocks": self.use_code_blocks,
            "include_examples": self.include_examples,
            "include_explanations": self.include_explanations,
            "include_caveats": self.include_caveats
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputStyle":
        """Create from dictionary."""
        preset = None
        if data.get("preset"):
            preset = StylePreset(data["preset"])
        
        return cls(
            name=data.get("name", "default"),
            preset=preset,
            max_length=data.get("max_length"),
            target_length=data.get("target_length"),
            format=data.get("format", "markdown"),
            tone=data.get("tone", "professional"),
            verbosity=data.get("verbosity", "normal"),
            use_headers=data.get("use_headers", True),
            use_lists=data.get("use_lists", True),
            use_code_blocks=data.get("use_code_blocks", True),
            include_examples=data.get("include_examples", True),
            include_explanations=data.get("include_explanations", True),
            include_caveats=data.get("include_caveats", True)
        )
