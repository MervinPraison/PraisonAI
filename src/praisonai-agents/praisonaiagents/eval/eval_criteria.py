"""
Evaluation criteria for the PraisonAI evaluation framework.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class EvalCriteria:
    """Criteria for multi-dimensional evaluation."""
    
    factual_accuracy: float = 0.4
    completeness: float = 0.3
    relevance: float = 0.3
    
    def __post_init__(self):
        """Validate that weights sum to 1.0."""
        total = self.factual_accuracy + self.completeness + self.relevance
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Criteria weights must sum to 1.0, got {total}")
    
    @property
    def weights(self) -> Dict[str, float]:
        """Get criteria weights as dictionary."""
        return {
            'factual_accuracy': self.factual_accuracy,
            'completeness': self.completeness,
            'relevance': self.relevance
        }
    
    def calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted score from individual criteria scores."""
        total_score = 0.0
        for criterion, weight in self.weights.items():
            if criterion in scores:
                total_score += scores[criterion] * weight
        return total_score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'factual_accuracy': self.factual_accuracy,
            'completeness': self.completeness,
            'relevance': self.relevance
        }