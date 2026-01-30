"""
Unified Judge class for LLM-as-judge evaluation.

Provides a simple, unified API for evaluating agent outputs using LLM-as-judge.
Follows PraisonAI naming conventions and engineering principles.

DRY: Extends BaseLLMGrader to reuse prompt building and response parsing.
Protocol-driven: Implements JudgeProtocol for extensibility.
Zero performance impact: Lazy imports for litellm.

Example:
    >>> from praisonaiagents.eval import Judge
    >>> result = Judge().run(output="4", expected="4")
    >>> print(f"Score: {result.score}/10")
"""

import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from .grader import BaseLLMGrader
from .results import JudgeResult

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..agents.agents import AgentManager

logger = logging.getLogger(__name__)


# Judge Registry - follows add_X/get_X/list_X naming convention
_JUDGE_REGISTRY: Dict[str, Type["Judge"]] = {}


@dataclass
class JudgeConfig:
    """
    Configuration for Judge instances.
    
    Attributes:
        model: LLM model to use for judging (default: gpt-4o-mini)
        temperature: Temperature for LLM calls (default: 0.1 for consistency)
        max_tokens: Maximum tokens for LLM response
        threshold: Score threshold for passing (default: 7.0)
        criteria: Optional custom criteria for evaluation
    """
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 500
    threshold: float = 7.0
    criteria: Optional[str] = None
    
    def __post_init__(self):
        if self.model is None:
            self.model = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")


@dataclass
class JudgeCriteriaConfig:
    """
    Dynamic criteria configuration for domain-agnostic judging.
    
    Enables judges to evaluate ANY domain, not just agent outputs:
    - Water flow optimization
    - Data pipeline efficiency
    - Manufacturing quality
    - Recipe/workflow optimization
    - Any custom domain
    
    Attributes:
        name: Name of the criteria configuration
        description: Description of what is being evaluated
        prompt_template: Custom prompt template with {output} placeholder
        scoring_dimensions: List of dimensions to score (e.g., ["efficiency", "safety"])
        threshold: Score threshold for passing (default: 7.0)
    
    Example:
        >>> config = JudgeCriteriaConfig(
        ...     name="water_flow",
        ...     description="Evaluate water flow optimization",
        ...     prompt_template="Is the water flow optimal? Output: {output}",
        ...     scoring_dimensions=["flow_rate", "pressure", "efficiency"],
        ... )
        >>> judge = Judge(criteria_config=config)
    """
    name: str
    description: str
    prompt_template: str
    scoring_dimensions: List[str]
    threshold: float = 7.0


