"""
Recipe Optimizer for PraisonAI.

Iteratively optimizes recipes using LLM-as-judge feedback.
Runs the recipe, judges the output, proposes improvements, and applies them.

DRY: Reuses ContextEffectivenessJudge from replay module.
     Reuses SDK knowledge and tool categories from recipe_creator.
     Reuses image reading and URL crawling from judge module.
"""

import os
import re
import logging
import base64
from pathlib import Path
from typing import Optional, List, Tuple, Any, Dict

# DRY: Import SDK knowledge from shared modules
from .sdk_knowledge import get_sdk_knowledge_prompt

logger = logging.getLogger(__name__)


def _read_image_for_optimizer(image_path: str, model: str = "gpt-4o-mini") -> str:
    """
    Read and describe an image for optimizer context.
    
    Uses vision LLM to describe the image content so the optimizer can
    validate if agent outputs match the actual image.
    
    Args:
        image_path: Local file path or URL to the image
        model: Vision-capable model to use
        
    Returns:
        Description of the image content
    """
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
        logger.warning(f"Failed to read image for optimizer: {e}")
        return f"[Failed to read image: {str(e)[:100]}]"


def _crawl_url_for_optimizer(url: str) -> str:
    """
    Crawl a URL to get content for optimizer context.
    
    Uses the web_crawl tool to extract content so the optimizer can
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
            
            # Truncate content for optimizer context
            if len(content) > 3000:
                content = content[:3000] + "... [truncated]"
            
            return f"[URL CONTENT (via {provider})]\nTitle: {title}\n\n{content}"
        
        return f"[URL content: {str(result)[:3000]}]"
        
    except ImportError:
        # Fallback to basic HTTP fetch
        try:
            import urllib.request
            
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
        logger.warning(f"Failed to crawl URL for optimizer: {e}")
        return f"[Failed to crawl URL: {str(e)[:100]}]"


# Common issue patterns and their fixes - comprehensive patterns
COMMON_ISSUE_FIXES = {
    "tool_not_called": {
        "pattern": r"(failed to call|did not call|without calling|tool.*not.*used|did not use)",
        "fix": "Add explicit tool call instruction: 'You MUST call the {tool} tool. Do NOT respond without calling {tool} first. Return [format] from the tool results.'",
        "severity": "critical",
    },
    "missing_output_format": {
        "pattern": r"(output.*format|expected.*format|format.*missing|unstructured|no format)",
        "fix": "Add explicit expected_output format: 'Return a structured response with: 1) [section1], 2) [section2], 3) [section3]'",
        "severity": "high",
    },
    "hallucination": {
        "pattern": r"(hallucin|fabricat|made up|incorrect.*fact|invented|false information)",
        "fix": "Add grounding instruction: 'Only use information from the provided context or tool results. Do NOT make up facts, statistics, or sources.'",
        "severity": "critical",
    },
    "truncation": {
        "pattern": r"(truncat|incomplete|cut off|partial|missing.*content)",
        "fix": "Add completeness instruction: 'Ensure your response is COMPLETE. Include ALL required sections. Do not stop mid-response.'",
        "severity": "high",
    },
    "context_not_used": {
        "pattern": r"(context.*not.*used|ignored.*context|failed.*utilize|did not reference)",
        "fix": "Add context reference: 'Use the information from {{previous_agent}}_output. Extract specific data points and reference them in your response.'",
        "severity": "high",
    },
    "missing_goal": {
        "pattern": r"(missing.*goal|no.*goal|goal.*empty|unclear.*objective)",
        "fix": "Add clear goal: 'Your goal is to [specific objective]. Success means [measurable outcome].'",
        "severity": "critical",
    },
    "vague_action": {
        "pattern": r"(vague|unclear|ambiguous|not specific|too general)",
        "fix": "Make action specific: Replace vague verbs with concrete instructions. Include exact tool names, expected counts, and output format.",
        "severity": "high",
    },
    "missing_verification": {
        "pattern": r"(no verification|unverified|not validated|needs.*check)",
        "fix": "Add verification step: 'Verify your output contains all required elements before responding.'",
        "severity": "medium",
    },
    "manager_rejected": {
        "pattern": r"(manager rejected|hierarchical.*failed|validation.*failed|step.*rejected)",
        "fix": "Make tool calls explicit and mandatory. Add: 'You MUST call [tool]. Do NOT respond without calling [tool] first. Return [format] from the tool results.'",
        "severity": "critical",
    },
    "hierarchical_failure": {
        "pattern": r"(status.*failed|failure_reason|workflow.*stopped)",
        "fix": "Strengthen action instructions: explicit tool calls, specific output format, grounding against hallucination.",
        "severity": "critical",
    },
}

# Comprehensive tool documentation for optimizer
TOOL_DOCUMENTATION = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE TOOLS (Use exact names)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## WEB SEARCH (Safe - No approval required):
- `search_web` - ⭐ RECOMMENDED - Unified search with auto-fallback
- `internet_search` - DuckDuckGo search (FREE, no API key)
- `tavily_search` - High-quality AI search (needs TAVILY_API_KEY)
- `exa_search` - Exa AI search (needs EXA_API_KEY)

## WEB SCRAPING (Safe):
- `scrape_page` - Scrape web page content
- `extract_links` - Extract links from URL
- `crawl4ai` - Advanced web crawling

## FILE TOOLS - READ (Safe):
- `read_file` - Read local files
- `list_files` - List directory contents

## FILE TOOLS - WRITE (⚠️ APPROVAL REQUIRED):
- `write_file` - Write to files
- `delete_file` - Delete files

## CODE EXECUTION (⚠️ APPROVAL REQUIRED):
- `execute_command` - Run shell commands
- `execute_code` - Execute Python code

## DATA PROCESSING (Safe):
- `read_csv`, `read_json`, `read_yaml`, `read_excel`
"""

