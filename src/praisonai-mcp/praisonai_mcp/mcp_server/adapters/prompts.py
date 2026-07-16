"""
MCP Prompts Adapter

Registers MCP prompts for PraisonAI:
- deep-research
- code-review
- workflow-auto
- guardrail-check
- context-engineering
- eval-criteria
"""

import logging

from ..registry import register_prompt

logger = logging.getLogger(__name__)


def register_mcp_prompts() -> None:
    """Register MCP prompts."""
    
    @register_prompt(
        "deep-research",
        description="Generate a deep research prompt for comprehensive topic analysis",
        arguments=[
            {"name": "topic", "description": "Research topic", "required": True},
            {"name": "depth", "description": "Research depth (shallow/medium/deep)", "required": False},
            {"name": "focus_areas", "description": "Specific areas to focus on", "required": False},
        ],
    )
    def deep_research_prompt(
        topic: str,
        depth: str = "medium",
        focus_areas: str = "",
    ) -> list:
        """Generate deep research prompt."""
        depth_instructions = {
            "shallow": "Provide a brief overview with key points.",
            "medium": "Conduct thorough research with multiple perspectives and sources.",
            "deep": "Perform exhaustive research covering all aspects, historical context, current state, and future implications.",
        }
        
        focus_text = f"\n\nFocus particularly on: {focus_areas}" if focus_areas else ""
        
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Research the following topic comprehensively:

Topic: {topic}

Research Depth: {depth}
{depth_instructions.get(depth, depth_instructions["medium"])}
{focus_text}

Please provide:
1. Executive Summary
2. Key Findings
3. Detailed Analysis
4. Sources and References
5. Conclusions and Recommendations"""
                }
            }
        ]
    
    @register_prompt(
        "code-review",
        description="Generate a code review prompt for analyzing code quality",
        arguments=[
            {"name": "code", "description": "Code to review", "required": True},
            {"name": "language", "description": "Programming language", "required": False},
            {"name": "focus", "description": "Review focus (security/performance/style/all)", "required": False},
        ],
    )
    def code_review_prompt(
        code: str,
        language: str = "auto",
        focus: str = "all",
    ) -> list:
        """Generate code review prompt."""
        focus_areas = {
            "security": "Focus on security vulnerabilities, input validation, and potential exploits.",
            "performance": "Focus on performance optimizations, algorithmic efficiency, and resource usage.",
            "style": "Focus on code style, readability, naming conventions, and best practices.",
            "all": "Review all aspects: security, performance, style, and correctness.",
        }
        
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Please review the following {language} code:

```{language}
{code}
```

Review Focus: {focus}
{focus_areas.get(focus, focus_areas["all"])}

Please provide:
1. Overall Assessment
2. Issues Found (with severity: critical/major/minor)
3. Suggestions for Improvement
4. Positive Aspects
5. Refactored Code (if applicable)"""
                }
            }
        ]
    
    @register_prompt(
        "workflow-auto",
        description="Generate a workflow auto-generation prompt",
        arguments=[
            {"name": "task", "description": "Task description", "required": True},
            {"name": "pattern", "description": "Workflow pattern (sequential/parallel/routing)", "required": False},
            {"name": "agents_count", "description": "Number of agents to use", "required": False},
        ],
    )
    def workflow_auto_prompt(
        task: str,
        pattern: str = "sequential",
        agents_count: str = "auto",
    ) -> list:
        """Generate workflow auto-generation prompt."""
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Generate a PraisonAI workflow configuration for the following task:

Task: {task}

Workflow Pattern: {pattern}
Number of Agents: {agents_count}

Please generate a YAML configuration that includes:
1. Framework specification
2. Topic/goal definition
3. Agent roles with:
   - Role name
   - Goal
   - Backstory
   - Tasks with descriptions and expected outputs
4. Appropriate tools for each agent

Output the complete agents.yaml configuration."""
                }
            }
        ]
    
    @register_prompt(
        "guardrail-check",
        description="Generate a guardrail check prompt for content safety",
        arguments=[
            {"name": "content", "description": "Content to check", "required": True},
            {"name": "rules", "description": "Specific rules to enforce", "required": False},
        ],
    )
    def guardrail_check_prompt(
        content: str,
        rules: str = "",
    ) -> list:
        """Generate guardrail check prompt."""
        rules_text = f"\n\nAdditional Rules:\n{rules}" if rules else ""
        
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Analyze the following content for safety and policy compliance:

Content:
{content}
{rules_text}

Please check for:
1. Harmful or dangerous content
2. Personal information exposure
3. Inappropriate language
4. Policy violations
5. Factual accuracy concerns

Provide:
- Safety Score (1-10)
- Issues Found
- Recommendations
- Modified Safe Version (if needed)"""
                }
            }
        ]
    
    @register_prompt(
        "context-engineering",
        description="Generate a context engineering prompt for optimal LLM interaction",
        arguments=[
            {"name": "goal", "description": "What you want to achieve", "required": True},
            {"name": "constraints", "description": "Any constraints or requirements", "required": False},
        ],
    )
    def context_engineering_prompt(
        goal: str,
        constraints: str = "",
    ) -> list:
        """Generate context engineering prompt."""
        constraints_text = f"\n\nConstraints:\n{constraints}" if constraints else ""
        
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Help me engineer an optimal prompt/context for the following goal:

Goal: {goal}
{constraints_text}

Please provide:
1. Optimal System Prompt
2. User Prompt Template
3. Few-shot Examples (if helpful)
4. Recommended Model Settings (temperature, etc.)
5. Expected Output Format
6. Potential Edge Cases to Handle"""
                }
            }
        ]
    
    @register_prompt(
        "eval-criteria",
        description="Generate evaluation criteria for agent output assessment",
        arguments=[
            {"name": "task_type", "description": "Type of task being evaluated", "required": True},
            {"name": "output_format", "description": "Expected output format", "required": False},
        ],
    )
    def eval_criteria_prompt(
        task_type: str,
        output_format: str = "text",
    ) -> list:
        """Generate evaluation criteria prompt."""
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Generate comprehensive evaluation criteria for the following:

Task Type: {task_type}
Expected Output Format: {output_format}

Please provide:
1. Accuracy Criteria (what makes output correct)
2. Quality Metrics (completeness, clarity, relevance)
3. Format Compliance Checks
4. Edge Case Handling Assessment
5. Scoring Rubric (1-10 scale with descriptions)
6. Example Good/Bad Outputs"""
                }
            }
        ]
    
    @register_prompt(
        "agent-instructions",
        description="Generate optimal agent instructions for a specific role",
        arguments=[
            {"name": "role", "description": "Agent role/persona", "required": True},
            {"name": "capabilities", "description": "Available capabilities/tools", "required": False},
        ],
    )
    def agent_instructions_prompt(
        role: str,
        capabilities: str = "",
    ) -> list:
        """Generate agent instructions prompt."""
        caps_text = f"\n\nAvailable Capabilities:\n{capabilities}" if capabilities else ""
        
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""Generate optimal instructions for an AI agent with the following role:

Role: {role}
{caps_text}

Please provide:
1. Core Identity Statement
2. Primary Objectives
3. Behavioral Guidelines
4. Communication Style
5. Decision-Making Framework
6. Error Handling Approach
7. Collaboration Guidelines (if working with other agents)"""
                }
            }
        ]
    
    logger.info("Registered MCP prompts")
