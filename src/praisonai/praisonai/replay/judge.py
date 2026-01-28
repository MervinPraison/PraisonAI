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


def _read_image_for_judge(image_path: str, model: str = "gpt-4o-mini") -> str:
    """
    Read and describe an image for judge context.
    
    Uses vision LLM to describe the image content so the judge can
    validate if agent outputs match the actual image.
    
    Args:
        image_path: Local file path or URL to the image
        model: Vision-capable model to use
        
    Returns:
        Description of the image content
    """
    import base64
    import os
    
    try:
        import litellm
        
        # Prepare image content
        if image_path.startswith(('http://', 'https://')):
            # URL - pass directly
            image_content = {
                "type": "image_url",
                "image_url": {"url": image_path}
            }
        elif os.path.exists(image_path):
            # Local file - encode as base64
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Detect mime type
            ext = os.path.splitext(image_path)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif',
                '.webp': 'image/webp', '.bmp': 'image/bmp'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image_data}"}
            }
        else:
            return f"[Image not found: {image_path}]"
        
        # Use vision model to describe the image
        response = litellm.completion(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in detail. Include: main subject, colors, text visible, key elements, and overall composition. Be factual and specific."},
                    image_content
                ]
            }],
            max_tokens=500,
        )
        
        description = response.choices[0].message.content or ""
        return f"[IMAGE DESCRIPTION: {description}]"
        
    except Exception as e:
        logger.warning(f"Failed to read image for judge: {e}")
        return f"[Failed to read image: {str(e)[:100]}]"


def _crawl_url_for_judge(url: str) -> str:
    """
    Crawl a URL to get content for judge context.
    
    Uses the web_crawl tool to extract content so the judge can
    validate if agent outputs match the actual URL content.
    
    Args:
        url: URL to crawl
        
    Returns:
        Extracted content from the URL (truncated)
    """
    try:
        # Try to use the web_crawl tool
        from praisonaiagents.tools import web_crawl
        
        result = web_crawl(url)
        
        if isinstance(result, dict):
            if result.get('error'):
                return f"[URL crawl error: {result.get('error')}]"
            content = result.get('content', '')
            title = result.get('title', '')
            provider = result.get('provider', 'unknown')
            
            # Truncate content for judge context
            if len(content) > 3000:
                content = content[:3000] + "... [truncated]"
            
            return f"[URL CONTENT (via {provider})]\nTitle: {title}\n\n{content}"
        
        return f"[URL content: {str(result)[:3000]}]"
        
    except ImportError:
        # Fallback to basic HTTP fetch
        try:
            import urllib.request
            import re
            
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read().decode('utf-8', errors='ignore')
            
            # Basic HTML to text
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<[^>]+>', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()
            
            if len(content) > 3000:
                content = content[:3000] + "... [truncated]"
            
            return f"[URL CONTENT (via urllib)]\n{content}"
            
        except Exception as e:
            return f"[Failed to crawl URL: {str(e)[:100]}]"
    except Exception as e:
        logger.warning(f"Failed to crawl URL for judge: {e}")
        return f"[Failed to crawl URL: {str(e)[:100]}]"


def _smart_truncate(text: str, max_chars: int = 1000, preserve_structure: bool = True) -> str:
    """
    Smart truncation that preserves key information for LLM evaluation.
    
    For large outputs exceeding LLM context limits, this function:
    1. Preserves the beginning (usually contains key info)
    2. Preserves the ending (usually contains conclusions)
    3. Adds a summary of what was truncated
    
    Args:
        text: Text to truncate
        max_chars: Maximum characters to keep
        preserve_structure: If True, try to preserve JSON/list structure
        
    Returns:
        Truncated text with truncation indicator
    """
    if not text or len(text) <= max_chars:
        return text
    
    # Calculate portions: 60% beginning, 30% ending, 10% for truncation message
    begin_chars = int(max_chars * 0.6)
    end_chars = int(max_chars * 0.3)
    
    beginning = text[:begin_chars]
    ending = text[-end_chars:]
    
    # Count what was truncated
    truncated_chars = len(text) - begin_chars - end_chars
    truncated_lines = text[begin_chars:-end_chars].count('\n') if end_chars > 0 else text[begin_chars:].count('\n')
    
    # Build truncation message
    truncation_msg = f"\n\n[... TRUNCATED {truncated_chars:,} chars, ~{truncated_lines} lines ...]\n\n"
    
    return beginning + truncation_msg + ending


def _estimate_tokens(text: str) -> int:
    """Rough token estimation (4 chars per token average)."""
    return len(text) // 4


def _llm_summarize(
    text: str,
    max_chars: int = 2000,
    model: str = "gpt-4o-mini",
    context: str = "tool result",
) -> str:
    """
    Use LLM to summarize large content before truncation.
    
    Priority order for handling large content:
    1. If content fits, return as-is
    2. Try LLM summarization to preserve key information
    3. Fall back to smart truncation if LLM fails
    
    Args:
        text: Text to summarize
        max_chars: Target maximum characters for summary
        model: LLM model to use for summarization
        context: Context description (e.g., "tool result", "agent output")
        
    Returns:
        Summarized text or original if small enough
    """
    if not text or len(text) <= max_chars:
        return text
    
    try:
        import litellm
        
        prompt = f"""Summarize this {context} concisely while preserving ALL key information, facts, and data points.
Keep the summary under {max_chars} characters. Preserve any lists, numbers, URLs, and specific details.

CONTENT TO SUMMARIZE:
{text[:20000]}

SUMMARY (preserve all key facts and data):"""
        
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_chars // 3,  # ~3 chars per token
        )
        
        summary = response.choices[0].message.content or ""
        if summary and len(summary) < len(text):
            return f"[LLM SUMMARY of {len(text):,} chars]\n{summary}"
        
    except Exception as e:
        logger.debug(f"LLM summarization failed, falling back to truncation: {e}")
    
    # Fallback to smart truncation
    return _smart_truncate(text, max_chars)