# Hierarchical process documentation for optimizer
HIERARCHICAL_PROCESS_DOC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIERARCHICAL PROCESS (CRITICAL - MUST PRESERVE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## What is Hierarchical Process?
In hierarchical mode, a MANAGER agent validates each step's output before
proceeding to the next step. If the manager rejects a step, the workflow
stops with status='failed' and includes a failure_reason.

## MANDATORY YAML Fields (NEVER REMOVE):
```yaml
process: hierarchical
manager_llm: gpt-4o-mini
```

## Why Hierarchical Matters:
1. **Quality Control**: Manager validates each step's output
2. **Tool Call Enforcement**: Manager rejects steps where tools weren't called
3. **Prevents Cascading Errors**: Bad outputs don't propagate to next steps
4. **Hallucination Detection**: Manager catches fabricated data

## Hierarchical-Specific Optimization Rules:
1. **Tool calls are MANDATORY** - Manager will reject if tools aren't called
2. **Output must match expected_output** - Manager validates format
3. **Context must be used** - Manager checks if previous output was utilized
4. **No hallucination** - Manager rejects fabricated data

## Common Manager Rejection Reasons:
- "Agent did not call the required tool"
- "Output does not match expected format"
- "Agent did not use context from previous step"
- "Output contains fabricated/unverified information"

## How to Fix Manager Rejections:
1. Make tool calls EXPLICIT: "You MUST call search_web. Do NOT respond without calling it."
2. Specify exact output format in expected_output
3. Reference previous output: "Using {{agent}}_output, extract..."
4. Add grounding: "Only use information from tool results. Do NOT fabricate."
"""

# Specialized agent documentation
SPECIALIZED_AGENTS_DOC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPECIALIZED AGENT TYPES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## AudioAgent - Text-to-Speech / Speech-to-Text
- Use `agent: AudioAgent` in agent definition
- TTS: llm: openai/tts-1 or openai/tts-1-hd
- STT: llm: openai/whisper-1 or groq/whisper-large-v3

## ImageAgent - Image Generation
- Use `agent: ImageAgent` in agent definition
- llm: openai/dall-e-3 or openai/dall-e-2

## VideoAgent - Video Generation
- Use `agent: VideoAgent` in agent definition
- llm: openai/sora-2 or gemini/veo-3.0-generate-preview

## OCRAgent - Text Extraction from Documents
- Use `agent: OCRAgent` in agent definition
- llm: mistral/mistral-ocr-latest (needs MISTRAL_API_KEY)

## DeepResearchAgent - Comprehensive Research
- Use `agent: DeepResearchAgent` in agent definition
"""


class RecipeOptimizer:
    """
    Iteratively optimizes recipes using judge feedback.
    
    Supports dynamic judge injection for domain-agnostic optimization:
    - Recipe/workflow optimization (default)
    - Water flow optimization
    - Data pipeline optimization
    - Any custom domain via JudgeCriteriaConfig
    
    Usage:
        # Default usage (backward compatible)
        optimizer = RecipeOptimizer(max_iterations=3, score_threshold=8.0)
        final_report = optimizer.optimize(recipe_path)
        
        # Custom judge for different domains
        from praisonaiagents.eval import Judge, JudgeCriteriaConfig
        
        water_config = JudgeCriteriaConfig(
            name="water_flow",
            description="Evaluate water flow optimization",
            prompt_template="Is the water flow optimal? {output}",
            scoring_dimensions=["flow_rate", "pressure", "efficiency"],
        )
        water_judge = Judge(criteria_config=water_config)
        optimizer = RecipeOptimizer(judge=water_judge)
    """
    
    def __init__(
        self,
        max_iterations: int = 3,
        score_threshold: float = 8.0,
        model: Optional[str] = None,
        judge: Optional[Any] = None,
        rules: Optional[List[Any]] = None,
        criteria: Optional[str] = None,
    ):
        """
        Initialize the optimizer.
        
        Args:
            max_iterations: Maximum optimization iterations
            score_threshold: Score threshold to stop optimization (1-10)
            model: LLM model for judging and optimization
            judge: Optional custom judge implementing JudgeProtocol (for domain-agnostic use)
            rules: Optional list of optimization rules implementing OptimizationRuleProtocol
            criteria: Optional custom criteria string for evaluation
        """
        self.max_iterations = max_iterations
        self.score_threshold = score_threshold
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.custom_judge = judge
        self.custom_rules = rules or []
        self.custom_criteria = criteria
    
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
        logger.debug(f"Running recipe iteration {iteration} with trace: {trace_name}")
        try:
            _result = recipe.run(
                str(recipe_path),
                input={"input": input_data} if input_data else {},
                options={
                    "save_replay": True,
                    "trace_name": trace_name,
                }
            )
            logger.debug(f"Recipe run completed with status: {getattr(_result, 'status', 'unknown')}")
        except Exception as e:
            logger.warning(f"Recipe run failed for iteration {iteration}: {e}")
            # Return a minimal report on failure
            from praisonai.replay.judge import JudgeReport
            return JudgeReport(
                session_id=trace_name,
                timestamp="",
                total_agents=0,
                overall_score=5.0,
                agent_scores=[],
                summary=f"Recipe execution failed: {e}",
                recommendations=["Fix recipe execution errors"],
            ), trace_name
        
        # Judge the trace
        reader = ContextTraceReader(trace_name)
        events = reader.get_all()
        
        if not events:
            # Check if recipe result indicates an error
            result_status = getattr(_result, 'status', None)
            result_error = getattr(_result, 'error', None)
            if result_error:
                logger.warning(f"No events found for trace: {trace_name} (recipe error: {result_error})")
            else:
                logger.warning(f"No events found for trace: {trace_name} (status: {result_status})")
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
        
        # Run judge - use custom judge if provided, otherwise default
        yaml_file = str(recipe_path / "agents.yaml")
        if self.custom_judge is not None:
            # Use custom judge for domain-agnostic evaluation
            # Custom judge should implement JudgeProtocol
            if hasattr(self.custom_judge, 'judge_trace'):
                report = self.custom_judge.judge_trace(events, session_id=trace_name, yaml_file=yaml_file)
            elif hasattr(self.custom_judge, 'run'):
                # Use the run method with output from events
                output = self._extract_output_from_events(events)
                result = self.custom_judge.run(output=output)
                # Convert to JudgeReport-like object
                from praisonai.replay.judge import JudgeReport
                report = JudgeReport(
                    session_id=trace_name,
                    timestamp="",
                    total_agents=len(events),
                    overall_score=result.score if hasattr(result, 'score') else 5.0,
                    agent_scores=[],
                    summary=result.reasoning if hasattr(result, 'reasoning') else "",
                    recommendations=result.suggestions if hasattr(result, 'suggestions') else [],
                )
            else:
                logger.warning("Custom judge does not implement expected interface, using default")
                judge = ContextEffectivenessJudge(model=self.model)
                report = judge.judge_trace(events, session_id=trace_name, yaml_file=yaml_file)
        else:
            # Default: use ContextEffectivenessJudge
            judge = ContextEffectivenessJudge(model=self.model)
            report = judge.judge_trace(events, session_id=trace_name, yaml_file=yaml_file)
        
        return report, trace_name
    
    def _extract_output_from_events(self, events: List[Any]) -> str:
        """
        Extract output text from trace events for custom judge evaluation.
        
        Args:
            events: List of trace events
            
        Returns:
            Combined output text from all events
        """
        outputs = []
        for event in events:
            if hasattr(event, 'output'):
                outputs.append(str(event.output))
            elif hasattr(event, 'result'):
                outputs.append(str(event.result))
            elif hasattr(event, 'content'):
                outputs.append(str(event.content))
        return "\n\n".join(outputs) if outputs else ""
    
    def _extract_agent_issues(self, report: Any) -> Dict[str, Dict[str, Any]]:
        """
        Extract detailed issues per agent from judge report.
        
        Returns:
            Dict mapping agent_name -> {scores, issues, suggestions}
        """
        agent_issues = {}
        
        if hasattr(report, 'agent_scores'):
            for score in report.agent_scores:
                agent_name = getattr(score, 'agent_name', 'unknown')
                agent_issues[agent_name] = {
                    'task_score': getattr(score, 'task_achievement_score', 5.0),
                    'context_score': getattr(score, 'context_utilization_score', 5.0),
                    'quality_score': getattr(score, 'output_quality_score', 5.0),
                    'instruction_score': getattr(score, 'instruction_following_score', 5.0),
                    'hallucination_score': getattr(score, 'hallucination_score', 5.0),
                    'error_score': getattr(score, 'error_handling_score', 5.0),
                    'failure_detected': getattr(score, 'failure_detected', False),
                    'failure_reason': getattr(score, 'failure_reason', ''),
                    'suggestions': getattr(score, 'suggestions', []),
                    'reasoning': getattr(score, 'reasoning', ''),
                    'tool_evaluations': getattr(score, 'tool_evaluations', []),
                }
        
        return agent_issues
    
    def _identify_fix_patterns(self, agent_issues: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify which common fix patterns apply based on issues.
        
        Returns:
            List of applicable fixes with agent context
        """
        applicable_fixes = []
        
        for agent_name, issues in agent_issues.items():
            reasoning = issues.get('reasoning', '').lower()
            failure_reason = issues.get('failure_reason', '').lower()
            combined_text = f"{reasoning} {failure_reason}"
            
            for fix_name, fix_info in COMMON_ISSUE_FIXES.items():
                if re.search(fix_info['pattern'], combined_text, re.IGNORECASE):
                    applicable_fixes.append({
                        'agent': agent_name,
                        'issue_type': fix_name,
                        'fix_template': fix_info['fix'],
                    })
            
            # Check for low scores and add specific fixes
            if issues.get('task_score', 10) < 5:
                applicable_fixes.append({
                    'agent': agent_name,
                    'issue_type': 'low_task_achievement',
                    'fix_template': 'Clarify the action with specific, concrete instructions. Add step-by-step guidance.',
                })
            
            if issues.get('instruction_score', 10) < 5:
                applicable_fixes.append({
                    'agent': agent_name,
                    'issue_type': 'poor_instruction_following',
                    'fix_template': 'Make instructions more explicit. Use numbered steps and clear requirements.',
                })
            
            if issues.get('hallucination_score', 10) < 6:
                applicable_fixes.append({
                    'agent': agent_name,
                    'issue_type': 'hallucination_risk',
                    'fix_template': 'Add grounding: "Only use information from provided context. Do NOT fabricate data."',
                })
        
        return applicable_fixes
    
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
        
        # Extract detailed agent issues
        agent_issues = self._extract_agent_issues(report)
        applicable_fixes = self._identify_fix_patterns(agent_issues)
        
        # Build detailed issue summary with severity ranking
        issue_summary = []
        sorted_agents = sorted(
            agent_issues.items(),
            key=lambda x: x[1].get('task_score', 10)  # Sort by lowest score first
        )
        
        for agent_name, issues in sorted_agents:
            avg_score = (
                issues['task_score'] + issues['context_score'] + 
                issues['quality_score'] + issues['instruction_score']
            ) / 4
            severity = "🔴 CRITICAL" if avg_score < 5 else "🟡 NEEDS WORK" if avg_score < 7 else "🟢 OK"
            
            issue_summary.append(f"""Agent: {agent_name} [{severity}] (avg: {avg_score:.1f}/10)
  - Task Achievement: {issues['task_score']}/10
  - Context Utilization: {issues['context_score']}/10
  - Output Quality: {issues['quality_score']}/10
  - Instruction Following: {issues['instruction_score']}/10
  - Hallucination Score: {issues['hallucination_score']}/10 (10=no hallucination)
  - Failure Detected: {issues['failure_detected']}
  - Failure Reason: {issues['failure_reason'] or 'N/A'}
  - Suggestions: {issues['suggestions']}""")
        
        # Build fix patterns summary with severity
        fix_patterns = []
        for fix in applicable_fixes:
            severity = COMMON_ISSUE_FIXES.get(fix['issue_type'], {}).get('severity', 'medium')
            severity_icon = "🔴" if severity == "critical" else "🟡" if severity == "high" else "🟢"
            fix_patterns.append(f"  {severity_icon} {fix['agent']}: {fix['issue_type']} → {fix['fix_template']}")
        
        recommendations = getattr(report, 'recommendations', [])
        overall_score = getattr(report, 'overall_score', 5.0)
        
        # Get SDK knowledge for comprehensive context (used in prompt)
        _sdk_knowledge = get_sdk_knowledge_prompt()  # Reserved for future use
        
        # Extract input context from YAML variables (image_path, url, etc.)
        input_context = ""
        try:
            import yaml
            yaml_data = yaml.safe_load(agents_yaml)
            variables = yaml_data.get('variables', {})
            
            # Check for image input
            image_path = variables.get('image_path') or variables.get('image_url') or variables.get('image')
            if image_path:
                logger.info(f"Reading image for optimizer context: {image_path}")
                image_desc = _read_image_for_optimizer(image_path, self.model)
                input_context += f"\n\n{image_desc}"
            
            # Check for URL input
            url = variables.get('url') or variables.get('source_url') or variables.get('webpage')
            if url:
                logger.info(f"Crawling URL for optimizer context: {url}")
                url_content = _crawl_url_for_optimizer(url)
                input_context += f"\n\n{url_content}"
        except Exception as e:
            logger.debug(f"Could not extract input context: {e}")
        
        # Build input context section for prompt
        input_context_section = ""
        if input_context:
            input_context_section = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACTUAL INPUT CONTENT (for validation):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{input_context}

IMPORTANT: Use this actual input content to validate if the agent outputs are correct.
If the agent output doesn't match the actual input, flag it as a hallucination issue.
"""
        
        prompt = f"""You are an expert at optimizing PraisonAI agent recipes. Your goal is to INCREASE the score from {overall_score}/10 to 8.0+/10.
{input_context_section}

{TOOL_DOCUMENTATION}

{HIERARCHICAL_PROCESS_DOC}

{SPECIALIZED_AGENTS_DOC}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT RECIPE (agents.yaml):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```yaml
{agents_yaml[:5000]}
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JUDGE REPORT (Current Score: {overall_score}/10 - Target: 8.0+/10):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Per-Agent Analysis (sorted by lowest score first):
{chr(10).join(issue_summary)}

Recommendations from Judge:
{chr(10).join(f'  - {r}' for r in recommendations)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTIFIED FIX PATTERNS (Apply these fixes):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(fix_patterns) if fix_patterns else '  No specific patterns identified'}

{f"Optimization Target: {optimization_target}" if optimization_target else ""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY OPTIMIZATION RULES (MUST FOLLOW ALL):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## RULE 1: TOOL CALL RELIABILITY (CRITICAL - Most common failure)
If an agent has tools assigned but failed to call them or got low task score:
- Action MUST explicitly name the tool: "You MUST call the search_web tool..."
- Action MUST forbid responding without tool: "Do NOT respond without calling search_web first."
- Action MUST require using results: "Return [specific format] from the search results."
- Action MUST specify count: "Return at least 5 items..."

❌ BAD: "Search for information about AI"
✅ GOOD: "You MUST call the search_web tool to search for AI developments. Do NOT respond without calling search_web first. Return at least 5 findings with titles, descriptions, and URLs from the search results."

## RULE 2: OUTPUT FORMAT SPECIFICATION (CRITICAL)
If output quality or format issues detected:
- expected_output MUST specify exact format with counts
- Include field names, counts, and structure

❌ BAD: "A report about the topic"
✅ GOOD: "A structured report with: 1) Executive summary (2-3 sentences), 2) Key findings (5 bullet points with title and description), 3) Recommendations (3 actionable items)"

## RULE 3: CONTEXT UTILIZATION (CRITICAL - MOST COMMON FAILURE)
If context not properly used or agent didn't reference previous output:
- Action MUST start with: "IMPORTANT: You MUST use ONLY the information from {{{{previous_agent}}}}_output below."
- Action MUST forbid training data: "Do NOT use your training data or prior knowledge."
- Action MUST require quoting: "Quote specific findings from the input."
- Action MUST require source references: "Reference the source URLs from the input."

❌ BAD: "Analyze the data"
❌ BAD: "Analyze the research findings from {{{{researcher}}}}_output."
✅ GOOD: "IMPORTANT: You MUST use ONLY the information from {{{{researcher}}}}_output below. Do NOT use your training data or prior knowledge. Read the research findings carefully, then: 1) Quote specific findings from the input, 2) Compare and identify the most significant insights, 3) Explain why each is important with references to the source URLs."

## RULE 4: ANTI-HALLUCINATION (CRITICAL)
If hallucination detected (score < 8):
- Add grounding instruction: "Only use information from the provided context or tool results."
- Add verification: "Do NOT make up facts, statistics, or sources. Cite your sources."

## RULE 5: GOAL CLARITY (CRITICAL)
If goal is missing or vague:
- Every agent MUST have a clear, specific goal
- Goal should describe measurable success criteria

❌ BAD: goal: "Help with research"
✅ GOOD: goal: "Find and compile the latest 5 developments in quantum computing with sources"

## RULE 6: COMPLETENESS (HIGH)
If truncation or incomplete output detected:
- Add: "Ensure your response is COMPLETE. Include ALL required sections."
- Specify minimum counts: "Include at least 5 items..."

## RULE 7: HIERARCHICAL PROCESS OPTIMIZATION (CRITICAL)
If workflow status is 'failed' or manager rejected a step:
- The manager validates EVERY step before proceeding
- Tool calls are MANDATORY - manager will reject if tools aren't called
- Make actions EXPLICIT: "You MUST call [tool]. Do NOT respond without calling [tool] first."
- Add grounding: "Only use information from tool results. Do NOT fabricate data."
- Specify exact output format in expected_output

Common manager rejection fixes:
- "Agent did not call tool" → Add explicit tool call instruction
- "Output format mismatch" → Specify exact format in expected_output

## RULE 8: FORCE TOOL USAGE (CRITICAL - ROOT CAUSE FIX)
If an agent has tools assigned but tools weren't called:
- ADD `tool_choice: required` to the agent definition
- This forces the LLM to call a tool before responding
- Without this, the LLM may skip tool calls even with explicit instructions

Example fix for agent with tools:
```yaml
agents:
  researcher:
    role: Research Specialist
    tools:
      - search_web
    tool_choice: required  # <-- ADD THIS to force tool usage
    llm: gpt-4o-mini
```
- "Hallucination detected" → Add grounding instruction
- "Context not used" → Reference {{previous_agent}}_output explicitly

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE: OPTIMIZED RECIPE PATTERN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

agents:
  researcher:
    role: Research Specialist
    goal: Find the latest 5+ developments on the topic with verified sources
    backstory: Expert at finding current, accurate information from web sources.
    tools:
      - search_web
    tool_choice: required
    llm: gpt-4o-mini

steps:
  - agent: researcher
    action: "You MUST call the search_web tool to search for [TOPIC]. Do NOT respond without calling search_web first. Return at least 5 key findings with: title, description (2-3 sentences), and source URL from the search results."
    expected_output: "Raw research data with 5+ findings, each containing: title, description, source URL"

  - agent: analyst
    action: "Analyze the research findings from {{researcher}}_output. Compare and identify the top 3 most significant insights. For each insight, explain: what it is, why it matters, and supporting evidence from the research."
    expected_output: "Analysis with 3 key insights, each with: insight name, significance explanation, supporting evidence from research"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR TASK: Propose 3-5 specific improvements
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Focus on the LOWEST scoring agents first (marked 🔴 CRITICAL).
Apply the mandatory rules above to fix each issue.

For EACH improvement, provide:
1. AGENT: Which agent to modify
2. FIELD: Which field to change (action, expected_output, goal, tools, etc.)
3. ISSUE: What problem this fixes (reference the rule number)
4. BEFORE: Current value (quote from YAML)
5. AFTER: New value (exact text to use)

Format your response as:

### IMPROVEMENT 1
- AGENT: [agent_name]
- FIELD: [field_name]
- ISSUE: [RULE X: brief description]
- BEFORE: [current value]
- AFTER: [new value]

### IMPROVEMENT 2
...

IMPORTANT: The AFTER value must be the EXACT text to use in the YAML file.
"""
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2500,
            )
            
            improvements_text = response.choices[0].message.content or ""
            
            # Parse structured improvements
            improvements = self._parse_structured_improvements(improvements_text)
            
            return improvements if improvements else [improvements_text]
            
        except Exception as e:
            logger.warning(f"Failed to propose improvements: {e}")
            # Fall back to fix patterns
            fallback = []
            for fix in applicable_fixes[:3]:
                fallback.append(f"{fix['agent']}: {fix['fix_template']}")
            return fallback if fallback else recommendations if recommendations else ["Review agent instructions"]
    
    def _parse_structured_improvements(self, text: str) -> List[str]:
        """
        Parse structured improvement suggestions from LLM response.
        
        Returns:
            List of improvement descriptions
        """
        improvements = []
        
        # Split by improvement headers
        sections = re.split(r'###\s*IMPROVEMENT\s*\d+', text, flags=re.IGNORECASE)
        
        for section in sections[1:]:  # Skip first empty section
            section = section.strip()
            if not section:
                continue
            
            # Extract key fields
            agent_match = re.search(r'AGENT:\s*(.+?)(?:\n|$)', section)
            field_match = re.search(r'FIELD:\s*(.+?)(?:\n|$)', section)
            issue_match = re.search(r'ISSUE:\s*(.+?)(?:\n|$)', section)
            after_match = re.search(r'AFTER:\s*(.+?)(?:###|$)', section, re.DOTALL)
            
            if agent_match and field_match:
                agent = agent_match.group(1).strip()
                field = field_match.group(1).strip()
                issue = issue_match.group(1).strip() if issue_match else "improve quality"
                after = after_match.group(1).strip() if after_match else ""
                
                improvement = f"Agent '{agent}' - {field}: {issue}"
                if after:
                    # Clean up the after value
                    after = re.sub(r'^[`"\']|[`"\']$', '', after.split('\n')[0].strip())
                    improvement += f" → {after[:200]}{'...' if len(after) > 200 else ''}"
                
                improvements.append(improvement)
        
        # Fallback: extract any numbered items
        if not improvements:
            for line in text.split('\n'):
                line = line.strip()
                if re.match(r'^\d+\.\s+', line) or line.startswith(('-', '*')):
                    improvements.append(re.sub(r'^[\d\.\-\*]+\s*', '', line))
        
        return improvements[:4]  # Max 4 improvements
    
    def _validate_yaml_structure(self, yaml_content: str) -> Tuple[bool, List[str]]:
        """
        Validate YAML structure for PraisonAI recipe requirements.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        import yaml
        errors = []
        
        try:
            data = yaml.safe_load(yaml_content)
            if not data:
                errors.append("YAML is empty")
                return False, errors
            
            # Check for required sections
            if 'agents' not in data:
                errors.append("Missing 'agents' section")
            elif not isinstance(data['agents'], dict):
                errors.append("'agents' must be a dictionary")
            else:
                # Validate each agent
                for agent_name, agent_config in data['agents'].items():
                    if not isinstance(agent_config, dict):
                        errors.append(f"Agent '{agent_name}' config must be a dictionary")
                        continue
                    
                    # Check for required agent fields
                    if 'role' not in agent_config:
                        errors.append(f"Agent '{agent_name}' missing 'role' field")
                    if 'goal' not in agent_config:
                        errors.append(f"Agent '{agent_name}' missing 'goal' field")
                    
                    # Validate tools is a list if present
                    if 'tools' in agent_config and not isinstance(agent_config['tools'], list):
                        errors.append(f"Agent '{agent_name}' tools must be a list")
            
            # Check for steps section
            if 'steps' not in data:
                errors.append("Missing 'steps' section")
            elif not isinstance(data['steps'], list):
                errors.append("'steps' must be a list")
            else:
                # Validate each step
                for i, step in enumerate(data['steps']):
                    if not isinstance(step, dict):
                        errors.append(f"Step {i+1} must be a dictionary")
                        continue
                    if 'agent' not in step:
                        errors.append(f"Step {i+1} missing 'agent' field")
                    if 'action' not in step:
                        errors.append(f"Step {i+1} missing 'action' field")
            
            return len(errors) == 0, errors
            
        except yaml.YAMLError as e:
            errors.append(f"Invalid YAML syntax: {str(e)[:200]}")
            return False, errors
    
    def _ensure_hierarchical_preserved(self, original_yaml: str, new_yaml: str) -> str:
        """
        Ensure hierarchical process fields are preserved after optimization.
        
        If the original YAML had process: hierarchical and manager_llm,
        ensure they are present in the new YAML. If missing, add them.
        
        Args:
            original_yaml: Original YAML content
            new_yaml: New YAML content after optimization
            
        Returns:
            Updated YAML with hierarchical fields preserved
        """
        import yaml
        
        try:
            original_data = yaml.safe_load(original_yaml)
            new_data = yaml.safe_load(new_yaml)
            
            if not original_data or not new_data:
                return new_yaml
            
            # Check if original had hierarchical process
            original_process = original_data.get('process')
            original_manager_llm = original_data.get('manager_llm')
            
            modified = False
            
            # Preserve process field
            if original_process == 'hierarchical':
                if new_data.get('process') != 'hierarchical':
                    new_data['process'] = 'hierarchical'
                    modified = True
                    logger.info("Restored process: hierarchical (was removed by LLM)")
            
            # Preserve manager_llm field
            if original_manager_llm:
                if not new_data.get('manager_llm'):
                    new_data['manager_llm'] = original_manager_llm
                    modified = True
                    logger.info(f"Restored manager_llm: {original_manager_llm} (was removed by LLM)")
            
            if modified:
                # Rebuild YAML with proper ordering
                return self._rebuild_yaml_with_order(new_data)
            
            return new_yaml
            
        except Exception as e:
            logger.debug(f"Could not validate hierarchical preservation: {e}")
            return new_yaml
    
    def _rebuild_yaml_with_order(self, data: Dict[str, Any]) -> str:
        """
        Rebuild YAML with proper field ordering.
        
        Ensures metadata, process, manager_llm come before agents and steps.
        """
        import yaml
        
        # Define preferred order
        ordered_keys = ['metadata', 'process', 'manager_llm', 'variables', 'agents', 'steps']
        
        # Build ordered dict
        ordered_data = {}
        
        # Add keys in preferred order
        for key in ordered_keys:
            if key in data:
                ordered_data[key] = data[key]
        
        # Add any remaining keys
        for key in data:
            if key not in ordered_data:
                ordered_data[key] = data[key]
        
        # Dump with proper formatting
        return yaml.dump(ordered_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
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

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT agents.yaml:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```yaml
{current_yaml}
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPROVEMENTS TO APPLY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(f"- {imp}" for imp in improvements)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY RULES FOR OUTPUT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Output ONLY valid YAML - no markdown code blocks, no explanations
2. Preserve ALL existing structure (metadata, agents, steps)
3. Only modify the specific fields mentioned in improvements
4. Ensure all agents have: role, goal, backstory, tools, llm
5. Ensure all steps have: agent, action, expected_output
6. Use proper YAML indentation (2 spaces)
7. Keep tools as a list: tools: [tool1, tool2] or tools: []
8. Use double curly braces for variable references: {{{{agent_name}}}}_output
9. CRITICAL: Quote ALL string values that contain colons (:) using double quotes
   Example: action: "Return findings with: title, description"
   NOT: action: Return findings with: title, description

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIERARCHICAL PROCESS PRESERVATION (CRITICAL - NEVER REMOVE):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If the original YAML contains these fields, you MUST preserve them EXACTLY:
- process: hierarchical
- manager_llm: gpt-4o-mini

These fields enable manager-based validation. NEVER remove them.
If they are missing, ADD them after the metadata section.

CRITICAL: Do NOT remove any existing agents or steps unless explicitly requested.
CRITICAL: Do NOT change the overall structure of the file.
CRITICAL: ALWAYS preserve process: hierarchical and manager_llm fields.

Output the complete, updated agents.yaml file now:
"""
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Lower temperature for more consistent output
                max_tokens=4000,
            )
            
            new_yaml = response.choices[0].message.content or ""
            
            # Clean up any markdown
            new_yaml = new_yaml.strip()
            if new_yaml.startswith('```'):
                lines = new_yaml.split('\n')
                # Find the end of the code block
                end_idx = len(lines) - 1
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip().startswith('```'):
                        end_idx = i
                        break
                new_yaml = '\n'.join(lines[1:end_idx])
            
            # Fix common YAML issues: quote strings with colons
            new_yaml = self._fix_yaml_string_quoting(new_yaml)
            
            # Validate YAML structure
            is_valid, errors = self._validate_yaml_structure(new_yaml)
            
            if not is_valid:
                logger.warning(f"Generated YAML has validation errors: {errors}")
                # Try to fix common issues
                if "Invalid YAML syntax" in str(errors):
                    logger.warning("YAML syntax error, keeping original file")
                    return False
            
            # Ensure hierarchical process is preserved
            new_yaml = self._ensure_hierarchical_preserved(current_yaml, new_yaml)
            
            # Create backup before writing
            backup_path = agents_yaml_path.with_suffix('.yaml.bak')
            backup_path.write_text(current_yaml)
            
            # Write updated YAML
            agents_yaml_path.write_text(new_yaml)
            logger.info(f"Applied improvements to {agents_yaml_path}")
            logger.info(f"Backup saved to {backup_path}")
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to apply improvements: {e}")
            return False
    
    def _ensure_hierarchical_preserved(self, original_yaml: str, new_yaml: str) -> str:
        """
        Ensure hierarchical process fields are preserved from original YAML.
        
        The LLM sometimes removes process: hierarchical and manager_llm fields.
        This method ensures they are always preserved or added.
        
        Args:
            original_yaml: Original YAML content
            new_yaml: New YAML content from LLM
            
        Returns:
            YAML with hierarchical fields preserved
        """
        import yaml
        
        try:
            original_data = yaml.safe_load(original_yaml)
            new_data = yaml.safe_load(new_yaml)
            
            if not new_data:
                return new_yaml
            
            # Check if original had hierarchical process
            had_hierarchical = original_data.get('process') == 'hierarchical'
            had_manager_llm = 'manager_llm' in original_data
            
            # Preserve or add hierarchical fields
            if had_hierarchical or 'process' not in new_data:
                new_data['process'] = 'hierarchical'
            
            if had_manager_llm or 'manager_llm' not in new_data:
                new_data['manager_llm'] = original_data.get('manager_llm', 'gpt-4o-mini')
            
            # Rebuild YAML with proper ordering
            ordered_data = {}
            
            # Put metadata first
            if 'metadata' in new_data:
                ordered_data['metadata'] = new_data.pop('metadata')
            
            # Put process and manager_llm next
            if 'process' in new_data:
                ordered_data['process'] = new_data.pop('process')
            if 'manager_llm' in new_data:
                ordered_data['manager_llm'] = new_data.pop('manager_llm')
            
            # Put variables next if present
            if 'variables' in new_data:
                ordered_data['variables'] = new_data.pop('variables')
            
            # Add remaining keys
            ordered_data.update(new_data)
            
            return yaml.dump(ordered_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
        except Exception as e:
            logger.warning(f"Failed to ensure hierarchical preserved: {e}")
            return new_yaml
    
    def _fix_yaml_string_quoting(self, yaml_content: str) -> str:
        """
        Fix YAML strings that contain colons but aren't properly quoted.
        
        The LLM sometimes generates YAML like:
            action: Return findings with: title, description
        Which should be:
            action: "Return findings with: title, description"
        
        Args:
            yaml_content: Raw YAML content
            
        Returns:
            Fixed YAML content with properly quoted strings
        """
        import re
        
        fixed_lines = []
        for line in yaml_content.split('\n'):
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                fixed_lines.append(line)
                continue
            
            # Check if line has a key: value pattern
            match = re.match(r'^(\s*)([\w_-]+):\s*(.+)$', line)
            if match:
                indent, key, value = match.groups()
                value = value.strip()
                
                # Skip if already quoted or is a special YAML value
                if value.startswith('"') or value.startswith("'"):
                    fixed_lines.append(line)
                    continue
                if value.startswith('[') or value.startswith('{'):
                    fixed_lines.append(line)
                    continue
                if value in ('true', 'false', 'null', 'yes', 'no', '~'):
                    fixed_lines.append(line)
                    continue
                if re.match(r'^-?\d+(\.\d+)?$', value):
                    fixed_lines.append(line)
                    continue
                
                # Check if value contains a colon (needs quoting)
                if ':' in value:
                    # Escape any existing quotes and wrap in double quotes
                    escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
                    fixed_lines.append(f'{indent}{key}: "{escaped_value}"')
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
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
                    logger.info("  ✅ Score threshold reached!")
                else:
                    logger.info("  Max iterations reached")
                break
            
            # Propose and apply improvements
            improvements = self.propose_improvements(report, recipe_path, optimization_target)
            logger.info(f"  Proposed {len(improvements)} improvements")
            
            if improvements:
                applied = self.apply_improvements(recipe_path, improvements)
                if applied:
                    logger.info("  ✏️ Applied improvements")
                else:
                    logger.warning("  Failed to apply improvements")
        
        return final_report


__all__ = ['RecipeOptimizer']
