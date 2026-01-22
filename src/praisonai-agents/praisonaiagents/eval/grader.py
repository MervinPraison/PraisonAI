"""
Base LLM Grader for PraisonAI Agents.

Provides a common base class for LLM-as-judge grading to eliminate duplication
across AccuracyEvaluator, CriteriaEvaluator, and TrainingGrader.

DRY: This module extracts the common prompt building and response parsing logic
that was duplicated across multiple evaluators.
"""

import os
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GradeResult:
    """
    Result from grading an agent output.
    
    This is the common result type used by all graders.
    
    Attributes:
        score: Quality score (1-10)
        reasoning: Explanation for the score
        suggestions: List of improvement suggestions (optional)
        input_text: The input that was given
        output: The output that was graded
        expected_output: Optional expected output
        timestamp: When grading occurred
    """
    score: float
    reasoning: str
    suggestions: List[str] = field(default_factory=list)
    input_text: str = ""
    output: str = ""
    expected_output: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GradeResult":
        """Create from dictionary."""
        return cls(
            score=data.get("score", 5.0),
            reasoning=data.get("reasoning", ""),
            suggestions=data.get("suggestions", []),
            input_text=data.get("input_text", ""),
            output=data.get("output", ""),
            expected_output=data.get("expected_output"),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
        )