class Judge(BaseLLMGrader):
    """
    Unified LLM-as-judge for evaluating agent outputs.
    
    Provides a simple API for:
    - Accuracy evaluation (comparing output to expected)
    - Criteria evaluation (evaluating against custom criteria)
    - Custom evaluation (subclass for domain-specific judges)
    
    Follows PraisonAI conventions:
    - run() for synchronous execution
    - run_async() for asynchronous execution
    - Simple defaults, explicit overrides
    
    Example:
        >>> # Simple accuracy check
        >>> result = Judge().run(output="4", expected="4")
        
        >>> # Custom criteria
        >>> result = Judge(criteria="Response is helpful").run(output="Hello!")
        
        >>> # With agent
        >>> result = Judge().run(agent=my_agent, input="2+2", expected="4")
    """
    
    # Default prompt for accuracy evaluation
    ACCURACY_PROMPT = """You are an expert evaluator. Compare the actual output against the expected output.

INPUT: {input_text}

EXPECTED OUTPUT:
{expected}

ACTUAL OUTPUT:
{output}

Scoring Guidelines:
- 10: Perfect match in meaning and completeness
- 8-9: Very close, minor differences that don't affect correctness
- 6-7: Mostly correct but missing some details or has minor errors
- 4-5: Partially correct but significant issues
- 2-3: Mostly incorrect but shows some understanding
- 1: Completely wrong or irrelevant

Respond in this EXACT format:
SCORE: [number 1-10]
REASONING: [brief explanation]
SUGGESTIONS:
- [improvement suggestion 1]
- [improvement suggestion 2]
"""
    
    # Default prompt for criteria evaluation
    CRITERIA_PROMPT = """You are an expert evaluator. Evaluate the output against the given criteria.

CRITERIA: {criteria}

OUTPUT TO EVALUATE:
{output}

Score the output from 1-10 based on how well it meets the criteria.
- 10: Perfectly meets all criteria
- 8-9: Meets criteria very well with minor issues
- 6-7: Meets most criteria but has some gaps
- 4-5: Partially meets criteria
- 2-3: Barely meets criteria
- 1: Does not meet criteria at all

Respond in this EXACT format:
SCORE: [number 1-10]
REASONING: [brief explanation]
SUGGESTIONS:
- [improvement suggestion 1]
- [improvement suggestion 2]
"""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 500,
        threshold: float = 7.0,
        criteria: Optional[str] = None,
        config: Optional[JudgeConfig] = None,
        criteria_config: Optional[JudgeCriteriaConfig] = None,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the Judge.
        
        Args:
            model: LLM model to use (default: gpt-4o-mini)
            temperature: Temperature for LLM calls (default: 0.1)
            max_tokens: Maximum tokens for response
            threshold: Score threshold for passing (default: 7.0)
            criteria: Optional custom criteria for evaluation
            config: Optional JudgeConfig for all settings
            criteria_config: Optional JudgeCriteriaConfig for domain-agnostic evaluation
            session_id: Optional session ID for trace isolation per recipe run
        
        Example:
            >>> # Simple usage
            >>> judge = Judge(criteria="Response is helpful")
            
            >>> # Domain-agnostic usage (water flow, data pipeline, etc.)
            >>> config = JudgeCriteriaConfig(
            ...     name="water_flow",
            ...     description="Evaluate water flow",
            ...     prompt_template="Is the water flow optimal? {output}",
            ...     scoring_dimensions=["flow_rate", "pressure"],
            ... )
            >>> judge = Judge(criteria_config=config)
        """
        # Use config if provided, otherwise use individual params
        if config:
            model = config.model
            temperature = config.temperature
            max_tokens = config.max_tokens
            threshold = config.threshold
            criteria = config.criteria
        
        # Use criteria_config if provided
        if criteria_config:
            threshold = criteria_config.threshold
            # criteria from criteria_config takes precedence
            criteria = criteria_config.description
        
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        self.threshold = threshold
        self.criteria = criteria
        self.criteria_config = criteria_config
        self.session_id = session_id
    
    def _build_judge_prompt(
        self,
        output: str,
        expected: Optional[str] = None,
        criteria: Optional[str] = None,
        input_text: str = "",
    ) -> str:
        """
        Build the appropriate prompt based on evaluation type.
        
        Args:
            output: The output to evaluate
            expected: Optional expected output (triggers accuracy mode)
            criteria: Optional criteria (triggers criteria mode)
            input_text: Optional input context
            
        Returns:
            Formatted prompt string
        """
        # Use criteria_config custom prompt template if available
        if self.criteria_config and self.criteria_config.prompt_template:
            # Domain-agnostic mode: use custom prompt template
            template = self.criteria_config.prompt_template
            # Support common placeholders
            return template.format(
                output=output,
                input=input_text or "Not provided",
                input_text=input_text or "Not provided",
                expected=expected or "Not specified",
            )
        
        # Use instance criteria if not provided
        effective_criteria = criteria or self.criteria
        
        if expected is not None:
            # Accuracy mode
            return self.ACCURACY_PROMPT.format(
                input_text=input_text or "Not provided",
                expected=expected,
                output=output,
            )
        elif effective_criteria:
            # Criteria mode
            return self.CRITERIA_PROMPT.format(
                criteria=effective_criteria,
                output=output,
            )
        else:
            # Default: general quality evaluation
            return self.PROMPT_TEMPLATE.format(
                input_text=input_text or "Not provided",
                output=output,
                expected_section="",
            )
    
    def _parse_judge_response(
        self,
        response_text: str,
        output: str,
        expected: Optional[str],
        criteria: Optional[str],
    ) -> JudgeResult:
        """
        Parse LLM response into JudgeResult.
        
        Args:
            response_text: Raw LLM response
            output: Original output
            expected: Original expected output
            criteria: Original criteria
            
        Returns:
            JudgeResult with score, passed, reasoning, suggestions
        """
        score = 5.0
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
                    score = max(1.0, min(10.0, score))
                except ValueError:
                    pass
            
            elif line.startswith('REASONING:'):
                reasoning = line.replace('REASONING:', '').strip()
            
            elif line.startswith('SUGGESTIONS:'):
                in_suggestions = True
                rest = line.replace('SUGGESTIONS:', '').strip()
                if rest.lower() not in ('none', '') and rest:
                    suggestions.append(rest)
            
            elif in_suggestions and line.startswith('-'):
                suggestion = line.lstrip('- ').strip()
                if suggestion and suggestion.lower() != 'none':
                    suggestions.append(suggestion)
        
        return JudgeResult(
            score=score,
            passed=score >= self.threshold,
            reasoning=reasoning,
            output=output,
            expected=expected,
            criteria=criteria or self.criteria,
            suggestions=suggestions,
        )
    
    def run(
        self,
        output: str = "",
        expected: Optional[str] = None,
        criteria: Optional[str] = None,
        input: str = "",
        agent: Optional["Agent"] = None,
        agents: Optional["Agents"] = None,
        print_summary: bool = False,
        **kwargs: Any,
    ) -> JudgeResult:
        """
        Judge an output.
        
        Args:
            output: The output to judge (required if no agent)
            expected: Optional expected output for accuracy evaluation
            criteria: Optional criteria for criteria evaluation
            input: Optional input context
            agent: Optional Agent to run and judge
            agents: Optional Agents to run and judge
            print_summary: Whether to print result summary
            **kwargs: Additional arguments
            
        Returns:
            JudgeResult with score, passed, reasoning, suggestions
        
        Example:
            >>> result = Judge().run(output="4", expected="4", input="What is 2+2?")
        """
        # Get output from agent if provided
        if agent is not None:
            output = self._get_agent_output(agent, input)
        elif agents is not None:
            output = self._get_agents_output(agents, input)
        
        if not output:
            return JudgeResult(
                score=0.0,
                passed=False,
                reasoning="No output provided to judge",
                output="",
                expected=expected,
                criteria=criteria,
            )
        
        litellm = self._get_litellm()
        
        prompt = self._build_judge_prompt(output, expected, criteria, input)
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            response_text = response.choices[0].message.content or ""
            result = self._parse_judge_response(response_text, output, expected, criteria)
            
            if print_summary:
                result.print_summary()
            
            return result
            
        except Exception as e:
            logger.warning(f"Judge evaluation failed: {e}")
            return JudgeResult(
                score=0.0,
                passed=False,
                reasoning=f"Evaluation error: {str(e)}",
                output=output,
                expected=expected,
                criteria=criteria,
            )
    
    async def run_async(
        self,
        output: str = "",
        expected: Optional[str] = None,
        criteria: Optional[str] = None,
        input: str = "",
        agent: Optional["Agent"] = None,
        agents: Optional["Agents"] = None,
        print_summary: bool = False,
        **kwargs: Any,
    ) -> JudgeResult:
        """
        Judge an output asynchronously.
        
        Args:
            output: The output to judge
            expected: Optional expected output
            criteria: Optional criteria
            input: Optional input context
            agent: Optional Agent to run and judge
            agents: Optional Agents to run and judge
            print_summary: Whether to print result summary
            **kwargs: Additional arguments
            
        Returns:
            JudgeResult with score, passed, reasoning, suggestions
        
        Example:
            >>> result = await Judge().run_async(output="4", expected="4", input="What is 2+2?")
        """
        # Get output from agent if provided
        if agent is not None:
            output = await self._get_agent_output_async(agent, input)
        elif agents is not None:
            output = await self._get_agents_output_async(agents, input)
        
        if not output:
            return JudgeResult(
                score=0.0,
                passed=False,
                reasoning="No output provided to judge",
                output="",
                expected=expected,
                criteria=criteria,
            )
        
        litellm = self._get_litellm()
        
        prompt = self._build_judge_prompt(output, expected, criteria, input)
        
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            response_text = response.choices[0].message.content or ""
            result = self._parse_judge_response(response_text, output, expected, criteria)
            
            if print_summary:
                result.print_summary()
            
            return result
            
        except Exception as e:
            logger.warning(f"Async judge evaluation failed: {e}")
            return JudgeResult(
                score=0.0,
                passed=False,
                reasoning=f"Evaluation error: {str(e)}",
                output=output,
                expected=expected,
                criteria=criteria,
            )
    
    def _get_agent_output(self, agent: "Agent", input_text: str) -> str:
        """Get output from an Agent."""
        if hasattr(agent, 'chat'):
            return str(agent.chat(input_text))
        elif hasattr(agent, 'start'):
            result = agent.start(input_text)
            if hasattr(result, 'raw'):
                return str(result.raw)
            return str(result)
        else:
            raise ValueError("Agent must have 'chat' or 'start' method")
    
    async def _get_agent_output_async(self, agent: "Agent", input_text: str) -> str:
        """Get output from an Agent asynchronously."""
        if hasattr(agent, 'achat'):
            return str(await agent.achat(input_text))
        elif hasattr(agent, 'astart'):
            result = await agent.astart(input_text)
            if hasattr(result, 'raw'):
                return str(result.raw)
            return str(result)
        else:
            # Fall back to sync
            return self._get_agent_output(agent, input_text)
    
    def _get_agents_output(self, agents: "Agents", input_text: str) -> str:
        """Get output from Agents (multi-agent)."""
        if hasattr(agents, 'start'):
            result = agents.start(input_text)
            if hasattr(result, 'raw'):
                return str(result.raw)
            return str(result)
        else:
            raise ValueError("Agents must have 'start' method")
    
    async def _get_agents_output_async(self, agents: "Agents", input_text: str) -> str:
        """Get output from Agents asynchronously."""
        if hasattr(agents, 'astart'):
            result = await agents.astart(input_text)
            if hasattr(result, 'raw'):
                return str(result.raw)
            return str(result)
        else:
            # Fall back to sync
            return self._get_agents_output(agents, input_text)


# Built-in judge types
class AccuracyJudge(Judge):
    """Judge for accuracy evaluation (comparing output to expected)."""
    pass


class CriteriaJudge(Judge):
    """Judge for criteria-based evaluation."""
    pass


class RecipeJudge(Judge):
    """
    Judge for evaluating recipe/workflow execution traces.
    
    This is a lightweight wrapper that delegates to ContextEffectivenessJudge
    in the praisonai wrapper package for full trace analysis.
    
    For simple output evaluation, use Judge directly.
    For full trace analysis, use:
        from praisonai.replay import ContextEffectivenessJudge
    
    Modes:
        - context: Evaluate context flow between agents (default)
        - memory: Evaluate memory utilization
        - knowledge: Evaluate knowledge retrieval
    
    Example:
        >>> from praisonaiagents.eval import RecipeJudge
        >>> judge = RecipeJudge(mode="context")
        >>> # For trace analysis, use the full implementation:
        >>> from praisonai.replay import ContextEffectivenessJudge
        >>> judge = ContextEffectivenessJudge(mode="context")
        >>> report = judge.judge_trace(events, session_id="run-123")
    """
    
    RECIPE_PROMPT = """You are an expert evaluator for AI agent workflow recipes.

