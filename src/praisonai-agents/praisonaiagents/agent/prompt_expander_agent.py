"""
Prompt Expander Agent Module

This module provides the PromptExpanderAgent class for expanding short prompts
into detailed, comprehensive prompts for better task execution.

Unlike QueryRewriterAgent (which optimizes queries for search/retrieval),
PromptExpanderAgent focuses on enriching prompts for task execution.

Supported Expansion Strategies:
- **BASIC**: Simple expansion with clarity improvements
- **DETAILED**: Rich expansion with context, constraints, and examples
- **STRUCTURED**: Expansion with clear structure (task, format, requirements)
- **CREATIVE**: Expansion with creative flair and vivid language
- **AUTO**: Automatically selects the best strategy based on prompt analysis

Example:
    from praisonaiagents import PromptExpanderAgent, ExpandStrategy
    
    agent = PromptExpanderAgent()
    
    # Basic expansion
    result = agent.expand("write a movie script in 3 lines")
    print(result.expanded_prompt)
    
    # Detailed expansion
    result = agent.expand("blog about AI", strategy=ExpandStrategy.DETAILED)
    print(result.expanded_prompt)
    
    # With tools for context gathering
    from praisonaiagents.tools import internet_search
    agent = PromptExpanderAgent(tools=[internet_search])
    result = agent.expand("latest AI developments")
"""

import logging
from typing import List, Optional, Any, Dict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

class ExpandStrategy(Enum):
    """Enumeration of available prompt expansion strategies."""
    BASIC = "basic"
    DETAILED = "detailed"
    STRUCTURED = "structured"
    CREATIVE = "creative"
    AUTO = "auto"


@dataclass
class ExpandResult:
    """Result of a prompt expansion operation."""
    original_prompt: str
    expanded_prompt: str
    strategy_used: ExpandStrategy
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self):
        return f"ExpandResult(strategy={self.strategy_used.value}, original_len={len(self.original_prompt)}, expanded_len={len(self.expanded_prompt)})"