class BaseLLMGrader:
    """
    Base class for LLM-as-judge grading.
    
    Provides common functionality for:
    - Building grading prompts
    - Parsing LLM responses (SCORE/REASONING/SUGGESTIONS format)
    - Lazy litellm import
    - Sync and async grading
    
    Subclasses can override:
    - _build_prompt() for custom prompt templates
    - _parse_response() for custom response parsing
    
    Usage:
        grader = BaseLLMGrader()
        result = grader.grade(
            input_text="What is Python?",
            output="Python is a programming language",
            expected_output="Python is a high-level programming language"
        )
        print(f"Score: {result.score}/10")
    """
    
    # Default prompt template - can be overridden by subclasses
    PROMPT_TEMPLATE = """You are an expert evaluator for AI agent outputs. Your task is to grade the quality of an agent's response.

INPUT (what the agent was asked):
{input_text}

AGENT OUTPUT (what the agent responded):
{output}
{expected_section}
GRADING CRITERIA:
- Accuracy: Is the response factually correct?
- Completeness: Does it fully address the input?
- Clarity: Is it well-written and easy to understand?
- Relevance: Does it stay on topic?

SCORING GUIDELINES:
- 10: Perfect - Excellent in all criteria
- 8-9: Very Good - Minor improvements possible
- 6-7: Good - Some issues but mostly correct
- 4-5: Fair - Significant issues
- 2-3: Poor - Major problems
- 1: Very Poor - Completely wrong or irrelevant

Respond in this EXACT format:
SCORE: [number 1-10]
REASONING: [brief explanation of the score]
SUGGESTIONS:
- [first suggestion for improvement]
- [second suggestion if applicable]
- [third suggestion if applicable]

If no suggestions are needed, write "SUGGESTIONS: None"
"""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 500,
    ):
        """
        Initialize the grader.
        
        Args:
            model: LLM model to use for grading (default: gpt-4o-mini)
            temperature: Temperature for LLM calls (default: 0.1 for consistency)
            max_tokens: Maximum tokens for LLM response
        """
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    def _build_prompt(
        self,
        input_text: str,
        output: str,
        expected_output: Optional[str] = None,
    ) -> str:
        """
        Build the grading prompt.
        
        Override this method in subclasses for custom prompt templates.
        
        Args:
            input_text: The input given to the agent
            output: The agent's output to grade
            expected_output: Optional expected output for comparison
            
        Returns:
            The prompt string for the LLM
        """
        expected_section = ""
        if expected_output:
            expected_section = f"""
EXPECTED OUTPUT (ideal response):
{expected_output}
"""
        
        return self.PROMPT_TEMPLATE.format(
            input_text=input_text,
            output=output,
            expected_section=expected_section,
        )
    
    def _parse_response(
        self,
        response_text: str,
        input_text: str,
        output: str,
        expected_output: Optional[str],
    ) -> GradeResult:
        """
        Parse the LLM response into a GradeResult.
        
        Override this method in subclasses for custom parsing logic.
        
        Args:
            response_text: Raw LLM response
            input_text: Original input
            output: Original output
            expected_output: Original expected output
            
        Returns:
            Parsed GradeResult
        """
        score = 5.0  # Default
        reasoning = "Unable to parse response"
        suggestions: List[str] = []
        
        lines = response_text.strip().split('\n')
        in_suggestions = False
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('SCORE:'):
                try:
                    score_str = line.replace('SCORE:', '').strip()
                    score = float(score_str)
                    # Clamp to valid range
                    score = max(1.0, min(10.0, score))
                except ValueError:
                    pass
            
            elif line.startswith('REASONING:'):
                reasoning = line.replace('REASONING:', '').strip()
            
            elif line.startswith('SUGGESTIONS:'):
                in_suggestions = True
                rest = line.replace('SUGGESTIONS:', '').strip()
                if rest.lower() != 'none' and rest:
                    suggestions.append(rest)
            
            elif in_suggestions and line.startswith('-'):
                suggestion = line.lstrip('- ').strip()
                if suggestion and suggestion.lower() != 'none':
                    suggestions.append(suggestion)
        
        return GradeResult(
            score=score,
            reasoning=reasoning,
            suggestions=suggestions,
            input_text=input_text,
            output=output,
            expected_output=expected_output,
        )
    
    def _get_litellm(self):
        """
        Lazy import litellm.
        
        Returns:
            The litellm module
            
        Raises:
            ImportError: If litellm is not installed
        """
        try:
            import litellm
            return litellm
        except ImportError:
            raise ImportError(
                "litellm is required for LLM grading. "
                "Install with: pip install litellm"
            )
    
    def grade(
        self,
        input_text: str,
        output: str,
        expected_output: Optional[str] = None,
    ) -> GradeResult:
        """
        Grade an agent output.
        
        Args:
            input_text: The input given to the agent
            output: The agent's output to grade
            expected_output: Optional expected output for comparison
            
        Returns:
            GradeResult with score, reasoning, and suggestions
        """
        litellm = self._get_litellm()
        
        prompt = self._build_prompt(input_text, output, expected_output)
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            response_text = response.choices[0].message.content or ""
            return self._parse_response(response_text, input_text, output, expected_output)
            
        except Exception as e:
            logger.warning(f"Grading failed: {e}")
            return GradeResult(
                score=5.0,
                reasoning=f"Grading error: {str(e)}",
                suggestions=[],
                input_text=input_text,
                output=output,
                expected_output=expected_output,
            )
    
    async def grade_async(
        self,
        input_text: str,
        output: str,
        expected_output: Optional[str] = None,
    ) -> GradeResult:
        """
        Grade an agent output asynchronously.
        
        Args:
            input_text: The input given to the agent
            output: The agent's output to grade
            expected_output: Optional expected output for comparison
            
        Returns:
            GradeResult with score, reasoning, and suggestions
        """
        litellm = self._get_litellm()
        
        prompt = self._build_prompt(input_text, output, expected_output)
        
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            response_text = response.choices[0].message.content or ""
            return self._parse_response(response_text, input_text, output, expected_output)
            
        except Exception as e:
            logger.warning(f"Async grading failed: {e}")
            return GradeResult(
                score=5.0,
                reasoning=f"Grading error: {str(e)}",
                suggestions=[],
                input_text=input_text,
                output=output,
                expected_output=expected_output,
            )


def parse_score_reasoning(response_text: str) -> tuple:
    """
    Parse SCORE and REASONING from LLM response.
    
    DRY: Static utility function for parsing LLM-as-judge responses.
    Used by AccuracyEvaluator, CriteriaEvaluator, and BaseLLMGrader.
    
    Args:
        response_text: Raw LLM response text
        
    Returns:
        Tuple of (score: float, reasoning: str)
    """
    score = 5.0  # Default
    reasoning = "Unable to parse response"
    
    lines = response_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        
        if line.startswith('SCORE:'):
            try:
                score_str = line.replace('SCORE:', '').strip()
                score = float(score_str)
                # Clamp to valid range
                score = max(1.0, min(10.0, score))
            except ValueError:
                pass
        
        elif line.startswith('REASONING:'):
            reasoning = line.replace('REASONING:', '').strip()
    
    return score, reasoning


__all__ = [
    'GradeResult',
    'BaseLLMGrader',
    'parse_score_reasoning',
]
