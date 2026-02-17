"""
Policy Configuration for PraisonAI Agents.

Extends the policy engine with learning capabilities:
- ``learn=True`` auto-persists "always allow" decisions
- ``rules=`` inline rules for static policy
- ``rules_file=`` path to persistent rules file
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict

logger = logging.getLogger(__name__)

# Default rules file path (follows ~/.praisonai/ convention)
DEFAULT_RULES_DIR = os.path.join(os.path.expanduser("~"), ".praisonai", "rules")
DEFAULT_RULES_FILE = os.path.join(DEFAULT_RULES_DIR, "default.rules")


@dataclass
class PolicyConfig:
    """Configuration for the policy engine.
    
    Follows PraisonAI's ``False/True/Config`` progressive-disclosure pattern:
    
    - ``policy=False`` — disabled (no policy checks)
    - ``policy=True`` — enabled with defaults
    - ``policy=PolicyConfig(...)`` — full control
    
    Attributes:
        enabled: Whether policy evaluation is enabled.
        default_action: Action when no rule matches ("allow" or "deny").
        log_decisions: Whether to log policy decisions.
        strict_mode: If True, deny when no policy matches.
        learn: When True, auto-persist user "always allow" decisions to
            ``rules_file``. Only writes when user explicitly approves.
        rules: Inline list of rule dicts or PolicyRule objects for static
            policy. Each dict should have at minimum ``resource`` and ``action``.
        rules_file: Path to persistent rules file. Defaults to
            ``~/.praisonai/rules/default.rules``.
    
    Usage::
    
        # Simple — learn from user decisions
        Agent(policy=PolicyConfig(learn=True))
        
        # With inline rules
        Agent(policy=PolicyConfig(
            rules=[
                {"resource": "tool:pip *", "action": "allow"},
                {"resource": "tool:rm *", "action": "deny"},
            ],
        ))
    """
    enabled: bool = True
    default_action: str = "allow"  # Default action when no policy matches
    log_decisions: bool = True
    strict_mode: bool = False  # If True, deny when no policy matches
    # G-1: Learning and persistence
    learn: bool = False
    rules: Optional[List[Any]] = None  # List of rule dicts or PolicyRule objects
    rules_file: Optional[str] = None  # Defaults to ~/.praisonai/rules/default.rules
    
    def __post_init__(self):
        if self.rules_file is None:
            self.rules_file = DEFAULT_RULES_FILE
    
    def load_learned_rules(self) -> List[Dict[str, str]]:
        """Load previously learned rules from the rules file.
        
        Returns:
            List of rule dicts with 'resource' and 'action' keys.
        """
        if not self.rules_file or not os.path.exists(self.rules_file):
            return []
        try:
            with open(self.rules_file, "r") as f:
                data = json.load(f)
            return data.get("rules", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Failed to load rules from {self.rules_file}: {e}")
            return []
    
    def save_learned_rule(self, resource: str, action: str = "allow") -> bool:
        """Persist a learned rule to the rules file.
        
        Uses atomic write (tmp + rename) for safety.
        
        Args:
            resource: Resource pattern (e.g., "tool:pip install *")
            action: Action to take ("allow" or "deny")
            
        Returns:
            True if saved successfully.
        """
        if not self.rules_file:
            return False
        
        try:
            # Load existing rules
            existing = self.load_learned_rules()
            
            # Check for duplicates
            for rule in existing:
                if rule.get("resource") == resource:
                    return True  # Already exists
            
            # Add new rule
            existing.append({"resource": resource, "action": action})
            
            # Ensure directory exists
            rules_dir = os.path.dirname(self.rules_file)
            os.makedirs(rules_dir, exist_ok=True)
            
            # Atomic write: tmp file + rename
            tmp_file = self.rules_file + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump({"rules": existing}, f, indent=2)
            os.replace(tmp_file, self.rules_file)
            
            logger.debug(f"Saved learned rule: {resource} -> {action}")
            return True
        except OSError as e:
            logger.debug(f"Failed to save rule: {e}")
            return False
    
    def get_all_rules(self) -> List[Dict[str, str]]:
        """Get all rules: inline + learned from file.
        
        Returns:
            Combined list of rule dicts.
        """
        result = []
        
        # Add inline rules
        if self.rules:
            for rule in self.rules:
                if isinstance(rule, dict):
                    result.append(rule)
                elif hasattr(rule, "to_dict"):
                    result.append(rule.to_dict())
        
        # Add learned rules from file
        if self.learn:
            result.extend(self.load_learned_rules())
        
        return result