class PromptExpanderAgent:
    """
    Agent for expanding short prompts into detailed, comprehensive prompts.
    
    This agent transforms brief task descriptions into rich, detailed prompts
    that provide better context and guidance for task execution.
    
    Key difference from QueryRewriterAgent:
    - QueryRewriterAgent: Optimizes queries for search/retrieval (RAG)
    - PromptExpanderAgent: Expands prompts for detailed task execution
    
    Attributes:
        name: Name of the agent
        model: LLM model to use for expansion (alias for llm=)
        temperature: Temperature for LLM generation (higher = more creative)
        tools: Optional tools for context gathering
        
    Example:
        agent = PromptExpanderAgent(model="gpt-4o-mini")
        result = agent.expand("write a poem", strategy=ExpandStrategy.CREATIVE)
        print(result.expanded_prompt)
    """
    
    # Default prompts for each strategy
    PROMPTS = {
        "basic": """You are an expert at improving task prompts.

Current date: {current_date}

Given the following task prompt, expand it to be clearer and more actionable while preserving the original intent.

Guidelines:
- Keep it as a TASK/COMMAND (do NOT convert to a question)
- Add clarity without changing the core request
- Fix any ambiguity
- Keep it concise but complete
- Use the current date for any time-sensitive context

Original prompt: {prompt}

Expanded prompt:""",

        "detailed": """You are an expert at creating comprehensive task prompts.

Current date: {current_date}

Given the following brief task prompt, expand it into a detailed, actionable prompt that provides rich context and clear guidance.

Guidelines:
- Keep it as a TASK/COMMAND (do NOT convert to a question)
- Add specific details about what to include
- Specify quality expectations
- Add relevant constraints or requirements
- Include format guidance if applicable
- Mention style or tone if relevant
- Use the current date for any time-sensitive context

Original prompt: {prompt}

Detailed expanded prompt:""",

        "structured": """You are an expert at creating well-structured task prompts.

Current date: {current_date}

Given the following task prompt, expand it into a structured format with clear sections.

Guidelines:
- Keep it as a TASK/COMMAND (do NOT convert to a question)
- Use a clear structure:
  * Task: What to do
  * Format: Expected output format
  * Requirements: Specific requirements
  * Style: Tone or style guidance
  * Constraints: Any limitations
- Be specific and actionable
- Use the current date for any time-sensitive context

Original prompt: {prompt}

Structured expanded prompt:""",

        "creative": """You are an expert at crafting inspiring, creative task prompts.

Current date: {current_date}

Given the following task prompt, expand it with vivid language and creative direction while keeping it actionable.

Guidelines:
- Keep it as a TASK/COMMAND (do NOT convert to a question)
- Use evocative, inspiring language
- Paint a picture of the desired outcome
- Add creative direction and artistic guidance
- Make it exciting and engaging
- Preserve the core task intent
- Use the current date for any time-sensitive context

Original prompt: {prompt}

Creative expanded prompt:""",

        "auto": """You are an expert at analyzing and expanding task prompts.

Current date: {current_date}

Analyze the following prompt and expand it appropriately based on its nature.

For short/vague prompts: Add significant detail and context
For task prompts: Preserve the action-oriented nature
For creative tasks: Add artistic direction
For technical tasks: Add precision and requirements

IMPORTANT: Keep it as a TASK/COMMAND. Never convert to a question.
Use the current date for any time-sensitive context.

Original prompt: {prompt}
{context}

Expanded prompt:"""
    }
    
    def __init__(
        self,
        name: str = "PromptExpanderAgent",
        model: str = "gpt-4o-mini",
        instructions: Optional[str] = None,
        verbose: bool = False,
        temperature: float = 0.7,  # Higher for creativity
        max_tokens: int = 1000,
        tools: Optional[List[Any]] = None
    ):
        """
        Initialize the PromptExpanderAgent.
        
        Args:
            name: Name of the agent
            model: LLM model to use (default: gpt-4o-mini)
            instructions: Custom instructions for the agent
            verbose: Whether to print detailed logs
            temperature: Temperature for LLM generation (default: 0.7 for creativity)
            max_tokens: Maximum tokens for LLM response
            tools: Optional list of tools for context gathering
        """
        self.name = name
        self.model = model
        self.instructions = instructions
        self.verbose = verbose
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = tools or []
        self._agent = None  # Lazy initialized
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        if self.verbose:
            self.logger.setLevel(logging.DEBUG)
    
    @property
    def agent(self):
        """Lazy initialization of internal Agent."""
        if self._agent is None:
            from .agent import Agent
            self._agent = Agent(
                name=self.name,
                role="Prompt Expansion Specialist",
                goal="Expand brief prompts into detailed, actionable prompts for better task execution. Use available tools when needed to gather context.",
                backstory="You are an expert at understanding user intent and transforming brief requests into comprehensive, detailed prompts.",
                tools=self.tools,
                llm=self.model,
                output={"verbose": self.verbose, "markdown": False}
            )
        return self._agent
    
    def _call_agent(self, prompt: str) -> str:
        """Call the internal Agent with the given prompt."""
        try:
            response = self.agent.chat(prompt)
            return response if response else ""
        except Exception as e:
            self.logger.error(f"Agent call failed: {e}")
            raise
    
    def _is_short_prompt(self, prompt: str, threshold: int = 10) -> bool:
        """Check if prompt is considered short."""
        return len(prompt.split()) < threshold
    
    def _is_task_prompt(self, prompt: str) -> bool:
        """Check if prompt is a task/command (vs a question)."""
        task_verbs = [
            "write", "create", "generate", "build", "make", "design",
            "develop", "implement", "compose", "draft", "produce",
            "craft", "construct", "prepare", "draw", "paint", "code"
        ]
        prompt_lower = prompt.lower().strip()
        return any(prompt_lower.startswith(verb) for verb in task_verbs)
    
    def _is_technical_task(self, prompt: str) -> bool:
        """Check if prompt is a technical/coding task."""
        technical_indicators = [
            "python", "javascript", "java", "code", "function", "class",
            "api", "database", "sql", "html", "css", "react", "node",
            "algorithm", "debug", "fix", "error", "bug", "test",
            "deploy", "server", "docker", "kubernetes", "aws", "azure",
            "typescript", "rust", "go", "c++", "c#", "ruby", "php",
            "script", "bash", "shell", "terminal", "command", "cli"
        ]
        prompt_lower = prompt.lower()
        return any(ind in prompt_lower for ind in technical_indicators)
    
    def _is_creative_task(self, prompt: str) -> bool:
        """Check if prompt is a creative task (non-technical)."""
        creative_indicators = [
            "poem", "story", "song", "art", "creative",
            "fiction", "novel", "essay", "blog", "article"
        ]
        prompt_lower = prompt.lower()
        return any(ind in prompt_lower for ind in creative_indicators)
    
    def _detect_strategy(self, prompt: str) -> ExpandStrategy:
        """Auto-detect the best expansion strategy for a prompt."""
        # Very short prompts need detailed expansion
        if self._is_short_prompt(prompt, threshold=5):
            return ExpandStrategy.DETAILED
        
        # Technical/coding tasks get structured expansion (check before creative)
        if self._is_technical_task(prompt):
            return ExpandStrategy.STRUCTURED
        
        # Creative tasks benefit from creative expansion
        if self._is_creative_task(prompt):
            return ExpandStrategy.CREATIVE
        
        # Task prompts get structured expansion
        if self._is_task_prompt(prompt):
            return ExpandStrategy.STRUCTURED
        
        # Default to basic
        return ExpandStrategy.BASIC
    
    def expand(
        self,
        prompt: str,
        strategy: ExpandStrategy = ExpandStrategy.AUTO,
        context: Optional[str] = None
    ) -> ExpandResult:
        """
        Expand a prompt using the specified strategy.
        
        All operations go through an internal Agent which automatically handles
        tool calling when tools are provided. The agent decides when to use tools
        based on the prompt context.
        
        Args:
            prompt: The original user prompt
            strategy: Expansion strategy to use
            context: Additional context to help with expansion
            
        Returns:
            ExpandResult containing the expanded prompt
        """
        if self.verbose:
            self.logger.debug(f"Expanding prompt: '{prompt}' with strategy: {strategy.value}")
            if self.tools:
                print(f"[cyan]Agent has {len(self.tools)} tools available (will use if needed)...[/cyan]")
        
        # Auto-detect strategy if needed
        if strategy == ExpandStrategy.AUTO:
            strategy = self._detect_strategy(prompt)
            if self.verbose:
                self.logger.debug(f"Auto-detected strategy: {strategy.value}")
        
        # Build the expansion prompt
        if strategy == ExpandStrategy.AUTO:
            # Fallback if auto-detect returns AUTO
            strategy = ExpandStrategy.DETAILED
        
        # Get current date for time-sensitive context
        current_date = datetime.now().strftime("%B %d, %Y")
        
        expansion_prompt = self.PROMPTS[strategy.value].format(
            prompt=prompt,
            context=context or "",
            current_date=current_date
        )
        
        # Add tool usage instructions if tools are available
        if self.tools:
            # Build dynamic tool descriptions from docstrings
            tool_descriptions = []
            for tool in self.tools:
                tool_name = getattr(tool, '__name__', str(tool))
                tool_doc = getattr(tool, '__doc__', '')
                # Get first line of docstring as description
                if tool_doc:
                    first_line = tool_doc.strip().split('\n')[0].strip()
                    tool_descriptions.append(f"- {tool_name}: {first_line}")
                else:
                    tool_descriptions.append(f"- {tool_name}")
            
            tools_list = '\n'.join(tool_descriptions)
            
            tool_instruction = f"""

IMPORTANT: You have the following tools available:
{tools_list}

Before expanding this prompt, FIRST use the available tools to gather relevant current information about the topic. This will help you create a more informed and accurate expanded prompt.

Steps:
1. Use the appropriate tool(s) to gather relevant information about the topic
2. Use the gathered information to inform your expansion
3. Create an expanded prompt that incorporates the latest context

"""
            expansion_prompt = tool_instruction + expansion_prompt
        
        # Call the agent
        expanded = self._call_agent(expansion_prompt).strip()
        
        # If expansion failed, return original
        if not expanded:
            expanded = prompt
        
        return ExpandResult(
            original_prompt=prompt,
            expanded_prompt=expanded,
            strategy_used=strategy,
            metadata={
                "original_length": len(prompt),
                "expanded_length": len(expanded),
                "has_context": bool(context),
                "has_tools": bool(self.tools)
            }
        )
    
    # Convenience methods for direct strategy access
    def expand_basic(self, prompt: str, context: Optional[str] = None) -> ExpandResult:
        """Convenience method for basic expansion."""
        return self.expand(prompt, strategy=ExpandStrategy.BASIC, context=context)
    
    def expand_detailed(self, prompt: str, context: Optional[str] = None) -> ExpandResult:
        """Convenience method for detailed expansion."""
        return self.expand(prompt, strategy=ExpandStrategy.DETAILED, context=context)
    
    def expand_structured(self, prompt: str, context: Optional[str] = None) -> ExpandResult:
        """Convenience method for structured expansion."""
        return self.expand(prompt, strategy=ExpandStrategy.STRUCTURED, context=context)
    
    def expand_creative(self, prompt: str, context: Optional[str] = None) -> ExpandResult:
        """Convenience method for creative expansion."""
        return self.expand(prompt, strategy=ExpandStrategy.CREATIVE, context=context)