RECIPE OUTPUT TO EVALUATE:
{output}

EXPECTED BEHAVIOR:
{expected}

EVALUATION CRITERIA:
{criteria}

Evaluate the recipe execution on:
1. Task completion (1-10): Did agents complete their assigned tasks?
2. Context flow (1-10): Was context properly passed between agents?
3. Output quality (1-10): Is the final output useful and accurate?

Respond in this EXACT format:
SCORE: [average of above, 1-10]
REASONING: [brief explanation]
SUGGESTIONS:
- [improvement suggestion 1]
- [improvement suggestion 2]
"""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 800,
        threshold: float = 7.0,
        mode: str = "context",
        config: Optional[JudgeConfig] = None,
    ):
        """
        Initialize RecipeJudge.
        
        Args:
            model: LLM model to use
            temperature: Temperature for LLM calls
            max_tokens: Maximum tokens for response
            threshold: Score threshold for passing
            mode: Evaluation mode (context, memory, knowledge)
            config: Optional JudgeConfig
        """
        criteria = f"Recipe execution quality in {mode} mode"
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            threshold=threshold,
            criteria=criteria,
            config=config,
        )
        self.mode = mode
    
    def _build_judge_prompt(
        self,
        output: str,
        expected: Optional[str] = None,
        criteria: Optional[str] = None,
        input_text: str = "",
    ) -> str:
        """Build recipe-specific prompt."""
        return self.RECIPE_PROMPT.format(
            output=output,
            expected=expected or "Complete workflow execution",
            criteria=criteria or self.criteria or f"Recipe quality in {self.mode} mode",
        )


# Registry functions following PraisonAI naming conventions
def add_judge(name: str, judge_class: Type[Judge]) -> None:
    """
    Register a custom judge type.
    
    Args:
        name: Name for the judge type
        judge_class: Judge class to register
        
    Example:
        >>> class RecipeJudge(Judge):
        ...     criteria = "Recipe is complete and accurate"
        >>> add_judge("recipe", RecipeJudge)
    """
    _JUDGE_REGISTRY[name.lower()] = judge_class


def get_judge(name: str) -> Optional[Type[Judge]]:
    """
    Get a registered judge type by name.
    
    Args:
        name: Name of the judge type
        
    Returns:
        Judge class or None if not found
        
    Example:
        >>> JudgeClass = get_judge("accuracy")
        >>> judge = JudgeClass()
    """
    return _JUDGE_REGISTRY.get(name.lower())


def list_judges() -> List[str]:
    """
    List all registered judge types.
    
    Returns:
        List of judge type names
        
    Example:
        >>> judges = list_judges()
        >>> print(judges)  # ['accuracy', 'criteria', ...]
    """
    return list(_JUDGE_REGISTRY.keys())


def remove_judge(name: str) -> bool:
    """
    Remove a registered judge type.
    
    Args:
        name: Name of the judge type to remove
        
    Returns:
        True if removed, False if not found
    """
    if name.lower() in _JUDGE_REGISTRY:
        del _JUDGE_REGISTRY[name.lower()]
        return True
    return False


# Register built-in judges
_JUDGE_REGISTRY["accuracy"] = AccuracyJudge
_JUDGE_REGISTRY["criteria"] = CriteriaJudge
_JUDGE_REGISTRY["recipe"] = RecipeJudge


# Optimization Rule Registry - for domain-agnostic optimization rules
_OPTIMIZATION_RULE_REGISTRY: Dict[str, Type] = {}


def add_optimization_rule(name: str, rule_class: Type) -> None:
    """
    Register a custom optimization rule.
    
    Args:
        name: Name for the rule
        rule_class: Rule class implementing OptimizationRuleProtocol
        
    Example:
        >>> class WaterLeakRule:
        ...     name = "water_leak"
        ...     pattern = r"(leak|overflow)"
        ...     severity = "critical"
        ...     def get_fix(self, context): return "Check for leaks"
        >>> add_optimization_rule("water_leak", WaterLeakRule)
    """
    _OPTIMIZATION_RULE_REGISTRY[name.lower()] = rule_class


def get_optimization_rule(name: str) -> Optional[Type]:
    """
    Get a registered optimization rule by name.
    
    Args:
        name: Name of the rule
        
    Returns:
        Rule class or None if not found
    """
    return _OPTIMIZATION_RULE_REGISTRY.get(name.lower())


def list_optimization_rules() -> List[str]:
    """
    List all registered optimization rules.
    
    Returns:
        List of rule names
    """
    return list(_OPTIMIZATION_RULE_REGISTRY.keys())


def remove_optimization_rule(name: str) -> bool:
    """
    Remove a registered optimization rule.
    
    Args:
        name: Name of the rule to remove
        
    Returns:
        True if removed, False if not found
    """
    if name.lower() in _OPTIMIZATION_RULE_REGISTRY:
        del _OPTIMIZATION_RULE_REGISTRY[name.lower()]
        return True
    return False


__all__ = [
    'Judge',
    'JudgeConfig',
    'JudgeCriteriaConfig',
    'JudgeResult',
    'AccuracyJudge',
    'CriteriaJudge',
    'RecipeJudge',
    'add_judge',
    'get_judge',
    'list_judges',
    'remove_judge',
    'add_optimization_rule',
    'get_optimization_rule',
    'list_optimization_rules',
    'remove_optimization_rule',
]
