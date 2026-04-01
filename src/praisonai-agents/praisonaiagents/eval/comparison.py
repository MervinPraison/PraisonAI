"""
ComparisonEval - Side-by-side comparison of two agent outputs.

This module provides evaluation capabilities for comparing two different outputs
or agents against the same input, useful for A/B testing and performance comparison.

Example:
    from praisonaiagents import Agent
    from praisonaiagents.eval import ComparisonEval
    
    agent_a = Agent(name="agent_a", instructions="Be concise")
    agent_b = Agent(name="agent_b", instructions="Be detailed")
    
    evaluator = ComparisonEval(
        input_text="Explain machine learning",
        agent_a=agent_a,
        agent_b=agent_b,
        criteria=["accuracy", "clarity", "conciseness"]
    )
    
    result = evaluator.run()
    print(f"Winner: {result.winner}")  # "agent_a", "agent_b", or "tie"
"""

from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass
import time
from praisonaiagents._logging import get_logger
from .base import BaseEvaluator
from .grader import BaseLLMGrader, parse_score_reasoning

if TYPE_CHECKING:
    from ..agent.agent import Agent

logger = get_logger(__name__)

@dataclass
class ComparisonResult:
    """Result container for comparison evaluations."""
    
    input_text: str
    output_a: str
    output_b: str
    agent_a_name: str
    agent_b_name: str
    criteria: List[str]
    scores: Dict[str, Dict[str, float]]  # {criterion: {agent_a: score, agent_b: score}}
    reasoning: Dict[str, str]  # {criterion: reasoning}
    winner: str  # "agent_a", "agent_b", or "tie"
    overall_score_a: float
    overall_score_b: float
    confidence: float
    duration: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "input_text": self.input_text,
            "outputs": {
                self.agent_a_name: self.output_a,
                self.agent_b_name: self.output_b
            },
            "criteria": self.criteria,
            "scores": self.scores,
            "reasoning": self.reasoning,
            "winner": self.winner,
            "overall_scores": {
                self.agent_a_name: self.overall_score_a,
                self.agent_b_name: self.overall_score_b
            },
            "confidence": self.confidence,
            "duration": self.duration
        }