def _is_content_truncated(text: str) -> bool:
    """
    Detect if content was actually truncated vs smart-truncated with preserved info.
    
    Smart truncation (showing first/last portions) is NOT considered problematic
    because it preserves key information from both ends.
    
    Args:
        text: Text to check
        
    Returns:
        True if content appears to be hard-truncated (info lost)
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Smart truncation markers - these PRESERVE info, not a problem
    smart_markers = [
        "showing first/last portions",  # New smart truncation format
        "[llm summary of",  # LLM summarized content preserves info
        "chars, showing",  # Smart truncation indicator
    ]
    
    for marker in smart_markers:
        if marker in text_lower:
            return False  # Smart truncation is OK
    
    # Hard truncation markers - these LOSE info, is a problem
    hard_truncation_markers = [
        "...[truncated]",
        "[truncated]",
        "[TRUNCATED",
        "... TRUNCATED",
        "[output truncated]",
        "(truncated)",
        "... (truncated)",
    ]
    
    for marker in hard_truncation_markers:
        if marker.lower() in text_lower:
            return True  # Hard truncation detected
    
    # Check for incomplete JSON/structure (only if very short)
    stripped = text.strip()
    if len(stripped) < 500:  # Only check short content
        if stripped.startswith('{') and not stripped.endswith('}'):
            return True
        if stripped.startswith('[') and not stripped.endswith(']'):
            return True
    
    return False


def chunk_split(
    text: str,
    max_chars: int = 8000,
    max_chunks: int = 5,
    overlap: int = 200,
    include_metadata: bool = False,
) -> List:
    """
    Split large text into chunks for separate evaluation.
    
    Unlike truncation which loses information, chunking preserves ALL content
    by splitting it into multiple evaluable pieces.
    
    Args:
        text: Text to split into chunks
        max_chars: Maximum characters per chunk
        max_chunks: Maximum number of chunks to create
        overlap: Number of characters to overlap between chunks for context
        include_metadata: If True, return list of dicts with metadata
        
    Returns:
        List of text chunks (or dicts with metadata if include_metadata=True)
    """
    if not text or len(text) <= max_chars:
        if include_metadata:
            return [{"content": text, "chunk_index": 0, "total_chunks": 1}]
        return [text]
    
    chunks = []
    start = 0
    chunk_index = 0
    
    while start < len(text) and chunk_index < max_chunks:
        # Calculate end position
        end = min(start + max_chars, len(text))
        
        # Try to find a good break point (paragraph, sentence, or word boundary)
        if end < len(text):
            # Look for paragraph break first
            para_break = text.rfind('\n\n', start, end)
            if para_break > start + max_chars // 2:
                end = para_break + 2
            else:
                # Look for sentence break
                for sep in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + max_chars // 2:
                        end = sent_break + len(sep)
                        break
                else:
                    # Look for word break
                    word_break = text.rfind(' ', start, end)
                    if word_break > start + max_chars // 2:
                        end = word_break + 1
        
        chunk_text = text[start:end].strip()
        
        if chunk_text:
            if include_metadata:
                chunks.append({
                    "content": chunk_text,
                    "chunk_index": chunk_index,
                    "total_chunks": -1,  # Will be updated after
                    "start_pos": start,
                    "end_pos": end,
                })
            else:
                chunks.append(chunk_text)
            chunk_index += 1
        
        # Move start position, accounting for overlap
        start = end - overlap if overlap > 0 and end < len(text) else end
    
    # If we hit max_chunks but have remaining text, append it to last chunk
    if start < len(text) and chunks:
        remaining = text[start:].strip()
        if remaining:
            if include_metadata:
                chunks[-1]["content"] += "\n\n[CONTINUED...]\n" + remaining
                chunks[-1]["end_pos"] = len(text)
            else:
                chunks[-1] += "\n\n[CONTINUED...]\n" + remaining
    
    # Update total_chunks in metadata
    if include_metadata:
        for chunk in chunks:
            chunk["total_chunks"] = len(chunks)
    
    return chunks


def aggregate_chunk_scores(
    chunk_scores: List[Dict[str, Any]],
    strategy: str = "weighted_average",
) -> float:
    """
    Aggregate scores from multiple chunks into a single score.
    
    Strategies:
        - weighted_average: Weight by chunk size (default)
        - average: Simple average
        - min: Use minimum score (conservative)
        - max: Use maximum score (optimistic)
        - first_last: Average of first and last chunk
    
    Args:
        chunk_scores: List of dicts with 'score' and 'chunk_size' keys
        strategy: Aggregation strategy
        
    Returns:
        Aggregated score (1-10)
    """
    if not chunk_scores:
        return 5.0
    
    if len(chunk_scores) == 1:
        return chunk_scores[0].get("score", 5.0)
    
    scores = [cs.get("score", 5.0) for cs in chunk_scores]
    sizes = [cs.get("chunk_size", 1) for cs in chunk_scores]
    
    if strategy == "min":
        return min(scores)
    elif strategy == "max":
        return max(scores)
    elif strategy == "average":
        return sum(scores) / len(scores)
    elif strategy == "first_last":
        return (scores[0] + scores[-1]) / 2
    else:  # weighted_average (default)
        total_size = sum(sizes)
        if total_size == 0:
            return sum(scores) / len(scores)
        weighted_sum = sum(s * sz for s, sz in zip(scores, sizes))
        return weighted_sum / total_size


class ChunkedEvaluator:
    """
    Evaluator that handles large outputs by splitting into chunks.
    
    Instead of truncating large outputs (which loses information),
    this evaluator splits content into chunks, evaluates each separately,
    and aggregates the scores.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        max_tokens: int = 800,
        chunk_size: int = 8000,
        max_chunks: int = 5,
        overlap: int = 200,
        aggregation_strategy: str = "weighted_average",
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.chunk_size = chunk_size
        self.max_chunks = max_chunks
        self.overlap = overlap
        self.aggregation_strategy = aggregation_strategy
    
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
    
    def evaluate_chunk(
        self,
        chunk: str,
        chunk_index: int,
        total_chunks: int,
        prompt_template: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Evaluate a single chunk of content.
        
        Args:
            chunk: The chunk content to evaluate
            chunk_index: Index of this chunk (0-based)
            total_chunks: Total number of chunks
            prompt_template: Prompt template to use
            **kwargs: Additional template variables
            
        Returns:
            Dict with score and reasoning
        """
        litellm = self._get_litellm()
        
        # Add chunk context to the prompt
        chunk_context = f"\n[CHUNK {chunk_index + 1} of {total_chunks}]\n"
        if chunk_index > 0:
            chunk_context += "(This is a continuation of the previous content)\n"
        
        # Build prompt with chunk
        prompt = prompt_template.format(
            output=chunk_context + chunk,
            **kwargs,
        )
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            response_text = response.choices[0].message.content or ""
            return {
                "score": self._extract_score(response_text),
                "chunk_size": len(chunk),
                "chunk_index": chunk_index,
                "reasoning": response_text,
            }
            
        except Exception as e:
            logger.warning(f"Chunk evaluation failed: {e}")
            return {
                "score": 5.0,
                "chunk_size": len(chunk),
                "chunk_index": chunk_index,
                "reasoning": f"Evaluation error: {str(e)}",
            }
    
    def _extract_score(self, response_text: str) -> float:
        """Extract score from LLM response."""
        import re
        
        # Look for SCORE: pattern
        match = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)', response_text)
        if match:
            return max(1.0, min(10.0, float(match.group(1))))
        
        # Look for any number between 1-10
        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', response_text)
        for num in numbers:
            val = float(num)
            if 1 <= val <= 10:
                return val
        
        return 5.0
    
    def aggregate_scores(
        self,
        chunk_scores: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Aggregate scores from multiple chunks.
        
        Args:
            chunk_scores: List of chunk evaluation results
            
        Returns:
            Dict with aggregated score and combined reasoning
        """
        final_score = aggregate_chunk_scores(
            chunk_scores,
            strategy=self.aggregation_strategy,
        )
        
        # Combine reasoning from all chunks
        reasonings = []
        for cs in chunk_scores:
            if cs.get("reasoning"):
                reasonings.append(f"[Chunk {cs.get('chunk_index', 0) + 1}]: {cs.get('reasoning', '')[:200]}")
        
        return {
            "score": final_score,
            "chunk_count": len(chunk_scores),
            "chunk_scores": [cs.get("score", 5.0) for cs in chunk_scores],
            "reasoning": "\n".join(reasonings),
        }


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
    # Dynamic failure detection (determined by LLM, not hardcoded)
    failure_detected: bool = False  # Did LLM detect a task failure?
    failure_reason: str = ""  # LLM's explanation of why task failed
    
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
    # Enhanced fields for recipe-level evaluation
    recipe_goal: str = ""  # The overall recipe goal from YAML
    failures_detected: int = 0  # Count of agents with detected failures
    input_validation_issues: List[str] = field(default_factory=list)  # Unresolved inputs
    
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
            "recipe_goal": self.recipe_goal,
            "failures_detected": self.failures_detected,
            "input_validation_issues": self.input_validation_issues,
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
            recipe_goal=data.get("recipe_goal", ""),
            failures_detected=data.get("failures_detected", 0),
            input_validation_issues=data.get("input_validation_issues", []),
        )


