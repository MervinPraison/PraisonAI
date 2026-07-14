"""
Training Grader for Agent Training.

Uses LLM-as-judge to grade agent outputs and provide improvement suggestions.

DRY: This module now inherits from praisonaiagents.eval.grader.BaseLLMGrader
to share common prompt building and response parsing logic.
"""

import logging
from typing import Optional

# DRY: Import base grader and result from praisonaiagents
from praisonaiagents.eval.grader import BaseLLMGrader, GradeResult

logger = logging.getLogger(__name__)

# Re-export GradeResult for backward compatibility
__all__ = ['GradeResult', 'TrainingGrader']


class TrainingGrader(BaseLLMGrader):
    """
    Grades agent outputs using LLM-as-judge.
    
    DRY: Inherits from BaseLLMGrader which provides common:
    - Prompt building (_build_prompt)
    - Response parsing (_parse_response)
    - Lazy litellm import (_get_litellm)
    - Sync and async grading (grade, grade_async)
    
    Uses an LLM to evaluate the quality of agent outputs and provide
    improvement suggestions. This enables automated training without
    human intervention.
    
    Usage:
        grader = TrainingGrader()
        result = grader.grade(
            input_text="What is Python?",
            output="Python is a programming language",
            expected_output="Python is a high-level programming language"
        )
        print(f"Score: {result.score}/10")
        print(f"Suggestions: {result.suggestions}")
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        """
        Initialize the grader.
        
        Args:
            model: LLM model to use for grading (default: gpt-4o-mini)
            temperature: Temperature for LLM calls (default: 0.1 for consistency)
        """
        # DRY: Use parent class initialization
        super().__init__(model=model, temperature=temperature, max_tokens=500)
    
    # All methods (grade, grade_async, _build_prompt, _parse_response)
    # are inherited from BaseLLMGrader - no duplication needed!
