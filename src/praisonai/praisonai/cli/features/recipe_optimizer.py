"""
Recipe Optimizer for PraisonAI.

Iteratively optimizes recipes using LLM-as-judge feedback.
Runs the recipe, judges the output, proposes improvements, and applies them.

DRY: Reuses ContextEffectivenessJudge from replay module.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Any

logger = logging.getLogger(__name__)


class RecipeOptimizer:
    """
    Iteratively optimizes recipes using judge feedback.
    
    Usage:
        optimizer = RecipeOptimizer(max_iterations=3, score_threshold=8.0)
        final_report = optimizer.optimize(recipe_path)
    """
    
    def __init__(
        self,
        max_iterations: int = 3,
        score_threshold: float = 8.0,
        model: Optional[str] = None,
    ):
        """
        Initialize the optimizer.
        
        Args:
            max_iterations: Maximum optimization iterations
            score_threshold: Score threshold to stop optimization (1-10)
            model: LLM model for judging and optimization
        """
        self.max_iterations = max_iterations
        self.score_threshold = score_threshold
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
    
    def _get_litellm(self):
        """Lazy import litellm."""
        try:
            import litellm
            return litellm
        except ImportError:
            raise ImportError(
                "litellm is required for recipe optimization. "
                "Install with: pip install litellm"
            )
    
    def should_continue(self, report: Any, iteration: int) -> bool:
        """
        Determine if optimization should continue.
        
        Args:
            report: JudgeReport from last iteration
            iteration: Current iteration number (1-indexed)
            
        Returns:
            True if should continue, False if should stop
        """
        # Stop if max iterations reached
        if iteration >= self.max_iterations:
            return False
        
        # Stop if score threshold reached
        if hasattr(report, 'overall_score') and report.overall_score >= self.score_threshold:
            return False
        
        return True
    
    def run_iteration(
        self,
        recipe_path: Path,
        input_data: str = "",
        iteration: int = 1,
    ) -> Tuple[Any, str]:
        """
        Run one optimization iteration: execute recipe and judge output.
        
        Args:
            recipe_path: Path to recipe folder
            input_data: Input data for recipe
            iteration: Current iteration number
            
        Returns:
            Tuple of (JudgeReport, trace_id)
        """
        from praisonai import recipe
        from praisonai.replay import ContextTraceReader, ContextEffectivenessJudge
        
        # Generate unique trace name for this iteration
        trace_name = f"{recipe_path.name}-opt-{iteration}"
        
        # Run the recipe with trace saving
        result = recipe.run(
            str(recipe_path),
            input={"input": input_data} if input_data else {},
            options={
                "save_replay": True,
                "trace_name": trace_name,
            }
        )
        
        # Judge the trace
        reader = ContextTraceReader(trace_name)
        events = reader.get_all()
        
        if not events:
            logger.warning(f"No events found for trace: {trace_name}")
            # Return a minimal report
            from praisonai.replay.judge import JudgeReport
            return JudgeReport(
                session_id=trace_name,
                timestamp="",
                total_agents=0,
                overall_score=5.0,
                agent_scores=[],
                summary="No events to judge",
                recommendations=["Ensure recipe runs correctly"],
            ), trace_name
        
        # Run judge
        yaml_file = str(recipe_path / "agents.yaml")
        judge = ContextEffectivenessJudge(model=self.model)
        report = judge.judge_trace(events, session_id=trace_name, yaml_file=yaml_file)
        
        return report, trace_name
    
    def propose_improvements(
        self,
        report: Any,
        recipe_path: Path,
        optimization_target: Optional[str] = None,
    ) -> List[str]:
        """
        Use LLM to propose specific YAML improvements based on judge feedback.
        
        Args:
            report: JudgeReport with scores and suggestions
            recipe_path: Path to recipe folder
            optimization_target: Optional specific aspect to optimize
            
        Returns:
            List of improvement suggestions
        """
        litellm = self._get_litellm()
        
        # Read current agents.yaml
        agents_yaml = (recipe_path / "agents.yaml").read_text()
        
        # Build prompt
        suggestions = []
        if hasattr(report, 'agent_scores'):
            for score in report.agent_scores:
                if hasattr(score, 'suggestions'):
                    suggestions.extend(score.suggestions)
        
        recommendations = getattr(report, 'recommendations', [])
        overall_score = getattr(report, 'overall_score', 5.0)
        
        prompt = f"""You are an expert at optimizing PraisonAI agent recipes.