class ContextEffectivenessJudge:
    """
    LLM-as-Judge for analyzing context/memory/knowledge effectiveness in agent traces.
    
    Modes:
    - context: Evaluates context flow between agents (default)
    - memory: Evaluates memory utilization (store/search effectiveness)
    - knowledge: Evaluates knowledge retrieval effectiveness
    
    DRY: Uses the same grading pattern with mode-specific prompts.
    """
    
    # Mode-specific prompt templates
    PROMPT_TEMPLATE_CONTEXT = """You are an expert evaluator for AI agent workflows. Analyze this agent's performance critically.

═══════════════════════════════════════════════════════════════════
RECIPE GOAL (The overall workflow objective - CRITICAL for evaluation):
{recipe_goal}

INPUT VALIDATION STATUS:
{input_validation_status}

ACTUAL INPUT CONTENT (Image/URL content the agent should have processed):
{input_content}
═══════════════════════════════════════════════════════════════════

AGENT: {agent_name}
AGENT GOAL: {agent_goal}
TASK DESCRIPTION: {task_description}
EXPECTED OUTPUT FORMAT: {expected_output}

═══════════════════════════════════════════════════════════════════
PREVIOUS AGENTS' PERFORMANCE (Context for this agent's evaluation):
{previous_steps_context}
═══════════════════════════════════════════════════════════════════

TASK/INPUT: {input_text}
CONTEXT RECEIVED (tokens: {input_tokens}):
{context_summary}

AGENT OUTPUT (tokens: {output_tokens}):
{output}

TOOL CALLS: {tool_calls}
TOOL ERRORS: {tool_errors}

═══════════════════════════════════════════════════════════════════
FAILURE DETECTION (CRITICAL - Analyze the output carefully):
You MUST determine if the agent FAILED its primary task. Look for:
- Agent explicitly stating it cannot access, read, or process required inputs
- Agent using fallback/sample/hypothetical data instead of real provided data
- Agent admitting inability to complete the requested action
- Output that doesn't match what was actually requested

If the agent failed to use the ACTUAL provided input and instead created
sample/hypothetical content, this is a TASK FAILURE regardless of output quality.
═══════════════════════════════════════════════════════════════════

Evaluate on these criteria:
1. TASK ACHIEVEMENT (1-10): Did the agent accomplish what it was asked to do based on the task description?
   - If agent failed to access/use required input: MAX 3/10
   - If agent used fallback/sample data instead of real input: MAX 3/10
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
FAILURE_DETECTED: [true/false] - Set to true if agent failed to complete primary task
FAILURE_REASON: [If FAILURE_DETECTED is true, explain why the task failed]
REASONING: [brief explanation of scores, referencing specific issues]
SUGGESTIONS:
- [specific, actionable improvement suggestion 1]
- [specific, actionable improvement suggestion 2]
"""

    PROMPT_TEMPLATE_MEMORY = """You are an expert evaluator for AI agent memory utilization. Analyze how well this agent uses memory.

AGENT: {agent_name}
AGENT GOAL: {agent_goal}

MEMORY OPERATIONS:
- Memory Stores: {memory_store_count}
- Memory Searches: {memory_search_count}
- Memory Store Details: {memory_store_details}
- Memory Search Details: {memory_search_details}

TASK/INPUT: {input_text}
AGENT OUTPUT: {output}

Evaluate on these memory-specific criteria:
1. RETRIEVAL_RELEVANCE (1-10): Did the agent search for relevant memories? Were queries well-formed?
2. STORAGE_QUALITY (1-10): Did the agent store useful information? Was content appropriate for memory?
3. RECALL_EFFECTIVENESS (1-10): Was retrieved memory actually used in the response?
4. MEMORY_EFFICIENCY (1-10): Was memory used efficiently? No redundant stores/searches?

Respond in this EXACT format:
RETRIEVAL_SCORE: [1-10]
STORAGE_SCORE: [1-10]
RECALL_SCORE: [1-10]
EFFICIENCY_SCORE: [1-10]
REASONING: [brief explanation of scores, referencing specific memory operations]
SUGGESTIONS:
- [specific, actionable improvement suggestion 1]
- [specific, actionable improvement suggestion 2]
"""

    PROMPT_TEMPLATE_KNOWLEDGE = """You are an expert evaluator for AI agent knowledge retrieval. Analyze how well this agent uses knowledge.

AGENT: {agent_name}
AGENT GOAL: {agent_goal}

KNOWLEDGE OPERATIONS:
- Knowledge Searches: {knowledge_search_count}
- Knowledge Adds: {knowledge_add_count}
- Search Details: {knowledge_search_details}
- Sources Used: {knowledge_sources}

TASK/INPUT: {input_text}
AGENT OUTPUT: {output}

Evaluate on these knowledge-specific criteria:
1. RETRIEVAL_ACCURACY (1-10): Did the agent find relevant documents? Were queries effective?
2. SOURCE_COVERAGE (1-10): Were all relevant sources used? Any important sources missed?
3. CITATION_QUALITY (1-10): Were sources properly attributed? Was information accurately represented?
4. KNOWLEDGE_INTEGRATION (1-10): Was retrieved knowledge well-integrated into the response?

Respond in this EXACT format:
RETRIEVAL_SCORE: [1-10]
COVERAGE_SCORE: [1-10]
CITATION_SCORE: [1-10]
INTEGRATION_SCORE: [1-10]
REASONING: [brief explanation of scores, referencing specific knowledge operations]
SUGGESTIONS:
- [specific, actionable improvement suggestion 1]
- [specific, actionable improvement suggestion 2]
"""

    # Backward compatibility alias
    PROMPT_TEMPLATE = PROMPT_TEMPLATE_CONTEXT
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 800,
        reports_dir: Optional[Path] = None,
        mode: str = "context",
        chunked: bool = False,
        auto_chunk: bool = False,
        chunk_size: int = 8000,
        max_chunks: int = 5,
        chunk_overlap: int = 200,
        aggregation_strategy: str = "weighted_average",
    ):
        """
        Initialize the judge.
        
        Args:
            model: LLM model for judging (default: gpt-4o-mini)
            temperature: LLM temperature
            max_tokens: Max tokens for LLM response
            reports_dir: Directory to save judge reports
            mode: Evaluation mode - 'context', 'memory', or 'knowledge'
            chunked: If True, always use chunked evaluation for large outputs
            auto_chunk: If True, automatically decide if chunking is needed based on content size
            chunk_size: Maximum characters per chunk (default: 8000, optimized for 128K context models)
            max_chunks: Maximum number of chunks per agent (default: 5, allows up to 40K chars total)
            chunk_overlap: Characters to overlap between chunks (default: 200)
            aggregation_strategy: How to aggregate chunk scores
                - 'weighted_average': Weight by chunk size (default)
                - 'average': Simple average
                - 'min': Use minimum score (conservative)
                - 'max': Use maximum score (optimistic)
        """
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reports_dir = reports_dir or Path.home() / ".praison" / "judge_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        
        # Chunked evaluation settings
        self.chunked = chunked
        self.auto_chunk = auto_chunk
        self.chunk_size = chunk_size
        self.max_chunks = max_chunks
        self.chunk_overlap = chunk_overlap
        self.aggregation_strategy = aggregation_strategy
        
        # Select prompt template based on mode
        if mode == "memory":
            self.prompt_template = self.PROMPT_TEMPLATE_MEMORY
        elif mode == "knowledge":
            self.prompt_template = self.PROMPT_TEMPLATE_KNOWLEDGE
        else:
            self.prompt_template = self.PROMPT_TEMPLATE_CONTEXT
    
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
        """Extract per-agent data from trace events.
        
        Only creates agent entries for actual agents (those with agent_start events),
        not for memory/knowledge event sources which may have different identifiers.
        """
        agent_data: Dict[str, Dict[str, Any]] = {}
        
        # First pass: identify actual agents from agent_start events
        actual_agents = set()
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                agent_name = event.agent_name
            else:
                event_type = event.get('event_type', '')
                agent_name = event.get('agent_name')
            
            if event_type == "agent_start" and agent_name:
                actual_agents.add(agent_name)
        
        # Second pass: extract data only for actual agents
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
            
            # Skip events from non-agent sources (e.g., memory user_id, knowledge sources)
            # Only process events from actual agents identified by agent_start
            if agent_name not in actual_agents:
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
                # Use intelligent truncation detection (consistent with other code paths)
                was_truncated = _is_content_truncated(str(result)) if result else False
                
                # Find matching tool call and update result
                for tc in reversed(agent_data[agent_name]["tool_calls"]):
                    if isinstance(tc, dict) and tc.get("tool_name") == tool_name and tc.get("result") is None:
                        tc["result"] = result
                        tc["was_truncated"] = was_truncated
                        break
        
        return agent_data
    
    def _extract_memory_events(self, events: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Extract memory events (store/search) per agent from trace.
        
        Memory events may be attributed to FileMemory user_id instead of agent name.
        This method associates memory events with the nearest agent:
        - If within agent_start/agent_end: use that agent
        - If before first agent_start: use the next agent
        - If after agent_end: use the previous or next agent
        """
        memory_data: Dict[str, Dict[str, Any]] = {}
        
        # First pass: build list of agent spans (start_seq, end_seq, agent_name)
        agent_spans = []
        current_agent = None
        current_start = None
        max_seq = 0
        
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                agent_name = event.agent_name
                seq_num = getattr(event, 'sequence_num', 0)
            else:
                event_type = event.get('event_type', '')
                agent_name = event.get('agent_name')
                seq_num = event.get('sequence_num', 0)
            
            max_seq = max(max_seq, seq_num)
            
            if event_type == "agent_start" and agent_name:
                current_agent = agent_name
                current_start = seq_num
            elif event_type == "agent_end" and current_agent:
                agent_spans.append((current_start, seq_num, current_agent))
                current_agent = None
                current_start = None
        
        # Helper to find the best agent for a sequence number
        def find_agent_for_seq(seq: int) -> Optional[str]:
            # Check if within any span
            for start, end, name in agent_spans:
                if start <= seq <= end:
                    return name
            
            # Find nearest span (prefer next agent for pre-agent events)
            nearest_agent = None
            nearest_dist = float('inf')
            
            for start, end, name in agent_spans:
                # Distance to span start (for events before agent)
                if seq < start:
                    dist = start - seq
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_agent = name
                # Distance to span end (for events after agent)
                elif seq > end:
                    dist = seq - end
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_agent = name
            
            return nearest_agent
        
        # Second pass: extract memory events and associate with nearest agent
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                event_agent_name = event.agent_name or "unknown"
                data = event.data or {}
                seq_num = getattr(event, 'sequence_num', 0)
            else:
                event_type = event.get('event_type', '')
                event_agent_name = event.get('agent_name', 'unknown')
                data = event.get('data', {})
                seq_num = event.get('sequence_num', 0)
            
            if event_type not in ("memory_store", "memory_search"):
                continue
            
            # Find the best agent for this memory event
            agent_name = find_agent_for_seq(seq_num)
            
            # Fallback to event's agent_name if no agent found
            if not agent_name:
                agent_name = event_agent_name
            
            if agent_name not in memory_data:
                memory_data[agent_name] = {
                    "stores": [],
                    "searches": [],
                }
            
            if event_type == "memory_store":
                memory_data[agent_name]["stores"].append({
                    "memory_type": data.get("memory_type", "unknown"),
                    "content_length": data.get("content_length", 0),
                    "metadata": data.get("metadata", {}),
                })
            elif event_type == "memory_search":
                memory_data[agent_name]["searches"].append({
                    "query": data.get("query", ""),
                    "result_count": data.get("result_count", 0),
                    "memory_type": data.get("memory_type", "unknown"),
                    "top_score": data.get("top_score"),
                })
        
        return memory_data
    
    def _extract_knowledge_events(self, events: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Extract knowledge events (search/add) per agent from trace.
        
        Knowledge events may be attributed to a different name than the agent.
        This method associates knowledge events with the nearest agent:
        - If within agent_start/agent_end: use that agent
        - If before first agent_start: use the next agent
        - If after agent_end: use the previous or next agent
        """
        knowledge_data: Dict[str, Dict[str, Any]] = {}
        
        # First pass: build list of agent spans (start_seq, end_seq, agent_name)
        agent_spans = []
        current_agent = None
        current_start = None
        
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                agent_name = event.agent_name
                seq_num = getattr(event, 'sequence_num', 0)
            else:
                event_type = event.get('event_type', '')
                agent_name = event.get('agent_name')
                seq_num = event.get('sequence_num', 0)
            
            if event_type == "agent_start" and agent_name:
                current_agent = agent_name
                current_start = seq_num
            elif event_type == "agent_end" and current_agent:
                agent_spans.append((current_start, seq_num, current_agent))
                current_agent = None
                current_start = None
        
        # Helper to find the best agent for a sequence number
        def find_agent_for_seq(seq: int) -> Optional[str]:
            # Check if within any span
            for start, end, name in agent_spans:
                if start <= seq <= end:
                    return name
            
            # Find nearest span
            nearest_agent = None
            nearest_dist = float('inf')
            
            for start, end, name in agent_spans:
                if seq < start:
                    dist = start - seq
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_agent = name
                elif seq > end:
                    dist = seq - end
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_agent = name
            
            return nearest_agent
        
        # Second pass: extract knowledge events and associate with nearest agent
        for event in events:
            if hasattr(event, 'event_type'):
                event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                event_agent_name = event.agent_name or "unknown"
                data = event.data or {}
                seq_num = getattr(event, 'sequence_num', 0)
            else:
                event_type = event.get('event_type', '')
                event_agent_name = event.get('agent_name', 'unknown')
                data = event.get('data', {})
                seq_num = event.get('sequence_num', 0)
            
            if event_type not in ("knowledge_search", "knowledge_add"):
                continue
            
            # Find the best agent for this knowledge event
            agent_name = find_agent_for_seq(seq_num)
            
            # Fallback to event's agent_name if no agent found
            if not agent_name:
                agent_name = event_agent_name
            
            if agent_name not in knowledge_data:
                knowledge_data[agent_name] = {
                    "searches": [],
                    "adds": [],
                }
            
            if event_type == "knowledge_search":
                knowledge_data[agent_name]["searches"].append({
                    "query": data.get("query", ""),
                    "result_count": data.get("result_count", 0),
                    "sources": data.get("sources", []),
                    "top_score": data.get("top_score"),
                })
            elif event_type == "knowledge_add":
                knowledge_data[agent_name]["adds"].append({
                    "source": data.get("source", ""),
                    "chunk_count": data.get("chunk_count", 0),
                    "metadata": data.get("metadata", {}),
                })
        
        return knowledge_data
    
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
                result = str(data.get("result", ""))
                # Use intelligent truncation detection
                was_truncated = _is_content_truncated(result)
                tool_events.append({
                    "agent_name": agent_name,
                    "tool_name": data.get("tool_name", "unknown"),
                    "result": result,
                    "duration_ms": data.get("duration_ms", 0),
                    "error": data.get("error"),
                    "was_truncated": was_truncated,
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
        """Detect if important content was lost during the workflow.
        
        Uses intelligent truncation detection that distinguishes between:
        - LLM summaries (preserves info, not a problem)
        - Hard truncation (loses info, is a problem)
        - Incomplete structures (JSON cut off, etc.)
        """
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
            
            # Check for truncated tool results using intelligent detection
            if event_type == "tool_call_end":
                result = str(data.get("result", ""))
                # Use intelligent truncation detection
                if _is_content_truncated(result):
                    content_loss_detected = True
                    tool_name = data.get("tool_name", "unknown")
                    content_loss_details.append(
                        f"Tool '{tool_name}' result was truncated for agent '{agent_name}'"
                    )
            
            # Check for truncated LLM responses
            if event_type == "llm_response":
                response = str(data.get("response_content", ""))
                # Use intelligent truncation detection
                if _is_content_truncated(response):
                    content_loss_detected = True
                    content_loss_details.append(
                        f"LLM response was truncated for agent '{agent_name}'"
                    )
            
            # Note: We no longer flag {{variable}} patterns in LLM requests as "unresolved"
            # because the trace stores the original action text BEFORE variable substitution.
            # The workflow correctly substitutes variables during execution, but the trace
            # records the template. This was causing false positives where the judge would
            # flag {{researcher_output}} as unresolved even though it was properly substituted.
            # 
            # If we need to detect truly unresolved variables in the future, we should:
            # 1. Check if the variable name matches a known output variable pattern (e.g., *_output)
            # 2. Verify if the corresponding agent actually produced output
            # 3. Only flag if the agent failed to produce output
        
        return content_loss_detected, content_loss_details
    
    def _build_previous_steps_context(
        self,
        previous_scores: List[ContextEffectivenessScore],
    ) -> str:
        """Build context string describing previous agents' performance.
        
        This helps the LLM judge understand the quality of work done by
        previous agents when evaluating the current agent.
        
        Args:
            previous_scores: List of scores from agents that ran before this one
            
        Returns:
            Formatted string describing previous agents' performance
        """
        if not previous_scores:
            return "This is the first agent in the workflow. No previous agents."
        
        lines = []
        for i, score in enumerate(previous_scores, 1):
            status = "✅ PASSED" if score.task_achievement_score >= 6 else "❌ FAILED"
            if score.failure_detected:
                status = "❌ FAILED"
            
            lines.append(f"Agent {i}: {score.agent_name}")
            lines.append(f"  Status: {status}")
            lines.append(f"  Task Score: {score.task_achievement_score}/10")
            lines.append(f"  Output Quality: {score.output_quality_score}/10")
            if score.failure_detected and score.failure_reason:
                lines.append(f"  Failure: {score.failure_reason[:100]}")
            elif score.reasoning:
                lines.append(f"  Summary: {score.reasoning[:100]}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _judge_agent(
        self,
        agent_name: str,
        agent_info: Dict[str, Any],
        yaml_info: Optional[Dict[str, Any]] = None,
        previous_scores: Optional[List[ContextEffectivenessScore]] = None,
        recipe_goal: str = "",
        input_validation_issues: Optional[List[str]] = None,
    ) -> ContextEffectivenessScore:
        """Judge a single agent's performance with YAML-aware evaluation.
        
        Args:
            agent_name: Name of the agent being judged
            agent_info: Extracted data about the agent's execution
            yaml_info: Optional YAML structure info for context
            previous_scores: Scores from agents that ran before this one
            recipe_goal: The overall recipe/workflow goal
            input_validation_issues: List of input validation issues (unresolved templates)
        """
        litellm = self._get_litellm()
        
        # Get raw data - handle multimodal content (lists) gracefully
        def _normalize_content(items):
            """Convert items to strings, handling multimodal content."""
            result = []
            for item in items:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, list):
                    # Multimodal content - extract text parts
                    text_parts = [p.get("text", "") for p in item if isinstance(p, dict) and p.get("type") == "text"]
                    result.append(" ".join(text_parts) if text_parts else "[multimodal content]")
                elif isinstance(item, dict):
                    # Single dict item - extract text if present
                    result.append(item.get("text", str(item)))
                else:
                    result.append(str(item))
            return result
        
        raw_input = "\n".join(_normalize_content(agent_info.get("inputs", [])[:3])) or "No input recorded"
        raw_output = "\n".join(_normalize_content(agent_info.get("outputs", [])[:3])) or "No output recorded"
        raw_context = "\n".join(_normalize_content(agent_info.get("context", [])[:2])) or "No context recorded"
        
        # Check if chunked evaluation is needed
        total_content_size = len(raw_input) + len(raw_output) + len(raw_context)
        
        # Determine if we should use chunked evaluation
        use_chunked = False
        if self.chunked:
            # Explicit chunked mode - use if content exceeds chunk size
            use_chunked = total_content_size > self.chunk_size
        elif self.auto_chunk:
            # Auto-chunk mode - use token utilities to decide
            try:
                from praisonaiagents.eval.tokens import needs_chunking
                use_chunked = needs_chunking(
                    raw_input + raw_output + raw_context,
                    model=self.model,
                    safety_margin=0.7,  # Leave room for prompt template
                )
            except ImportError:
                # Fallback to simple size check if praisonaiagents not available
                use_chunked = total_content_size > self.chunk_size
        
        if use_chunked:
            # Use chunked evaluation for large outputs
            return self._judge_agent_chunked(
                agent_name=agent_name,
                agent_info=agent_info,
                raw_input=raw_input,
                raw_output=raw_output,
                raw_context=raw_context,
                yaml_info=yaml_info,
                previous_scores=previous_scores,
                recipe_goal=recipe_goal,
                input_validation_issues=input_validation_issues,
            )
        
        # Standard evaluation with smart truncation
        input_text = _smart_truncate(raw_input, max_chars=800)
        output = _smart_truncate(raw_output, max_chars=2000)
        context_summary = _smart_truncate(raw_context, max_chars=1500)
        
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
        
        # Build previous steps context
        previous_steps_context = self._build_previous_steps_context(previous_scores or [])
        
        # Build input validation status
        if input_validation_issues:
            input_validation_status = "⚠️ INPUT ISSUES DETECTED:\n" + "\n".join(f"  - {issue}" for issue in input_validation_issues[:5])
        else:
            input_validation_status = "✅ All inputs appear to be properly provided"
        
        # Use mode-specific prompt template
        # Note: input_text, output, context_summary already smart-truncated above
        # Get input context (image/URL descriptions) if available
        input_content = yaml_info.get("input_context", "Not provided") if yaml_info else "Not provided"
        
        prompt = self.prompt_template.format(
            agent_name=agent_name,
            agent_goal=_smart_truncate(agent_goal, max_chars=200),
            task_description=_smart_truncate(task_description, max_chars=500),
            expected_output=_smart_truncate(expected_output, max_chars=300),
            input_text=input_text,  # Already smart-truncated
            input_tokens=agent_info.get("prompt_tokens", 0),
            context_summary=context_summary,  # Already smart-truncated
            output_tokens=agent_info.get("completion_tokens", 0),
            output=output,  # Already smart-truncated
            tool_calls=_smart_truncate(tool_calls, max_chars=500),
            tool_errors=_smart_truncate(tool_errors, max_chars=500),
            # Enhanced fields for context mode
            recipe_goal=recipe_goal or "Not specified",
            previous_steps_context=previous_steps_context,
            input_validation_status=input_validation_status,
            input_content=input_content,  # Image/URL descriptions for validation
            # Memory-specific fields (used in memory mode)
            memory_store_count=agent_info.get("memory_store_count", 0),
            memory_search_count=agent_info.get("memory_search_count", 0),
            memory_store_details=agent_info.get("memory_store_details", "None"),
            memory_search_details=agent_info.get("memory_search_details", "None"),
            # Knowledge-specific fields (used in knowledge mode)
            knowledge_search_count=agent_info.get("knowledge_search_count", 0),
            knowledge_add_count=agent_info.get("knowledge_add_count", 0),
            knowledge_search_details=agent_info.get("knowledge_search_details", "None"),
            knowledge_sources=agent_info.get("knowledge_sources", "None"),
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
    
    def _judge_agent_chunked(
        self,
        agent_name: str,
        agent_info: Dict[str, Any],
        raw_input: str,
        raw_output: str,
        raw_context: str,
        yaml_info: Optional[Dict[str, Any]] = None,
        previous_scores: Optional[List[ContextEffectivenessScore]] = None,
        recipe_goal: str = "",
        input_validation_issues: Optional[List[str]] = None,
    ) -> ContextEffectivenessScore:
        """
        Judge agent using chunked evaluation for large outputs.
        
        Instead of truncating large outputs (which loses information),
        this method splits the output into chunks, evaluates each separately,
        and aggregates the scores.
        
        Args:
            agent_name: Name of the agent being judged
            agent_info: Extracted data about the agent's execution
            raw_input: Raw input text (not truncated)
            raw_output: Raw output text (not truncated)
            raw_context: Raw context text (not truncated)
            yaml_info: Optional YAML structure info
            previous_scores: Scores from previous agents
            recipe_goal: Overall recipe goal
            input_validation_issues: Input validation issues
            
        Returns:
            ContextEffectivenessScore with aggregated scores from all chunks
        """
        litellm = self._get_litellm()
        
        # Split output into chunks (output is usually the largest)
        output_chunks = chunk_split(
            raw_output,
            max_chars=self.chunk_size,
            max_chunks=self.max_chunks,
            overlap=self.chunk_overlap,
        )
        
        logger.info(f"Chunked evaluation for {agent_name}: {len(output_chunks)} chunks")
        
        # Prepare common fields (these don't need chunking)
        input_text = _smart_truncate(raw_input, max_chars=800)
        context_summary = _smart_truncate(raw_context, max_chars=1000)
        
        # Format tool calls
        raw_tool_calls = agent_info.get("tool_calls", [])[:5]
        tool_calls_strs = []
        tool_errors_list = []
        for tc in raw_tool_calls:
            if isinstance(tc, dict):
                tool_calls_strs.append(f"{tc.get('tool_name', 'unknown')}({str(tc.get('args', ''))[:100]})")
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
                tasks = role_data.get("tasks", {})
                if tasks:
                    first_task = list(tasks.values())[0]
                    if isinstance(first_task, dict):
                        task_description = first_task.get("description", task_description)[:500]
                        expected_output = first_task.get("expected_output", expected_output)[:300]
        
        # Build previous steps context
        previous_steps_context = self._build_previous_steps_context(previous_scores or [])
        
        # Build input validation status
        if input_validation_issues:
            input_validation_status = "⚠️ INPUT ISSUES DETECTED:\n" + "\n".join(f"  - {issue}" for issue in input_validation_issues[:5])
        else:
            input_validation_status = "✅ All inputs appear to be properly provided"
        
        # Evaluate each chunk
        chunk_results = []
        all_scores = {
            "task": [],
            "context": [],
            "quality": [],
            "instruction": [],
            "hallucination": [],
            "error": [],
        }
        failure_detected = False
        failure_reason = ""
        all_reasoning = []
        all_suggestions = []
        
        for i, chunk in enumerate(output_chunks):
            # Add chunk indicator to output
            chunk_header = f"\n[CHUNK {i + 1} of {len(output_chunks)}]\n"
            if i > 0:
                chunk_header += "(Continuation of agent output)\n"
            
            output_with_header = chunk_header + chunk
            
            # Get input context (image/URL descriptions) if available
            input_content = yaml_info.get("input_context", "Not provided") if yaml_info else "Not provided"
            
            # Build prompt for this chunk
            prompt = self.prompt_template.format(
                agent_name=agent_name,
                agent_goal=_smart_truncate(agent_goal, max_chars=200),
                task_description=_smart_truncate(task_description, max_chars=500),
                expected_output=_smart_truncate(expected_output, max_chars=300),
                input_text=input_text,
                input_tokens=agent_info.get("prompt_tokens", 0),
                context_summary=context_summary,
                output_tokens=agent_info.get("completion_tokens", 0),
                output=output_with_header,
                tool_calls=_smart_truncate(tool_calls, max_chars=500),
                tool_errors=_smart_truncate(tool_errors, max_chars=500),
                recipe_goal=recipe_goal or "Not specified",
                previous_steps_context=previous_steps_context,
                input_validation_status=input_validation_status,
                input_content=input_content,  # Image/URL descriptions for validation
                memory_store_count=agent_info.get("memory_store_count", 0),
                memory_search_count=agent_info.get("memory_search_count", 0),
                memory_store_details=agent_info.get("memory_store_details", "None"),
                memory_search_details=agent_info.get("memory_search_details", "None"),
                knowledge_search_count=agent_info.get("knowledge_search_count", 0),
                knowledge_add_count=agent_info.get("knowledge_add_count", 0),
                knowledge_search_details=agent_info.get("knowledge_search_details", "None"),
                knowledge_sources=agent_info.get("knowledge_sources", "None"),
            )
            
            try:
                response = litellm.completion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                
                response_text = response.choices[0].message.content or ""
                chunk_score = self._parse_response(response_text, agent_name, agent_info)
                
                # Collect scores from this chunk
                all_scores["task"].append(chunk_score.task_achievement_score)
                all_scores["context"].append(chunk_score.context_utilization_score)
                all_scores["quality"].append(chunk_score.output_quality_score)
                all_scores["instruction"].append(chunk_score.instruction_following_score)
                all_scores["hallucination"].append(chunk_score.hallucination_score)
                all_scores["error"].append(chunk_score.error_handling_score)
                
                # Track failures
                if chunk_score.failure_detected:
                    failure_detected = True
                    if chunk_score.failure_reason:
                        failure_reason = chunk_score.failure_reason
                
                # Collect reasoning and suggestions
                if chunk_score.reasoning:
                    all_reasoning.append(f"[Chunk {i + 1}]: {chunk_score.reasoning}")
                all_suggestions.extend(chunk_score.suggestions or [])
                
                chunk_results.append({
                    "chunk_index": i,
                    "score": chunk_score.overall_score,
                    "chunk_size": len(chunk),
                })
                
            except Exception as e:
                logger.warning(f"Chunk {i + 1} evaluation failed for {agent_name}: {e}")
                # Use default scores for failed chunk
                for key in all_scores:
                    all_scores[key].append(5.0)
                chunk_results.append({
                    "chunk_index": i,
                    "score": 5.0,
                    "chunk_size": len(chunk),
                })
        
        # Aggregate scores using the configured strategy
        def aggregate_list(scores: List[float]) -> float:
            if not scores:
                return 5.0
            chunk_data = [{"score": s, "chunk_size": cr.get("chunk_size", 1)} 
                         for s, cr in zip(scores, chunk_results)]
            return aggregate_chunk_scores(chunk_data, strategy=self.aggregation_strategy)
        
        final_task = aggregate_list(all_scores["task"])
        final_context = aggregate_list(all_scores["context"])
        final_quality = aggregate_list(all_scores["quality"])
        final_instruction = aggregate_list(all_scores["instruction"])
        final_hallucination = aggregate_list(all_scores["hallucination"])
        final_error = aggregate_list(all_scores["error"])
        
        # Calculate overall score
        overall_score = (final_task + final_context + final_quality + 
                        final_instruction + final_hallucination + final_error) / 6
        
        # Combine reasoning
        combined_reasoning = f"[Chunked evaluation: {len(output_chunks)} chunks, strategy: {self.aggregation_strategy}]\n"
        combined_reasoning += "\n".join(all_reasoning[:3])  # Limit to first 3
        
        # Deduplicate suggestions
        unique_suggestions = list(dict.fromkeys(all_suggestions))[:5]
        
        return ContextEffectivenessScore(
            agent_name=agent_name,
            task_achievement_score=final_task,
            context_utilization_score=final_context,
            output_quality_score=final_quality,
            instruction_following_score=final_instruction,
            hallucination_score=final_hallucination,
            error_handling_score=final_error,
            overall_score=overall_score,
            reasoning=combined_reasoning,
            suggestions=unique_suggestions,
            failure_detected=failure_detected,
            failure_reason=failure_reason,
            input_tokens=agent_info.get("prompt_tokens", 0),
            output_tokens=agent_info.get("completion_tokens", 0),
        )
    
    def _parse_response(
        self,
        response_text: str,
        agent_name: str,
        agent_info: Dict[str, Any],
    ) -> ContextEffectivenessScore:
        """Parse LLM response into ContextEffectivenessScore.
        
        Handles mode-specific score names:
        - context mode: TASK_SCORE, CONTEXT_SCORE, QUALITY_SCORE, INSTRUCTION_SCORE
        - memory mode: RETRIEVAL_SCORE, STORAGE_SCORE, RECALL_SCORE, EFFICIENCY_SCORE
        - knowledge mode: RETRIEVAL_SCORE, COVERAGE_SCORE, CITATION_SCORE, INTEGRATION_SCORE
        
        Also handles dynamic failure detection:
        - FAILURE_DETECTED: true/false
        - FAILURE_REASON: explanation of failure
        """
        task_score = 5.0
        context_score = 5.0
        quality_score = 5.0
        instruction_score = 5.0
        hallucination_score = 10.0  # Default to no hallucination
        error_score = 10.0  # Default to good error handling
        reasoning = "Unable to parse response"
        suggestions: List[str] = []
        failure_detected = False
        failure_reason = ""
        
        lines = response_text.strip().split('\n')
        in_suggestions = False
        
        for line in lines:
            line = line.strip()
            
            # Context mode scores
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
            
            # Memory mode scores (map to context mode equivalents)
            elif line.startswith('RETRIEVAL_SCORE:'):
                try:
                    task_score = float(line.replace('RETRIEVAL_SCORE:', '').strip())
                    task_score = max(1.0, min(10.0, task_score))
                except ValueError:
                    pass
            
            elif line.startswith('STORAGE_SCORE:'):
                try:
                    context_score = float(line.replace('STORAGE_SCORE:', '').strip())
                    context_score = max(1.0, min(10.0, context_score))
                except ValueError:
                    pass
            
            elif line.startswith('RECALL_SCORE:'):
                try:
                    quality_score = float(line.replace('RECALL_SCORE:', '').strip())
                    quality_score = max(1.0, min(10.0, quality_score))
                except ValueError:
                    pass
            
            elif line.startswith('EFFICIENCY_SCORE:'):
                try:
                    instruction_score = float(line.replace('EFFICIENCY_SCORE:', '').strip())
                    instruction_score = max(1.0, min(10.0, instruction_score))
                except ValueError:
                    pass
            
            # Knowledge mode scores (map to context mode equivalents)
            elif line.startswith('COVERAGE_SCORE:'):
                try:
                    context_score = float(line.replace('COVERAGE_SCORE:', '').strip())
                    context_score = max(1.0, min(10.0, context_score))
                except ValueError:
                    pass
            
            elif line.startswith('CITATION_SCORE:'):
                try:
                    quality_score = float(line.replace('CITATION_SCORE:', '').strip())
                    quality_score = max(1.0, min(10.0, quality_score))
                except ValueError:
                    pass
            
            elif line.startswith('INTEGRATION_SCORE:'):
                try:
                    instruction_score = float(line.replace('INTEGRATION_SCORE:', '').strip())
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
            
            elif line.startswith('FAILURE_DETECTED:'):
                value = line.replace('FAILURE_DETECTED:', '').strip().lower()
                failure_detected = value in ('true', 'yes', '1')
            
            elif line.startswith('FAILURE_REASON:'):
                failure_reason = line.replace('FAILURE_REASON:', '').strip()
            
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
            failure_detected=failure_detected,
            failure_reason=failure_reason,
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
        
        # Enrich agent_data with memory/knowledge events based on mode
        if self.mode == "memory":
            memory_data = self._extract_memory_events(events)
            for agent_name, mem_info in memory_data.items():
                if agent_name in agent_data:
                    stores = mem_info.get("stores", [])
                    searches = mem_info.get("searches", [])
                    agent_data[agent_name]["memory_store_count"] = len(stores)
                    agent_data[agent_name]["memory_search_count"] = len(searches)
                    agent_data[agent_name]["memory_store_details"] = str(stores[:3]) if stores else "None"
                    agent_data[agent_name]["memory_search_details"] = str(searches[:3]) if searches else "None"
        
        elif self.mode == "knowledge":
            knowledge_data = self._extract_knowledge_events(events)
            for agent_name, know_info in knowledge_data.items():
                if agent_name in agent_data:
                    searches = know_info.get("searches", [])
                    adds = know_info.get("adds", [])
                    agent_data[agent_name]["knowledge_search_count"] = len(searches)
                    agent_data[agent_name]["knowledge_add_count"] = len(adds)
                    agent_data[agent_name]["knowledge_search_details"] = str(searches[:3]) if searches else "None"
                    # Collect all sources
                    all_sources = []
                    for s in searches:
                        all_sources.extend(s.get("sources", []))
                    agent_data[agent_name]["knowledge_sources"] = ", ".join(list(set(all_sources))[:5]) or "None"
        
        # Load YAML info if provided
        yaml_info = None
        recipe_goal = ""
        input_context = ""  # Additional context from input images/URLs
        if yaml_file:
            yaml_info = _detect_yaml_structure(yaml_file)
            recipe_goal = yaml_info.get("recipe_goal", "")
            
            # Extract input variables from YAML for image/URL context
            variables = yaml_info.get("variables", {})
            
            # Check for image input and read it for judge context
            image_path = variables.get("image_path") or variables.get("image_url") or variables.get("image")
            if image_path:
                logger.info(f"Reading image for judge context: {image_path}")
                image_description = _read_image_for_judge(image_path)
                input_context += f"\n\nINPUT IMAGE CONTENT:\n{image_description}"
            
            # Check for URL input and crawl it for judge context
            url = variables.get("url") or variables.get("source_url") or variables.get("target_url")
            if url and url.startswith(('http://', 'https://')):
                logger.info(f"Crawling URL for judge context: {url}")
                url_content = _crawl_url_for_judge(url)
                input_context += f"\n\nINPUT URL CONTENT:\n{url_content}"
        
        # Store input context for use in agent judging
        if input_context:
            yaml_info = yaml_info or {}
            yaml_info["input_context"] = input_context
        
        # Detect content loss (includes unresolved templates)
        content_loss_detected, content_loss_details = self._detect_content_loss(events)
        
        # Extract input validation issues from content loss details
        input_validation_issues = [d for d in content_loss_details if "Unresolved template" in d]
        
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
        
        # Judge each agent, passing previous scores for context
        for agent_name, agent_info in agent_data.items():
            score = self._judge_agent(
                agent_name,
                agent_info,
                yaml_info,
                previous_scores=agent_scores.copy(),  # Pass scores of agents judged so far
                recipe_goal=recipe_goal,
                input_validation_issues=input_validation_issues,
            )
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
        
        # Count failures detected by LLM
        failures_detected = sum(1 for s in agent_scores if s.failure_detected)
        
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
                "failures_detected": failures_detected,
            },
            context_flow_evaluations=context_flow_evaluations,
            content_loss_detected=content_loss_detected,
            content_loss_details=content_loss_details,
            recipe_goal=recipe_goal,
            failures_detected=failures_detected,
            input_validation_issues=input_validation_issues,
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
    
    # Show recipe goal if available
    if report.recipe_goal:
        lines.append(f"  Recipe Goal: {report.recipe_goal[:100]}...")
    
    # Show failures detected
    if report.failures_detected > 0:
        lines.append("")
        lines.append(f"  ❌ FAILURES DETECTED: {report.failures_detected} agent(s) failed their primary task")
    
    # Show input validation issues
    if report.input_validation_issues:
        lines.append("")
        lines.append("  ⚠️  INPUT VALIDATION ISSUES:")
        for issue in report.input_validation_issues[:3]:
            lines.append(f"    - {issue}")
    
    # Show content loss warning if detected
    if report.content_loss_detected:
        lines.append("")
        lines.append("  ⚠️  CONTENT LOSS DETECTED:")
        for detail in report.content_loss_details[:3]:
            if "Unresolved template" not in detail:  # Already shown above
                lines.append(f"    - {detail}")
    
    lines.append("")
    lines.append("  AGENT SCORES:")
    
    for score in report.agent_scores:
        # Show failure status prominently
        status = "❌ FAILED" if score.failure_detected else "✅"
        lines.append(f"    {score.agent_name}: {status}")
        lines.append(f"      Task Achievement: {score.task_achievement_score}/10")
        lines.append(f"      Context Utilization: {score.context_utilization_score}/10")
        lines.append(f"      Output Quality: {score.output_quality_score}/10")
        lines.append(f"      Instruction Following: {score.instruction_following_score}/10")
        lines.append(f"      Hallucination: {score.hallucination_score}/10")
        lines.append(f"      Error Handling: {score.error_handling_score}/10")
        lines.append(f"      Overall: {score.overall_score}/10")
        
        # Show failure reason if detected
        if score.failure_detected and score.failure_reason:
            lines.append(f"      ❌ Failure Reason: {score.failure_reason[:150]}")
        
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
        - recipe_goal: the overall goal/objective from the YAML (if present)
        - roles: role data for each agent
    """
    from pathlib import Path
    import yaml
    
    result = {"structure": "simple", "agent_map": {}, "roles": {}, "recipe_goal": ""}
    
    try:
        yaml_path = Path(yaml_file)
        if not yaml_path.exists():
            return result
        
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        
        if not data:
            return result
        
        # Extract recipe-level goal (can be 'goal', 'objective', or 'description')
        recipe_goal = data.get("goal", "") or data.get("objective", "") or data.get("description", "")
        if isinstance(recipe_goal, str):
            result["recipe_goal"] = recipe_goal
        
        # Also check for 'topic' which often describes the workflow purpose
        if not result["recipe_goal"] and data.get("topic"):
            result["recipe_goal"] = f"Topic: {data.get('topic')}"
        
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
