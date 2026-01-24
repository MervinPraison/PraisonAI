"""
LLM as Judge for Context Effectiveness Analysis.

Analyzes trace events to evaluate how effectively context was passed
between agents and how well agents performed their tasks.

DRY: Reuses BaseLLMGrader from praisonaiagents.eval for LLM-as-judge logic.
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolEvaluation:
    """Evaluation of a single tool call."""
    tool_name: str
    agent_name: str
    input_quality_score: float  # 1-10: Was the input well-formed?
    output_utilization_score: float  # 1-10: Was the output fully used?
    result_completeness: float  # 1-10: Was the full result captured?
    reasoning: str
    issues: List[str] = field(default_factory=list)
    input_summary: str = ""
    output_summary: str = ""
    was_truncated: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContextFlowEvaluation:
    """Evaluation of context flow between agents."""
    from_agent: str
    to_agent: str
    context_passed_score: float  # 1-10: How much context was passed?
    context_relevance_score: float  # 1-10: Was the right context passed?
    content_loss_detected: bool  # Was important content lost?
    lost_content_summary: str = ""
    reasoning: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContextEffectivenessScore:
    """Score for a single agent's context effectiveness."""
    agent_name: str
    task_achievement_score: float  # 1-10: Did agent achieve its task?
    context_utilization_score: float  # 1-10: How well was context used?
    output_quality_score: float  # 1-10: Quality of output
    overall_score: float  # Average of above
    reasoning: str
    suggestions: List[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    wasted_tokens: int = 0
    tool_evaluations: List[ToolEvaluation] = field(default_factory=list)
    # Enhanced evaluation criteria
    instruction_following_score: float = 0.0  # 1-10: Did agent follow instructions?
    hallucination_score: float = 0.0  # 1-10: 10=no hallucination, 1=severe hallucination
    error_handling_score: float = 0.0  # 1-10: How well did agent handle errors?
    tool_errors: List[str] = field(default_factory=list)  # List of tool errors encountered
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["tool_evaluations"] = [t.to_dict() for t in self.tool_evaluations]
        return result


@dataclass
class JudgeReport:
    """Complete judge report for a trace session."""
    session_id: str
    timestamp: str
    total_agents: int
    overall_score: float
    agent_scores: List[ContextEffectivenessScore]
    summary: str
    recommendations: List[str]
    metrics: Dict[str, Any] = field(default_factory=dict)
    context_flow_evaluations: List[ContextFlowEvaluation] = field(default_factory=list)
    content_loss_detected: bool = False
    content_loss_details: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "total_agents": self.total_agents,
            "overall_score": self.overall_score,
            "agent_scores": [s.to_dict() for s in self.agent_scores],
            "summary": self.summary,
            "recommendations": self.recommendations,
            "metrics": self.metrics,
            "context_flow_evaluations": [c.to_dict() for c in self.context_flow_evaluations],
            "content_loss_detected": self.content_loss_detected,
            "content_loss_details": self.content_loss_details,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JudgeReport":
        return cls(
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp", ""),
            total_agents=data.get("total_agents", 0),
            overall_score=data.get("overall_score", 0.0),
            agent_scores=[
                ContextEffectivenessScore(**s) for s in data.get("agent_scores", [])
            ],
            summary=data.get("summary", ""),
            recommendations=data.get("recommendations", []),
            metrics=data.get("metrics", {}),
            context_flow_evaluations=[
                ContextFlowEvaluation(**c) for c in data.get("context_flow_evaluations", [])
            ],
            content_loss_detected=data.get("content_loss_detected", False),
            content_loss_details=data.get("content_loss_details", []),
        )


class ContextEffectivenessJudge:
    """
    LLM-as-Judge for analyzing context effectiveness in agent traces.
    
    Evaluates:
    - Task achievement: Did each agent accomplish its goal?
    - Context utilization: Was the context passed effectively used?
    - Output quality: Is the output high quality and relevant?
    
    DRY: Uses the same grading pattern as BaseLLMGrader.
    """
    
    PROMPT_TEMPLATE = """You are an expert evaluator for AI agent workflows. Analyze this agent's performance.

AGENT: {agent_name}
AGENT GOAL: {agent_goal}
TASK DESCRIPTION: {task_description}
EXPECTED OUTPUT FORMAT: {expected_output}

TASK/INPUT: {input_text}
CONTEXT RECEIVED (tokens: {input_tokens}):
{context_summary}

AGENT OUTPUT (tokens: {output_tokens}):
{output}

TOOL CALLS: {tool_calls}
TOOL ERRORS: {tool_errors}

Evaluate on these criteria:
1. TASK ACHIEVEMENT (1-10): Did the agent accomplish what it was asked to do based on the task description?
2. CONTEXT UTILIZATION (1-10): Did the agent effectively use the context provided?
3. OUTPUT QUALITY (1-10): Does the output match the expected format and contain useful information?
4. INSTRUCTION_FOLLOWING (1-10): Did the agent follow the specific instructions given? (format, steps, constraints)
5. HALLUCINATION (1-10): 10=no hallucination/fabrication, 1=severe hallucination. Did agent make up facts or use incorrect parameter names?
6. ERROR_HANDLING (1-10): How well did the agent handle errors? Did it retry correctly? Did it recover gracefully?

Respond in this EXACT format:
TASK_SCORE: [1-10]
CONTEXT_SCORE: [1-10]
QUALITY_SCORE: [1-10]
INSTRUCTION_SCORE: [1-10]
HALLUCINATION_SCORE: [1-10]
ERROR_SCORE: [1-10]
REASONING: [brief explanation of scores, referencing specific issues]
SUGGESTIONS:
- [specific, actionable improvement suggestion 1]
- [specific, actionable improvement suggestion 2]
"""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 800,
        reports_dir: Optional[Path] = None,
    ):
        """
        Initialize the judge.
        
        Args:
            model: LLM model for judging (default: gpt-4o-mini)
            temperature: LLM temperature
            max_tokens: Max tokens for LLM response
            reports_dir: Directory to save judge reports
        """
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reports_dir = reports_dir or Path.home() / ".praison" / "judge_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_litellm(self):
        """Lazy import litellm."""
        try:
            import litellm
            return litellm
        except ImportError:
            raise ImportError(
                "litellm is required for LLM judging. "
                "Install with: pip install litellm"
            )
    
    def _extract_agent_data(self, events: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Extract per-agent data from trace events."""
        agent_data: Dict[str, Dict[str, Any]] = {}
        
        for event in events:
            # Handle both objects and dicts
            if hasattr(event, 'agent_name'):
                agent_name = event.agent_name
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                data = event.data or {}
                prompt_tokens = getattr(event, 'prompt_tokens', 0) or 0
                completion_tokens = getattr(event, 'completion_tokens', 0) or 0
            else:
                agent_name = event.get('agent_name')
                event_type = event.get('event_type', '')
                data = event.get('data', {})
                prompt_tokens = event.get('prompt_tokens', 0) or 0
                completion_tokens = event.get('completion_tokens', 0) or 0
            
            if not agent_name:
                continue
            
            if agent_name not in agent_data:
                agent_data[agent_name] = {
                    "inputs": [],
                    "outputs": [],
                    "context": [],
                    "tool_calls": [],
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
            
            agent_data[agent_name]["prompt_tokens"] += prompt_tokens
            agent_data[agent_name]["completion_tokens"] += completion_tokens
            
            if event_type == "llm_request":
                messages = data.get("messages", [])
                if messages:
                    # Get the last user message as input
                    for msg in reversed(messages):
                        if isinstance(msg, dict) and msg.get("role") == "user":
                            agent_data[agent_name]["inputs"].append(msg.get("content", "")[:500])
                            break
                    # Get context from all messages
                    context_preview = str(messages)[:1000]
                    agent_data[agent_name]["context"].append(context_preview)
            
            elif event_type == "llm_response":
                response_content = data.get("response_content", "")
                if response_content:
                    agent_data[agent_name]["outputs"].append(response_content[:1000])
            
            elif event_type == "tool_call_start":
                tool_name = data.get("tool_name", "unknown")
                tool_args = data.get("tool_args", data.get("args", {}))
                agent_data[agent_name]["tool_calls"].append({
                    "tool_name": tool_name,
                    "args": tool_args,
                    "result": None,
                    "was_truncated": False,
                })
            
            elif event_type == "tool_call_end":
                tool_name = data.get("tool_name", "unknown")
                result = data.get("result", "")
                was_truncated = "[truncated]" in str(result) if result else False
                
                # Find matching tool call and update result
                for tc in reversed(agent_data[agent_name]["tool_calls"]):
                    if isinstance(tc, dict) and tc.get("tool_name") == tool_name and tc.get("result") is None:
                        tc["result"] = result
                        tc["was_truncated"] = was_truncated
                        break
        
        return agent_data
    
    def _extract_tool_events(self, events: List[Any]) -> List[Dict[str, Any]]:
        """Extract detailed tool call events for evaluation."""
        tool_events = []
        
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                agent_name = event.agent_name
                data = event.data or {}
            else:
                event_type = event.get('event_type', '')
                agent_name = event.get('agent_name')
                data = event.get('data', {})
            
            if event_type == "tool_call_end":
                tool_events.append({
                    "agent_name": agent_name,
                    "tool_name": data.get("tool_name", "unknown"),
                    "result": data.get("result", ""),
                    "duration_ms": data.get("duration_ms", 0),
                    "error": data.get("error"),
                    "was_truncated": "[truncated]" in str(data.get("result", "")),
                })
        
        return tool_events
    
    def _evaluate_tool_call(self, tool_event: Dict[str, Any]) -> ToolEvaluation:
        """Evaluate a single tool call using LLM judge."""
        litellm = self._get_litellm()
        
        tool_name = tool_event.get("tool_name", "unknown")
        agent_name = tool_event.get("agent_name", "unknown")
        result = str(tool_event.get("result", ""))[:2000]
        was_truncated = tool_event.get("was_truncated", False)
        
        prompt = f"""Evaluate this tool call:

TOOL: {tool_name}
AGENT: {agent_name}
RESULT (truncated={was_truncated}):
{result}

Evaluate:
1. INPUT_QUALITY (1-10): Was the tool called with appropriate inputs?
2. OUTPUT_UTILIZATION (1-10): Based on the result, will the agent likely use this effectively?
3. RESULT_COMPLETENESS (1-10): Does the result appear complete? (10 if not truncated, lower if truncated)

Respond in this EXACT format:
INPUT_SCORE: [1-10]
OUTPUT_SCORE: [1-10]
COMPLETENESS_SCORE: [1-10]
ISSUES: [comma-separated list of issues, or "none"]
REASONING: [brief explanation]
"""
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            
            response_text = response.choices[0].message.content or ""
            return self._parse_tool_evaluation(response_text, tool_name, agent_name, was_truncated)
            
        except Exception as e:
            logger.warning(f"Tool evaluation failed for {tool_name}: {e}")
            return ToolEvaluation(
                tool_name=tool_name,
                agent_name=agent_name,
                input_quality_score=5.0,
                output_utilization_score=5.0,
                result_completeness=3.0 if was_truncated else 8.0,
                reasoning=f"Evaluation error: {str(e)}",
                was_truncated=was_truncated,
            )
    
    def _parse_tool_evaluation(
        self,
        response_text: str,
        tool_name: str,
        agent_name: str,
        was_truncated: bool,
    ) -> ToolEvaluation:
        """Parse tool evaluation response."""
        input_score = 5.0
        output_score = 5.0
        completeness_score = 3.0 if was_truncated else 8.0
        issues = []
        reasoning = ""
        
        for line in response_text.strip().split('\n'):
            line = line.strip()
            if line.startswith('INPUT_SCORE:'):
                try:
                    input_score = float(line.replace('INPUT_SCORE:', '').strip())
                    input_score = max(1.0, min(10.0, input_score))
                except ValueError:
                    pass
            elif line.startswith('OUTPUT_SCORE:'):
                try:
                    output_score = float(line.replace('OUTPUT_SCORE:', '').strip())
                    output_score = max(1.0, min(10.0, output_score))
                except ValueError:
                    pass
            elif line.startswith('COMPLETENESS_SCORE:'):
                try:
                    completeness_score = float(line.replace('COMPLETENESS_SCORE:', '').strip())
                    completeness_score = max(1.0, min(10.0, completeness_score))
                except ValueError:
                    pass
            elif line.startswith('ISSUES:'):
                issues_str = line.replace('ISSUES:', '').strip()
                if issues_str.lower() != "none":
                    issues = [i.strip() for i in issues_str.split(',') if i.strip()]
            elif line.startswith('REASONING:'):
                reasoning = line.replace('REASONING:', '').strip()
        
        return ToolEvaluation(
            tool_name=tool_name,
            agent_name=agent_name,
            input_quality_score=input_score,
            output_utilization_score=output_score,
            result_completeness=completeness_score,
            reasoning=reasoning,
            issues=issues,
            was_truncated=was_truncated,
        )
    
    def _evaluate_context_flow(
        self,
        events: List[Any],
        agent_order: List[str],
    ) -> List[ContextFlowEvaluation]:
        """Evaluate context flow between agents."""
        if len(agent_order) < 2:
            return []
        
        flow_evaluations = []
        
        # Extract outputs per agent
        agent_outputs = {}
        agent_inputs = {}
        
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                agent_name = event.agent_name
                data = event.data or {}
            else:
                event_type = event.get('event_type', '')
                agent_name = event.get('agent_name')
                data = event.get('data', {})
            
            if not agent_name:
                continue
            
            if event_type == "llm_response":
                response = data.get("response_content", "")
                if response:
                    agent_outputs[agent_name] = response
            
            if event_type == "llm_request":
                messages = data.get("messages", [])
                if messages:
                    agent_inputs[agent_name] = str(messages)
        
        # Evaluate flow between consecutive agents
        for i in range(len(agent_order) - 1):
            from_agent = agent_order[i]
            to_agent = agent_order[i + 1]
            
            from_output = agent_outputs.get(from_agent, "")
            to_input = agent_inputs.get(to_agent, "")
            
            # Check if output was passed to next agent
            content_loss = False
            lost_content = ""
            
            if from_output and to_input:
                # Check if output content appears in next agent's input
                # Handle JSON outputs by checking if key values are present
                import re
                
                # Extract meaningful content (alphanumeric sequences 4+ chars)
                output_tokens = set(re.findall(r'\b[a-zA-Z0-9]{4,}\b', from_output.lower()))
                input_tokens = set(re.findall(r'\b[a-zA-Z0-9]{4,}\b', to_input.lower()))
                
                # Also check for exact substring matches (for JSON values)
                exact_match = from_output in to_input or str(from_output)[:200] in to_input
                
                if exact_match:
                    context_passed_score = 10.0
                    context_relevance_score = 9.0
                else:
                    # Calculate token overlap
                    overlap = len(output_tokens & input_tokens) / max(len(output_tokens), 1)
                    context_passed_score = min(10.0, overlap * 12 + 2)  # Scale to 2-10
                    context_relevance_score = 7.0
                
                if context_passed_score < 5.0:
                    content_loss = True
                    lost_content = f"Only {(context_passed_score/10)*100:.0f}% of output content found in next agent's input"
            else:
                context_passed_score = 5.0
                context_relevance_score = 5.0
            
            flow_evaluations.append(ContextFlowEvaluation(
                from_agent=from_agent,
                to_agent=to_agent,
                context_passed_score=context_passed_score,
                context_relevance_score=context_relevance_score,
                content_loss_detected=content_loss,
                lost_content_summary=lost_content,
                reasoning=f"Context flow from {from_agent} to {to_agent}",
            ))
        
        return flow_evaluations
    
    def _detect_content_loss(self, events: List[Any]) -> tuple:
        """Detect if important content was lost during the workflow."""
        content_loss_detected = False
        content_loss_details = []
        
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                data = event.data or {}
                agent_name = event.agent_name
            else:
                event_type = event.get('event_type', '')
                data = event.get('data', {})
                agent_name = event.get('agent_name', 'unknown')
            
            # Check for truncated tool results
            if event_type == "tool_call_end":
                result = str(data.get("result", ""))
                if "[truncated]" in result:
                    content_loss_detected = True
                    tool_name = data.get("tool_name", "unknown")
                    content_loss_details.append(
                        f"Tool '{tool_name}' result was truncated for agent '{agent_name}'"
                    )
            
            # Check for truncated LLM responses
            if event_type == "llm_response":
                response = str(data.get("response_content", ""))
                if "[truncated]" in response:
                    content_loss_detected = True
                    content_loss_details.append(
                        f"LLM response was truncated for agent '{agent_name}'"
                    )
        
        return content_loss_detected, content_loss_details
    
    def _judge_agent(
        self,
        agent_name: str,
        agent_info: Dict[str, Any],
        yaml_info: Optional[Dict[str, Any]] = None,
    ) -> ContextEffectivenessScore:
        """Judge a single agent's performance with YAML-aware evaluation."""
        litellm = self._get_litellm()
        
        input_text = "\n".join(agent_info.get("inputs", [])[:3]) or "No input recorded"
        output = "\n".join(agent_info.get("outputs", [])[:3]) or "No output recorded"
        context_summary = "\n".join(agent_info.get("context", [])[:2]) or "No context recorded"
        
        # Format tool calls and extract errors (can be dicts or strings)
        raw_tool_calls = agent_info.get("tool_calls", [])[:5]
        tool_calls_strs = []
        tool_errors_list = []
        for tc in raw_tool_calls:
            if isinstance(tc, dict):
                tool_calls_strs.append(f"{tc.get('tool_name', 'unknown')}({str(tc.get('args', ''))[:100]})")
                # Check for errors in tool result
                result = tc.get('result', '')
                if isinstance(result, dict) and result.get('error'):
                    tool_errors_list.append(f"{tc.get('tool_name', 'unknown')}: {result.get('error')}")
                elif isinstance(result, str) and 'error' in result.lower():
                    tool_errors_list.append(f"{tc.get('tool_name', 'unknown')}: {result[:200]}")
            else:
                tool_calls_strs.append(str(tc))
        tool_calls = "\n".join(tool_calls_strs) or "No tool calls recorded"
        tool_errors = "\n".join(tool_errors_list) or "No errors"
        
        # Extract YAML-aware fields
        agent_goal = "Complete the assigned task effectively"
        task_description = "Not specified"
        expected_output = "Not specified"
        
        if yaml_info:
            agent_map = yaml_info.get("agent_map", {})
            yaml_key = agent_map.get(agent_name, agent_name)
            roles = yaml_info.get("roles", {})
            
            if yaml_key in roles:
                role_data = roles[yaml_key]
                agent_goal = role_data.get("goal", agent_goal)
                
                # Get first task's description and expected_output
                tasks = role_data.get("tasks", {})
                if tasks:
                    first_task = list(tasks.values())[0]
                    if isinstance(first_task, dict):
                        task_description = first_task.get("description", task_description)[:500]
                        expected_output = first_task.get("expected_output", expected_output)[:300]
        
        prompt = self.PROMPT_TEMPLATE.format(
            agent_name=agent_name,
            agent_goal=agent_goal[:200],
            task_description=task_description[:500],
            expected_output=expected_output[:300],
            input_text=input_text[:500],
            input_tokens=agent_info.get("prompt_tokens", 0),
            context_summary=context_summary[:1000],
            output_tokens=agent_info.get("completion_tokens", 0),
            output=output[:1000],
            tool_calls=tool_calls[:300],
            tool_errors=tool_errors[:500],
        )
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            response_text = response.choices[0].message.content or ""
            return self._parse_response(response_text, agent_name, agent_info)
            
        except Exception as e:
            logger.warning(f"Judge failed for {agent_name}: {e}")
            return ContextEffectivenessScore(
                agent_name=agent_name,
                task_achievement_score=5.0,
                context_utilization_score=5.0,
                output_quality_score=5.0,
                overall_score=5.0,
                reasoning=f"Judging error: {str(e)}",
                input_tokens=agent_info.get("prompt_tokens", 0),
                output_tokens=agent_info.get("completion_tokens", 0),
            )
    
    def _parse_response(
        self,
        response_text: str,
        agent_name: str,
        agent_info: Dict[str, Any],
    ) -> ContextEffectivenessScore:
        """Parse LLM response into ContextEffectivenessScore."""
        task_score = 5.0
        context_score = 5.0
        quality_score = 5.0
        instruction_score = 5.0
        hallucination_score = 10.0  # Default to no hallucination
        error_score = 10.0  # Default to good error handling
        reasoning = "Unable to parse response"
        suggestions: List[str] = []
        
        lines = response_text.strip().split('\n')
        in_suggestions = False
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('TASK_SCORE:'):
                try:
                    task_score = float(line.replace('TASK_SCORE:', '').strip())
                    task_score = max(1.0, min(10.0, task_score))
                except ValueError:
                    pass
            
            elif line.startswith('CONTEXT_SCORE:'):
                try:
                    context_score = float(line.replace('CONTEXT_SCORE:', '').strip())
                    context_score = max(1.0, min(10.0, context_score))
                except ValueError:
                    pass
            
            elif line.startswith('QUALITY_SCORE:'):
                try:
                    quality_score = float(line.replace('QUALITY_SCORE:', '').strip())
                    quality_score = max(1.0, min(10.0, quality_score))
                except ValueError:
                    pass
            
            elif line.startswith('INSTRUCTION_SCORE:'):
                try:
                    instruction_score = float(line.replace('INSTRUCTION_SCORE:', '').strip())
                    instruction_score = max(1.0, min(10.0, instruction_score))
                except ValueError:
                    pass
            
            elif line.startswith('HALLUCINATION_SCORE:'):
                try:
                    hallucination_score = float(line.replace('HALLUCINATION_SCORE:', '').strip())
                    hallucination_score = max(1.0, min(10.0, hallucination_score))
                except ValueError:
                    pass
            
            elif line.startswith('ERROR_SCORE:'):
                try:
                    error_score = float(line.replace('ERROR_SCORE:', '').strip())
                    error_score = max(1.0, min(10.0, error_score))
                except ValueError:
                    pass
            
            elif line.startswith('REASONING:'):
                reasoning = line.replace('REASONING:', '').strip()
            
            elif line.startswith('SUGGESTIONS:'):
                in_suggestions = True
            
            elif in_suggestions and line.startswith('-'):
                suggestion = line.lstrip('- ').strip()
                if suggestion:
                    suggestions.append(suggestion)
        
        # Calculate overall score including new criteria
        overall_score = (task_score + context_score + quality_score + instruction_score + hallucination_score + error_score) / 6
        
        return ContextEffectivenessScore(
            agent_name=agent_name,
            task_achievement_score=task_score,
            context_utilization_score=context_score,
            output_quality_score=quality_score,
            overall_score=round(overall_score, 2),
            reasoning=reasoning,
            suggestions=suggestions,
            input_tokens=agent_info.get("prompt_tokens", 0),
            output_tokens=agent_info.get("completion_tokens", 0),
            instruction_following_score=instruction_score,
            hallucination_score=hallucination_score,
            error_handling_score=error_score,
        )
    
    def judge_trace(
        self,
        events: List[Any],
        session_id: str = "",
        yaml_file: Optional[str] = None,
        evaluate_tools: bool = True,
        evaluate_context_flow: bool = True,
    ) -> JudgeReport:
        """
        Judge all agents in a trace with YAML-aware evaluation.
        
        Args:
            events: List of trace events
            session_id: Session identifier
            yaml_file: Optional path to YAML file for context-aware evaluation
            evaluate_tools: Whether to evaluate individual tool calls
            evaluate_context_flow: Whether to evaluate context flow between agents
            
        Returns:
            JudgeReport with all agent scores, tool evaluations, and recommendations
        """
        agent_data = self._extract_agent_data(events)
        
        # Load YAML info if provided
        yaml_info = None
        if yaml_file:
            yaml_info = _detect_yaml_structure(yaml_file)
        
        # Detect content loss
        content_loss_detected, content_loss_details = self._detect_content_loss(events)
        
        # Evaluate tool calls if enabled
        tool_evaluations_by_agent: Dict[str, List[ToolEvaluation]] = {}
        if evaluate_tools:
            tool_events = self._extract_tool_events(events)
            for tool_event in tool_events:
                agent_name = tool_event.get("agent_name", "unknown")
                tool_eval = self._evaluate_tool_call(tool_event)
                if agent_name not in tool_evaluations_by_agent:
                    tool_evaluations_by_agent[agent_name] = []
                tool_evaluations_by_agent[agent_name].append(tool_eval)
        
        agent_scores: List[ContextEffectivenessScore] = []
        agent_order = list(agent_data.keys())
        
        for agent_name, agent_info in agent_data.items():
            score = self._judge_agent(agent_name, agent_info, yaml_info)
            # Add tool evaluations to agent score
            score.tool_evaluations = tool_evaluations_by_agent.get(agent_name, [])
            agent_scores.append(score)
        
        # Evaluate context flow between agents
        context_flow_evaluations = []
        if evaluate_context_flow and len(agent_order) >= 2:
            context_flow_evaluations = self._evaluate_context_flow(events, agent_order)
        
        # Calculate overall score
        if agent_scores:
            overall_score = sum(s.overall_score for s in agent_scores) / len(agent_scores)
        else:
            overall_score = 0.0
        
        # Generate summary and recommendations
        summary = self._generate_summary(agent_scores)
        recommendations = self._generate_recommendations(agent_scores)
        
        # Add content loss warnings to recommendations
        if content_loss_detected:
            recommendations.insert(0, "⚠️ CONTENT LOSS DETECTED: Some tool results or LLM responses were truncated")
            for detail in content_loss_details[:3]:
                recommendations.append(f"  - {detail}")
        
        # Calculate metrics
        total_input_tokens = sum(s.input_tokens for s in agent_scores)
        total_output_tokens = sum(s.output_tokens for s in agent_scores)
        
        # Calculate tool evaluation metrics
        total_tool_calls = sum(len(evals) for evals in tool_evaluations_by_agent.values())
        truncated_tool_calls = sum(
            1 for evals in tool_evaluations_by_agent.values()
            for e in evals if e.was_truncated
        )
        
        report = JudgeReport(
            session_id=session_id,
            timestamp=datetime.utcnow().isoformat(),
            total_agents=len(agent_scores),
            overall_score=round(overall_score, 2),
            agent_scores=agent_scores,
            summary=summary,
            recommendations=recommendations,
            metrics={
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "total_tool_calls": total_tool_calls,
                "truncated_tool_calls": truncated_tool_calls,
            },
            context_flow_evaluations=context_flow_evaluations,
            content_loss_detected=content_loss_detected,
            content_loss_details=content_loss_details,
        )
        
        # Save report
        self._save_report(report)
        
        return report
    
    def _generate_summary(self, scores: List[ContextEffectivenessScore]) -> str:
        """Generate a summary of the evaluation."""
        if not scores:
            return "No agents to evaluate."
        
        avg_task = sum(s.task_achievement_score for s in scores) / len(scores)
        avg_context = sum(s.context_utilization_score for s in scores) / len(scores)
        avg_quality = sum(s.output_quality_score for s in scores) / len(scores)
        
        return (
            f"Evaluated {len(scores)} agents. "
            f"Average scores: Task={avg_task:.1f}/10, Context={avg_context:.1f}/10, Quality={avg_quality:.1f}/10"
        )
    
    def _generate_recommendations(self, scores: List[ContextEffectivenessScore]) -> List[str]:
        """Generate recommendations based on scores."""
        recommendations = []
        
        for score in scores:
            if score.task_achievement_score < 6:
                recommendations.append(f"{score.agent_name}: Improve task completion - {score.reasoning}")
            if score.context_utilization_score < 6:
                recommendations.append(f"{score.agent_name}: Better utilize provided context")
            if score.output_quality_score < 6:
                recommendations.append(f"{score.agent_name}: Improve output quality")
        
        # Add suggestions from individual scores
        for score in scores:
            for suggestion in score.suggestions[:2]:  # Limit to 2 per agent
                recommendations.append(f"{score.agent_name}: {suggestion}")
        
        return recommendations[:10]  # Limit total recommendations
    
    def _save_report(self, report: JudgeReport) -> Path:
        """Save report to disk."""
        filename = f"judge-{report.session_id}-{report.timestamp[:10]}.json"
        filepath = self.reports_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        
        return filepath
    
    def load_report(self, session_id: str) -> Optional[JudgeReport]:
        """Load a saved report by session ID."""
        for filepath in self.reports_dir.glob(f"judge-{session_id}*.json"):
            with open(filepath) as f:
                data = json.load(f)
                return JudgeReport.from_dict(data)
        return None
    
    def list_reports(self, limit: int = 10) -> List[Path]:
        """List recent judge reports."""
        reports = sorted(self.reports_dir.glob("judge-*.json"), reverse=True)
        return reports[:limit]


def format_judge_report(report: JudgeReport) -> str:
    """Format a judge report for display."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  LLM JUDGE REPORT: {report.session_id}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Timestamp: {report.timestamp}")
    lines.append(f"  Agents Evaluated: {report.total_agents}")
    lines.append(f"  Overall Score: {report.overall_score}/10")
    
    # Show content loss warning if detected
    if report.content_loss_detected:
        lines.append("")
        lines.append("  ⚠️  CONTENT LOSS DETECTED:")
        for detail in report.content_loss_details[:3]:
            lines.append(f"    - {detail}")
    
    lines.append("")
    lines.append("  AGENT SCORES:")
    
    for score in report.agent_scores:
        lines.append(f"    {score.agent_name}:")
        lines.append(f"      Task Achievement: {score.task_achievement_score}/10")
        lines.append(f"      Context Utilization: {score.context_utilization_score}/10")
        lines.append(f"      Output Quality: {score.output_quality_score}/10")
        lines.append(f"      Instruction Following: {score.instruction_following_score}/10")
        lines.append(f"      Hallucination: {score.hallucination_score}/10")
        lines.append(f"      Error Handling: {score.error_handling_score}/10")
        lines.append(f"      Overall: {score.overall_score}/10")
        lines.append(f"      Reasoning: {score.reasoning[:100]}...")
        
        # Show tool evaluations if any
        if score.tool_evaluations:
            lines.append(f"      Tool Calls ({len(score.tool_evaluations)}):")
            for te in score.tool_evaluations[:3]:
                truncated_marker = " [TRUNCATED]" if te.was_truncated else ""
                lines.append(f"        - {te.tool_name}: completeness={te.result_completeness}/10{truncated_marker}")
                if te.issues:
                    lines.append(f"          Issues: {', '.join(te.issues[:2])}")
        lines.append("")
    
    # Show context flow evaluations
    if report.context_flow_evaluations:
        lines.append("  CONTEXT FLOW:")
        for flow in report.context_flow_evaluations:
            loss_marker = " ⚠️" if flow.content_loss_detected else " ✓"
            lines.append(f"    {flow.from_agent} → {flow.to_agent}: {flow.context_passed_score:.1f}/10{loss_marker}")
            if flow.content_loss_detected and flow.lost_content_summary:
                lines.append(f"      {flow.lost_content_summary}")
        lines.append("")
    
    lines.append("  SUMMARY:")
    lines.append(f"    {report.summary}")
    lines.append("")
    
    # Show metrics
    if report.metrics:
        lines.append("  METRICS:")
        lines.append(f"    Total Tokens: {report.metrics.get('total_tokens', 0):,}")
        if report.metrics.get('total_tool_calls', 0) > 0:
            lines.append(f"    Tool Calls: {report.metrics.get('total_tool_calls', 0)} ({report.metrics.get('truncated_tool_calls', 0)} truncated)")
        lines.append("")
    
    if report.recommendations:
        lines.append("  RECOMMENDATIONS:")
        for rec in report.recommendations[:5]:
            lines.append(f"    - {rec}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def _calculate_dynamic_confidence(score: float, fix_type: str) -> float:
    """
    Calculate dynamic confidence based on score severity and fix type.
    
    Lower scores = higher confidence that fix is needed.
    Different fix types have different base confidence levels.
    
    Args:
        score: The score (1-10) that triggered this fix
        fix_type: Type of fix being suggested
        
    Returns:
        Confidence value between 0.0 and 1.0
    """
    # Base confidence by fix type
    base_confidence = {
        "append_instruction": 0.6,
        "add_expected_output": 0.7,
        "modify_context_config": 0.5,
        "add_goal": 0.8,
        "suggestion": 0.4,
    }.get(fix_type, 0.5)
    
    # Adjust based on score severity
    # Score 1-3: Very low, high confidence fix is needed (+0.3)
    # Score 4-5: Low, medium confidence (+0.15)
    # Score 6-7: Borderline, lower confidence (+0.0)
    if score <= 3:
        severity_boost = 0.3
    elif score <= 5:
        severity_boost = 0.15
    else:
        severity_boost = 0.0
    
    # Cap at 0.95
    return min(0.95, base_confidence + severity_boost)


def _detect_yaml_structure(yaml_file: str) -> dict:
    """
    Detect the YAML structure to generate correct paths.
    
    Returns dict with:
        - structure: 'recipe' (roles/tasks) or 'simple' (agents) or 'workflow' (steps)
        - agent_map: mapping of agent display names to YAML keys
    """
    from pathlib import Path
    import yaml
    
    result = {"structure": "simple", "agent_map": {}, "roles": {}}
    
    try:
        yaml_path = Path(yaml_file)
        if not yaml_path.exists():
            return result
        
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        
        if not data:
            return result
        
        # Detect recipe structure (roles with tasks)
        if "roles" in data:
            result["structure"] = "recipe"
            for role_key, role_data in data.get("roles", {}).items():
                if isinstance(role_data, dict):
                    display_name = role_data.get("role", role_key)
                    result["agent_map"][display_name] = role_key
                    result["roles"][role_key] = role_data
        
        # Detect simple agents structure
        elif "agents" in data:
            result["structure"] = "simple"
            agents_data = data.get("agents", {})
            # Handle both dict and list formats
            if isinstance(agents_data, dict):
                # Dict format: agents: {agent_key: {role: "Name", ...}}
                for agent_key, agent_data in agents_data.items():
                    if isinstance(agent_data, dict):
                        display_name = agent_data.get("role", agent_key)
                        result["agent_map"][display_name] = agent_key
                        result["roles"][agent_key] = agent_data
            elif isinstance(agents_data, list):
                # List format: agents: [{name: "Name", ...}]
                for agent in agents_data:
                    if isinstance(agent, dict):
                        name = agent.get("name", agent.get("role", ""))
                        result["agent_map"][name] = name
        
        # Detect workflow steps structure
        if "steps" in data:
            result["has_steps"] = True
        
    except Exception:
        pass
    
    return result


def generate_plan_from_report(report: JudgeReport, yaml_file: str, goal: Optional[str] = None) -> "JudgePlan":
    """
    Generate a JudgePlan with actionable fixes from a JudgeReport.
    
    Args:
        report: The JudgeReport from judge_trace()
        yaml_file: Path to the YAML file to fix
        goal: Optional goal for the workflow
        
    Returns:
        JudgePlan with actionable fixes
    """
    from .plan import JudgePlan, ActionableFix, generate_fix_id
    
    # Detect YAML structure to generate correct paths
    yaml_info = _detect_yaml_structure(yaml_file)
    structure = yaml_info.get("structure", "simple")
    agent_map = yaml_info.get("agent_map", {})
    
    fixes = []
    
    for score in report.agent_scores:
        # Map agent display name to YAML key
        yaml_key = agent_map.get(score.agent_name, score.agent_name)
        
        # Generate correct path based on YAML structure
        if structure == "recipe":
            # Recipe structure: roles.{key}.tasks.{first_task}.description
            role_data = yaml_info.get("roles", {}).get(yaml_key, {})
            tasks = role_data.get("tasks", {})
            first_task = list(tasks.keys())[0] if tasks else "task"
            base_path = f"roles.{yaml_key}.tasks.{first_task}"
            instruction_path = f"{base_path}.description"
            output_path = f"{base_path}.expected_output"
        else:
            # Simple structure: agents.{name}
            base_path = f"agents.{yaml_key}"
            # Check if this agent has backstory (dict format) or instructions
            agent_data = yaml_info.get("roles", {}).get(yaml_key, {})
            if agent_data.get("backstory"):
                instruction_path = f"{base_path}.backstory"
            else:
                instruction_path = f"{base_path}.goal"  # Fallback to goal
            output_path = f"{base_path}.expected_output"
        
        # Task achievement issues - append suggestion to description
        if score.task_achievement_score < 6:
            fix = ActionableFix(
                fix_id=generate_fix_id(score.agent_name, "append_instruction", instruction_path),
                agent_name=score.agent_name,
                fix_type="append_instruction",
                target_path=instruction_path,
                current_value=None,
                suggested_value=f"\n\nADDITIONAL GUIDANCE: {score.reasoning}. Ensure task completion with specific success criteria.",
                reasoning=f"Task achievement score is low ({score.task_achievement_score}/10). {score.reasoning}",
                confidence=_calculate_dynamic_confidence(score.task_achievement_score, "append_instruction"),
                priority="high" if score.task_achievement_score < 4 else "medium",
            )
            fixes.append(fix)
        
        # Context utilization issues
        if score.context_utilization_score < 6:
            fix = ActionableFix(
                fix_id=generate_fix_id(score.agent_name, "modify_context_config", "context"),
                agent_name=score.agent_name,
                fix_type="modify_context_config",
                target_path="context",
                current_value=None,
                suggested_value="Ensure previous_output is properly formatted and contains required data.",
                reasoning=f"Context utilization score is low ({score.context_utilization_score}/10). Agent may not be receiving or using context effectively.",
                confidence=_calculate_dynamic_confidence(score.context_utilization_score, "modify_context_config"),
                priority="medium",
            )
            fixes.append(fix)
        
        # Output quality issues
        if score.output_quality_score < 6:
            fix = ActionableFix(
                fix_id=generate_fix_id(score.agent_name, "add_expected_output", output_path),
                agent_name=score.agent_name,
                fix_type="add_expected_output",
                target_path=output_path,
                current_value=None,
                suggested_value="Add clear expected_output format with JSON schema or example.",
                reasoning=f"Output quality score is low ({score.output_quality_score}/10). Define expected output format.",
                confidence=_calculate_dynamic_confidence(score.output_quality_score, "add_expected_output"),
                priority="medium",
            )
            fixes.append(fix)
        
        # Add fixes from suggestions - append to description
        # Use overall score for suggestion confidence
        for i, suggestion in enumerate(score.suggestions[:2]):
            fix = ActionableFix(
                fix_id=generate_fix_id(score.agent_name, "suggestion", f"suggestion_{i}"),
                agent_name=score.agent_name,
                fix_type="append_instruction",
                target_path=instruction_path,
                current_value=None,
                suggested_value=f"\n\nIMPROVEMENT: {suggestion}",
                reasoning=f"Suggestion from LLM judge: {suggestion}",
                confidence=_calculate_dynamic_confidence(score.overall_score, "suggestion"),
                priority="low",
            )
            fixes.append(fix)
    
    # Add goal if not present and score is low
    if report.overall_score < 7 and goal is None:
        fix = ActionableFix(
            fix_id=generate_fix_id("workflow", "add_goal", "goal"),
            agent_name="workflow",
            fix_type="add_goal",
            target_path="goal",
            current_value=None,
            suggested_value="Define a clear, measurable goal for this workflow",
            reasoning="Adding a goal helps evaluate task achievement more accurately.",
            confidence=0.8,
            priority="medium",
        )
        fixes.append(fix)
    
    return JudgePlan(
        trace_id=report.session_id,
        yaml_file=yaml_file,
        goal=goal,
        overall_score=report.overall_score,
        fixes=fixes,
    )
