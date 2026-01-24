"""
Judge Plan Module for PraisonAI.

Provides structured, actionable fix recommendations similar to Terraform's plan/apply pattern.

Features:
- ActionableFix: Specific, targeted fixes with file paths and values
- JudgePlan: Collection of fixes to apply
- Plan serialization to YAML/JSON for review before applying

Usage:
    from praisonai.replay import JudgePlan, ActionableFix
    
    # Generate plan from judge report
    plan = JudgePlan.from_judge_report(report, yaml_file="agents.yaml")
    
    # Save plan for review
    plan.save("judge_plan.yaml")
    
    # Apply plan
    from praisonai.replay import PlanApplier
    applier = PlanApplier(plan)
    applier.apply()
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path


@dataclass
class ActionableFix:
    """
    A specific, actionable fix recommendation.
    
    Represents a single change to be made to a YAML file.
    """
    fix_id: str                         # Unique ID for this fix
    agent_name: str                     # Which agent to fix
    fix_type: str                       # Type of fix (see FIX_TYPES)
    target_path: str                    # YAML path: "steps.0.agent.instructions"
    current_value: Optional[str]        # Current value (for context)
    suggested_value: str                # New value to apply
    reasoning: str                      # Why this fix helps
    confidence: float                   # 0.0-1.0 confidence score
    priority: str                       # "high", "medium", "low"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionableFix":
        """Create from dictionary."""
        return cls(**data)


# Valid fix types
FIX_TYPES = {
    "replace_instruction": "Replace agent instructions for clarity or completeness",
    "add_expected_output": "Add or modify expected_output field",
    "modify_context_config": "Adjust context management settings",
    "add_validation": "Add output validation or schema",
    "modify_tool_config": "Adjust tool configuration",
    "add_goal": "Add goal field to workflow",
    "modify_step_order": "Reorder workflow steps",
    "add_retry_config": "Add retry/error handling configuration",
}


@dataclass
class JudgePlan:
    """
    A plan of fixes to apply (like terraform plan).
    
    Contains all the fixes recommended by the judge, ready for review and application.
    """
    trace_id: str
    yaml_file: str
    goal: Optional[str]                 # Extracted from YAML or inferred
    overall_score: float
    fixes: List[ActionableFix] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    applied: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "yaml_file": self.yaml_file,
            "goal": self.goal,
            "overall_score": self.overall_score,
            "fixes": [f.to_dict() for f in self.fixes],
            "created_at": self.created_at,
            "applied": self.applied,
            "summary": {
                "total_fixes": len(self.fixes),
                "high_priority": len([f for f in self.fixes if f.priority == "high"]),
                "medium_priority": len([f for f in self.fixes if f.priority == "medium"]),
                "low_priority": len([f for f in self.fixes if f.priority == "low"]),
            }
        }
    
    def to_yaml(self) -> str:
        """Convert to YAML string."""
        try:
            import yaml
            return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False, allow_unicode=True)
        except ImportError:
            # Fallback to JSON if yaml not available
            return json.dumps(self.to_dict(), indent=2)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def save(self, filepath: str) -> None:
        """Save plan to file."""
        path = Path(filepath)
        content = self.to_yaml() if path.suffix in [".yaml", ".yml"] else self.to_json()
        path.write_text(content)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JudgePlan":
        """Create from dictionary."""
        fixes = [ActionableFix.from_dict(f) for f in data.get("fixes", [])]
        return cls(
            trace_id=data["trace_id"],
            yaml_file=data["yaml_file"],
            goal=data.get("goal"),
            overall_score=data["overall_score"],
            fixes=fixes,
            created_at=data.get("created_at", datetime.now().isoformat()),
            applied=data.get("applied", False),
        )
    
    @classmethod
    def load(cls, filepath: str) -> "JudgePlan":
        """Load plan from file."""
        path = Path(filepath)
        content = path.read_text()
        
        if path.suffix in [".yaml", ".yml"]:
            try:
                import yaml
                data = yaml.safe_load(content)
            except ImportError:
                data = json.loads(content)
        else:
            data = json.loads(content)
        
        return cls.from_dict(data)
    
    def get_fixes_by_priority(self, priority: str) -> List[ActionableFix]:
        """Get fixes filtered by priority."""
        return [f for f in self.fixes if f.priority == priority]
    
    def get_fixes_by_agent(self, agent_name: str) -> List[ActionableFix]:
        """Get fixes for a specific agent."""
        return [f for f in self.fixes if f.agent_name == agent_name]
    
    def format_summary(self) -> str:
        """Format a human-readable summary of the plan."""
        lines = [
            "=" * 60,
            f"  JUDGE PLAN: {self.trace_id}",
            "=" * 60,
            f"  YAML File: {self.yaml_file}",
            f"  Overall Score: {self.overall_score}/10",
            f"  Goal: {self.goal or 'Not specified'}",
            f"  Created: {self.created_at}",
            "",
            f"  FIXES TO APPLY: {len(self.fixes)}",
        ]
        
        # Group by priority
        for priority in ["high", "medium", "low"]:
            priority_fixes = self.get_fixes_by_priority(priority)
            if priority_fixes:
                lines.append(f"\n  [{priority.upper()} PRIORITY] ({len(priority_fixes)} fixes)")
                for fix in priority_fixes:
                    lines.append(f"    • {fix.fix_id}: {fix.agent_name}")
                    lines.append(f"      Type: {fix.fix_type}")
                    lines.append(f"      Path: {fix.target_path}")
                    lines.append(f"      Reasoning: {fix.reasoning[:80]}...")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)


def generate_fix_id(agent_name: str, fix_type: str, target_path: str) -> str:
    """Generate a unique fix ID."""
    content = f"{agent_name}:{fix_type}:{target_path}"
    hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"fix_{hash_suffix}"
