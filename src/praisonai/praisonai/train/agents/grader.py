"""
Training Grader for Agent Training.

Uses LLM-as-judge to grade agent outputs and provide improvement suggestions.
DRY: Reuses the same pattern as praisonaiagents.eval.AccuracyEvaluator.
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
    
    Attributes:
        score: Quality score (1-10)
        reasoning: Explanation for the score
        suggestions: List of improvement suggestions
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


class TrainingGrader:
    """
    Grades agent outputs using LLM-as-judge.
    
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
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.temperature = temperature
    
    def _build_prompt(
        self,
        input_text: str,
        output: str,
        expected_output: Optional[str] = None,
    ) -> str:
        """
        Build the grading prompt.
        
        Args:
            input_text: The input given to the agent
            output: The agent's output to grade
            expected_output: Optional expected output for comparison
            
        Returns:
            The prompt string for the LLM
        """
        prompt = f"""You are an expert evaluator for AI agent outputs. Your task is to grade the quality of an agent's response.

INPUT (what the agent was asked):
{input_text}

AGENT OUTPUT (what the agent responded):
{output}
"""
        
        if expected_output:
            prompt += f"""
EXPECTED OUTPUT (ideal response):
{expected_output}
"""
        
        prompt += """
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
        return prompt
    
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
        # Lazy import litellm to avoid import overhead
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "litellm is required for training grading. "
                "Install with: pip install litellm"
            )
        
        prompt = self._build_prompt(input_text, output, expected_output)
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=500,
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
    
    def _parse_response(
        self,
        response_text: str,
        input_text: str,
        output: str,
        expected_output: Optional[str],
    ) -> GradeResult:
        """
        Parse the LLM response into a GradeResult.
        
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
        suggestions = []
        
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
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "litellm is required for training grading. "
                "Install with: pip install litellm"
            )
        
        prompt = self._build_prompt(input_text, output, expected_output)
        
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=500,
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
