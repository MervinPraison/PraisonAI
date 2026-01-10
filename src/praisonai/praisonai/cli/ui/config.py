"""
UI Configuration for PraisonAI CLI.

Provides unified configuration for all UI backends.
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class UIConfig:
    """Configuration for UI backends."""
    
    # Backend selection
    ui_backend: str = 'auto'  # auto, plain, rich, mg
    
    # Output modes
    json_output: bool = False
    compact: bool = False
    verbose: bool = False
    
    # Styling
    no_color: bool = False
    no_unicode: bool = False
    theme: str = 'default'
    
    # Behavior
    no_fullscreen: bool = False
    
    # Additional settings
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_cli_args(cls, **kwargs) -> 'UIConfig':
        """Create UIConfig from CLI arguments."""
        return cls(
            ui_backend=kwargs.get('ui', 'auto'),
            json_output=kwargs.get('json', False),
            compact=kwargs.get('compact', False),
            verbose=kwargs.get('verbose', False),
            no_color=kwargs.get('no_color', False),
            no_unicode=kwargs.get('no_unicode', False),
            theme=kwargs.get('theme', 'default'),
            no_fullscreen=kwargs.get('no_fullscreen', False),
        )