Current agents.yaml:
```yaml
{agents_yaml[:3000]}
```

Judge Report:
- Overall Score: {overall_score}/10
- Recommendations: {recommendations}
- Agent Suggestions: {suggestions}

{f"Optimization Target: {optimization_target}" if optimization_target else ""}

Propose 2-3 specific improvements to the agents.yaml file.
For each improvement, explain:
1. What to change
2. Why it will help
3. The exact YAML modification

Be specific and actionable. Focus on:
- Clearer agent instructions
- Better tool selection
- Improved expected_output specifications
- Better workflow structure
"""
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1500,
            )
            
            improvements_text = response.choices[0].message.content or ""
            
            # Parse improvements into list
            improvements = []
            for line in improvements_text.split('\n'):
                line = line.strip()
                if line.startswith(('1.', '2.', '3.', '-', '*')):
                    improvements.append(line.lstrip('123.-* '))
            
            return improvements if improvements else [improvements_text]
            
        except Exception as e:
            logger.warning(f"Failed to propose improvements: {e}")
            return recommendations if recommendations else ["Review agent instructions"]
    
    def apply_improvements(
        self,
        recipe_path: Path,
        improvements: List[str],
    ) -> bool:
        """
        Apply improvements to agents.yaml using LLM.
        
        Args:
            recipe_path: Path to recipe folder
            improvements: List of improvement suggestions
            
        Returns:
            True if improvements were applied
        """
        litellm = self._get_litellm()
        
        # Read current agents.yaml
        agents_yaml_path = recipe_path / "agents.yaml"
        current_yaml = agents_yaml_path.read_text()
        
        prompt = f"""You are an expert at modifying PraisonAI agent YAML files.

Current agents.yaml:
```yaml
{current_yaml}
```

Apply these improvements:
{chr(10).join(f"- {imp}" for imp in improvements)}

Output ONLY the complete, updated agents.yaml file.
Do not include markdown code blocks or explanations.
Ensure the YAML is valid and parseable.
"""
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=3000,
            )
            
            new_yaml = response.choices[0].message.content or ""
            
            # Clean up any markdown
            new_yaml = new_yaml.strip()
            if new_yaml.startswith('```'):
                lines = new_yaml.split('\n')
                new_yaml = '\n'.join(lines[1:-1] if lines[-1].startswith('```') else lines[1:])
            
            # Validate YAML
            import yaml
            yaml.safe_load(new_yaml)
            
            # Write updated YAML
            agents_yaml_path.write_text(new_yaml)
            logger.info(f"Applied improvements to {agents_yaml_path}")
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to apply improvements: {e}")
            return False
    
    def optimize(
        self,
        recipe_path: Path,
        input_data: str = "",
        optimization_target: Optional[str] = None,
    ) -> Any:
        """
        Run the full optimization loop.
        
        Args:
            recipe_path: Path to recipe folder
            input_data: Input data for recipe runs
            optimization_target: Optional specific aspect to optimize
            
        Returns:
            Final JudgeReport after optimization
        """
        recipe_path = Path(recipe_path)
        
        if not recipe_path.exists():
            raise ValueError(f"Recipe path does not exist: {recipe_path}")
        
        final_report = None
        
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"Optimization iteration {iteration}/{self.max_iterations}")
            
            # Run and judge
            report, trace_id = self.run_iteration(recipe_path, input_data, iteration)
            final_report = report
            
            score = getattr(report, 'overall_score', 0)
            logger.info(f"  Score: {score}/10")
            
            # Check if we should continue
            if not self.should_continue(report, iteration):
                if score >= self.score_threshold:
                    logger.info(f"  ✅ Score threshold reached!")
                else:
                    logger.info(f"  Max iterations reached")
                break
            
            # Propose and apply improvements
            improvements = self.propose_improvements(report, recipe_path, optimization_target)
            logger.info(f"  Proposed {len(improvements)} improvements")
            
            if improvements:
                applied = self.apply_improvements(recipe_path, improvements)
                if applied:
                    logger.info(f"  ✏️ Applied improvements")
                else:
                    logger.warning(f"  Failed to apply improvements")
        
        return final_report


__all__ = ['RecipeOptimizer']