class ComparisonGrader(BaseLLMGrader):
    """LLM grader for comparing two outputs side-by-side."""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ):
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
    
    def compare_outputs(
        self,
        input_text: str,
        output_a: str,
        output_b: str,
        agent_a_name: str,
        agent_b_name: str,
        criteria: List[str]
    ) -> Dict[str, Any]:
        """
        Compare two outputs across multiple criteria.
        
        Returns:
            Dict with scores and reasoning for each criterion
        """
        criteria_str = ", ".join(criteria)
        
        system_prompt = f"""You are an expert evaluator comparing two AI agent outputs.

TASK: Compare Output A and Output B across these criteria: {criteria_str}

SCORING:
- Rate each output from 1-10 for each criterion
- Provide clear reasoning for scores
- Determine overall winner

RESPONSE FORMAT:
For each criterion, provide:
Criterion: [criterion_name]
Output A Score: [1-10]
Output B Score: [1-10]
Reasoning: [detailed explanation]

Final Assessment:
Overall Winner: [A/B/Tie]
Confidence: [1-10]
Summary: [brief explanation of decision]"""

        user_prompt = f"""INPUT: {input_text}

OUTPUT A ({agent_a_name}):
{output_a}

OUTPUT B ({agent_b_name}):
{output_b}

Please evaluate these outputs across the specified criteria."""

        try:
            response = self._make_llm_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            return self._parse_comparison_response(response, criteria, agent_a_name, agent_b_name)
            
        except Exception as e:
            logger.error(f"Comparison grading failed: {e}")
            # Return default scores
            return {
                "scores": {criterion: {agent_a_name: 5.0, agent_b_name: 5.0} for criterion in criteria},
                "reasoning": {criterion: f"Error during evaluation: {e}" for criterion in criteria},
                "winner": "tie",
                "confidence": 1.0,
                "summary": f"Evaluation failed: {e}"
            }
    
    def _parse_comparison_response(
        self, 
        response: str, 
        criteria: List[str],
        agent_a_name: str,
        agent_b_name: str
    ) -> Dict[str, Any]:
        """Parse LLM response into structured comparison result."""
        scores = {}
        reasoning = {}
        winner = "tie"
        confidence = 5.0
        summary = ""
        
        lines = response.strip().split('\n')
        current_criterion = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Parse criterion sections
            if line.startswith("Criterion:"):
                current_criterion = line.split(":", 1)[1].strip().lower()
                if current_criterion in [c.lower() for c in criteria]:
                    scores[current_criterion] = {}
            
            elif line.startswith("Output A Score:") and current_criterion:
                try:
                    score = float(line.split(":", 1)[1].strip())
                    scores[current_criterion][agent_a_name] = score
                except ValueError:
                    scores[current_criterion][agent_a_name] = 5.0
            
            elif line.startswith("Output B Score:") and current_criterion:
                try:
                    score = float(line.split(":", 1)[1].strip())
                    scores[current_criterion][agent_b_name] = score
                except ValueError:
                    scores[current_criterion][agent_b_name] = 5.0
            
            elif line.startswith("Reasoning:") and current_criterion:
                reasoning[current_criterion] = line.split(":", 1)[1].strip()
            
            # Parse final assessment
            elif line.startswith("Overall Winner:"):
                winner_text = line.split(":", 1)[1].strip().lower()
                normalized = winner_text.replace(" ", "_").replace("-", "_")
                
                # Check for tie first
                if "tie" in normalized or "both" in normalized:
                    winner = "tie"
                # Check explicit agent A patterns
                elif normalized in {"a", "agent_a", "output_a", "model_a"} or normalized.startswith("agent_a"):
                    winner = "agent_a"
                # Check explicit agent B patterns  
                elif normalized in {"b", "agent_b", "output_b", "model_b"} or normalized.startswith("agent_b"):
                    winner = "agent_b"
                else:
                    # Fallback to tie if we can't confidently parse
                    winner = "tie"
            
            elif line.startswith("Confidence:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except ValueError:
                    confidence = 5.0
            
            elif line.startswith("Summary:"):
                summary = line.split(":", 1)[1].strip()
        
        # Ensure all criteria have scores
        for criterion in criteria:
            criterion_lower = criterion.lower()
            if criterion_lower not in scores:
                scores[criterion_lower] = {agent_a_name: 5.0, agent_b_name: 5.0}
                reasoning[criterion_lower] = "No specific evaluation provided"
        
        return {
            "scores": scores,
            "reasoning": reasoning,
            "winner": winner,
            "confidence": confidence,
            "summary": summary
        }

class ComparisonEval(BaseEvaluator):
    """
    Evaluator for comparing two agent outputs side-by-side.
    
    Provides A/B testing capabilities and detailed comparison across multiple criteria.
    """
    
    def __init__(
        self,
        input_text: str,
        agent_a: Optional["Agent"] = None,
        agent_b: Optional["Agent"] = None,
        output_a: Optional[str] = None,
        output_b: Optional[str] = None,
        criteria: List[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        **kwargs
    ):
        """
        Initialize comparison evaluator.
        
        Args:
            input_text: Input prompt for both agents
            agent_a: First agent (if not providing output_a directly)
            agent_b: Second agent (if not providing output_b directly)
            output_a: Pre-generated output A (if not using agent_a)
            output_b: Pre-generated output B (if not using agent_b)
            criteria: List of evaluation criteria (default: ["accuracy", "clarity", "helpfulness"])
            model: LLM model for evaluation
            temperature: Temperature for evaluation LLM
        """
        super().__init__(**kwargs)
        
        self.input_text = input_text
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.output_a = output_a
        self.output_b = output_b
        self.criteria = criteria or ["accuracy", "clarity", "helpfulness"]
        
        # Validation
        if not ((agent_a and agent_b) or (output_a and output_b)):
            raise ValueError("Must provide either (agent_a, agent_b) or (output_a, output_b)")
        
        self.grader = ComparisonGrader(
            model=model,
            temperature=temperature
        )
    
    def run(self, print_summary: bool = True) -> ComparisonResult:
        """
        Run the comparison evaluation.
        
        Args:
            print_summary: Print detailed results
            
        Returns:
            ComparisonResult with detailed comparison analysis
        """
        self.before_run()
        start_time = time.time()
        
        try:
            # Generate outputs if needed
            output_a, agent_a_name = self._get_output_a()
            output_b, agent_b_name = self._get_output_b()
            
            # Run comparison
            comparison_data = self.grader.compare_outputs(
                input_text=self.input_text,
                output_a=output_a,
                output_b=output_b,
                agent_a_name=agent_a_name,
                agent_b_name=agent_b_name,
                criteria=self.criteria
            )
            
            # Calculate overall scores
            overall_score_a = self._calculate_overall_score(comparison_data["scores"], agent_a_name)
            overall_score_b = self._calculate_overall_score(comparison_data["scores"], agent_b_name)
            
            result = ComparisonResult(
                input_text=self.input_text,
                output_a=output_a,
                output_b=output_b,
                agent_a_name=agent_a_name,
                agent_b_name=agent_b_name,
                criteria=self.criteria,
                scores=comparison_data["scores"],
                reasoning=comparison_data["reasoning"],
                winner=comparison_data["winner"],
                overall_score_a=overall_score_a,
                overall_score_b=overall_score_b,
                confidence=comparison_data["confidence"],
                duration=time.time() - start_time
            )
            
            if print_summary:
                self._print_summary(result)
            
            self.after_run(result)
            return result
            
        except Exception as e:
            logger.error(f"ComparisonEval failed: {e}")
            raise
    
    def _get_output_a(self) -> tuple:
        """Get output A and agent name."""
        if self.output_a:
            return self.output_a, "Agent_A"
        elif self.agent_a:
            output = self.agent_a.start(self.input_text)
            return str(output), self.agent_a.name
        else:
            raise ValueError("No output_a or agent_a provided")
    
    def _get_output_b(self) -> tuple:
        """Get output B and agent name."""
        if self.output_b:
            return self.output_b, "Agent_B"
        elif self.agent_b:
            output = self.agent_b.start(self.input_text)
            return str(output), self.agent_b.name
        else:
            raise ValueError("No output_b or agent_b provided")
    
    def _calculate_overall_score(self, scores: Dict[str, Dict[str, float]], agent_name: str) -> float:
        """Calculate overall score for an agent across all criteria."""
        if not scores:
            return 0.0
        
        total_score = 0.0
        count = 0
        
        for criterion_scores in scores.values():
            if agent_name in criterion_scores:
                total_score += criterion_scores[agent_name]
                count += 1
        
        return total_score / count if count > 0 else 0.0
    
    def _print_summary(self, result: ComparisonResult) -> None:
        """Print detailed comparison summary."""
        print(f"\n{'='*80}")
        print(f"Comparison Evaluation Results")
        print(f"{'='*80}")
        print(f"Input: {result.input_text[:100]}{'...' if len(result.input_text) > 100 else ''}")
        print(f"Duration: {result.duration:.2f}s")
        print()
        
        # Overall scores
        print(f"Overall Scores:")
        print(f"  🤖 {result.agent_a_name}: {result.overall_score_a:.1f}/10")
        print(f"  🤖 {result.agent_b_name}: {result.overall_score_b:.1f}/10")
        print()
        
        # Winner
        winner_icon = "🏆" if result.winner != "tie" else "🤝"
        winner_text = {
            "agent_a": result.agent_a_name,
            "agent_b": result.agent_b_name,
            "tie": "Tie"
        }.get(result.winner, result.winner)
        print(f"Winner: {winner_icon} {winner_text} (Confidence: {result.confidence:.1f}/10)")
        print()
        
        # Detailed scores by criteria
        print("Detailed Scores by Criteria:")
        for criterion in result.criteria:
            criterion_lower = criterion.lower()
            if criterion_lower in result.scores:
                scores = result.scores[criterion_lower]
                score_a = scores.get(result.agent_a_name, 0)
                score_b = scores.get(result.agent_b_name, 0)
                reasoning = result.reasoning.get(criterion_lower, "No reasoning provided")
                
                print(f"  📊 {criterion.title()}:")
                print(f"    {result.agent_a_name}: {score_a:.1f}/10")
                print(f"    {result.agent_b_name}: {score_b:.1f}/10")
                print(f"    Reasoning: {reasoning}")
                print()
        
        print(f"{'='*80}\n")