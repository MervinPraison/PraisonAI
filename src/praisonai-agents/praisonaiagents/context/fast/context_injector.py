"""
Context Injector for Fast Context.

Injects FastContext results into the main agent with:
- Token budget management
- Context formatting for different models
- Precision over recall (avoid context pollution)
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from praisonaiagents.context.fast.result import FastContextResult, FileMatch

logger = logging.getLogger(__name__)


@dataclass
class InjectionConfig:
    """Configuration for context injection.
    
    Attributes:
        max_tokens: Maximum tokens for injected context
        max_files: Maximum files to include
        max_lines_per_file: Maximum lines per file
        include_line_numbers: Whether to include line numbers
        include_file_content: Whether to include file content
        format_style: Format style ('markdown', 'xml', 'plain')
        prioritize_precision: If True, include fewer but more relevant results
    """
    max_tokens: int = 4000
    max_files: int = 10
    max_lines_per_file: int = 100
    include_line_numbers: bool = True
    include_file_content: bool = True
    format_style: str = "markdown"
    prioritize_precision: bool = True
    
    # Approximate tokens per character (conservative estimate)
    chars_per_token: float = 4.0


class ContextInjector:
    """Injects FastContext results into agent context.
    
    Handles:
    - Token budget management
    - Result formatting
    - Context pollution prevention
    """
    
    def __init__(self, config: Optional[InjectionConfig] = None):
        """Initialize context injector.
        
        Args:
            config: Injection configuration
        """
        self.config = config or InjectionConfig()
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated token count
        """
        return int(len(text) / self.config.chars_per_token)
    
    def inject(
        self,
        result: FastContextResult,
        system_prompt: Optional[str] = None,
        user_message: Optional[str] = None
    ) -> Dict[str, str]:
        """Inject FastContext results into agent context.
        
        Args:
            result: FastContext search result
            system_prompt: Original system prompt
            user_message: Original user message
            
        Returns:
            Dict with 'system_prompt' and 'user_message' keys
        """
        # Format the context
        context_str = self.format_context(result)
        
        # Inject into appropriate location
        if system_prompt:
            # Add to system prompt
            injected_system = self._inject_into_system_prompt(system_prompt, context_str)
            return {
                "system_prompt": injected_system,
                "user_message": user_message or ""
            }
        elif user_message:
            # Add to user message
            injected_user = self._inject_into_user_message(user_message, context_str)
            return {
                "system_prompt": "",
                "user_message": injected_user
            }
        else:
            return {
                "system_prompt": context_str,
                "user_message": ""
            }
    
    def format_context(self, result: FastContextResult) -> str:
        """Format FastContext result as context string.
        
        Args:
            result: FastContext search result
            
        Returns:
            Formatted context string
        """
        if self.config.format_style == "markdown":
            return self._format_markdown(result)
        elif self.config.format_style == "xml":
            return self._format_xml(result)
        else:
            return self._format_plain(result)
    
    def _format_markdown(self, result: FastContextResult) -> str:
        """Format result as markdown.
        
        Args:
            result: FastContext search result
            
        Returns:
            Markdown formatted string
        """
        if not result.files:
            return ""
        
        lines = ["# Relevant Code Context"]
        lines.append(f"*Found {result.total_files} file(s) in {result.search_time_ms}ms*\n")
        
        token_budget = self.config.max_tokens
        files_included = 0
        
        # Sort by relevance
        sorted_files = sorted(
            result.files,
            key=lambda f: f.relevance_score,
            reverse=True
        )
        
        # Apply precision filter if enabled
        if self.config.prioritize_precision:
            sorted_files = [f for f in sorted_files if f.relevance_score >= 0.5]
        
        for file_match in sorted_files:
            if files_included >= self.config.max_files:
                break
            
            file_section = self._format_file_markdown(file_match)
            section_tokens = self.estimate_tokens(file_section)
            
            if section_tokens > token_budget:
                # Try truncated version
                file_section = self._format_file_markdown(file_match, truncate=True)
                section_tokens = self.estimate_tokens(file_section)
                
                if section_tokens > token_budget:
                    continue
            
            lines.append(file_section)
            token_budget -= section_tokens
            files_included += 1
        
        if files_included < result.total_files:
            lines.append(f"\n*... and {result.total_files - files_included} more files*")
        
        return "\n".join(lines)
    
    def _format_file_markdown(
        self,
        file_match: FileMatch,
        truncate: bool = False
    ) -> str:
        """Format a single file match as markdown.
        
        Args:
            file_match: File match to format
            truncate: Whether to truncate content
            
        Returns:
            Markdown formatted string
        """
        lines = [f"## `{file_match.path}`"]
        
        if not self.config.include_file_content:
            if file_match.line_ranges:
                ranges = ", ".join(
                    f"L{lr.start}-{lr.end}" for lr in file_match.line_ranges[:3]
                )
                lines.append(f"Relevant lines: {ranges}")
            return "\n".join(lines)
        
        max_lines = self.config.max_lines_per_file
        if truncate:
            max_lines = max_lines // 2
        
        lines_shown = 0
        for lr in file_match.line_ranges:
            if lines_shown >= max_lines:
                break
            
            if self.config.include_line_numbers:
                lines.append(f"Lines {lr.start}-{lr.end}:")
            
            if lr.content:
                content = lr.content
                content_lines = content.split("\n")
                
                if len(content_lines) > max_lines - lines_shown:
                    content_lines = content_lines[:max_lines - lines_shown]
                    content = "\n".join(content_lines) + "\n..."
                
                lines.append(f"```\n{content}\n```")
                lines_shown += len(content_lines)
        
        return "\n".join(lines)
    
    def _format_xml(self, result: FastContextResult) -> str:
        """Format result as XML.
        
        Args:
            result: FastContext search result
            
        Returns:
            XML formatted string
        """
        if not result.files:
            return ""
        
        lines = ["<code_context>"]
        lines.append(f"  <summary files=\"{result.total_files}\" search_time_ms=\"{result.search_time_ms}\"/>")
        
        token_budget = self.config.max_tokens
        files_included = 0
        
        sorted_files = sorted(
            result.files,
            key=lambda f: f.relevance_score,
            reverse=True
        )
        
        for file_match in sorted_files[:self.config.max_files]:
            if files_included >= self.config.max_files:
                break
            
            file_xml = self._format_file_xml(file_match)
            section_tokens = self.estimate_tokens(file_xml)
            
            if section_tokens > token_budget:
                continue
            
            lines.append(file_xml)
            token_budget -= section_tokens
            files_included += 1
        
        lines.append("</code_context>")
        return "\n".join(lines)
    
    def _format_file_xml(self, file_match: FileMatch) -> str:
        """Format a single file match as XML.
        
        Args:
            file_match: File match to format
            
        Returns:
            XML formatted string
        """
        lines = [f'  <file path="{file_match.path}" relevance="{file_match.relevance_score:.2f}">']
        
        for lr in file_match.line_ranges[:3]:
            lines.append(f'    <lines start="{lr.start}" end="{lr.end}">')
            if lr.content and self.config.include_file_content:
                # Escape XML special characters
                content = lr.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f"      <![CDATA[{content}]]>")
            lines.append("    </lines>")
        
        lines.append("  </file>")
        return "\n".join(lines)
    
    def _format_plain(self, result: FastContextResult) -> str:
        """Format result as plain text.
        
        Args:
            result: FastContext search result
            
        Returns:
            Plain text formatted string
        """
        if not result.files:
            return ""
        
        lines = [f"Code Context ({result.total_files} files):"]
        
        for file_match in result.files[:self.config.max_files]:
            lines.append(f"\nFile: {file_match.path}")
            
            for lr in file_match.line_ranges[:3]:
                lines.append(f"  Lines {lr.start}-{lr.end}")
                if lr.content and self.config.include_file_content:
                    for line in lr.content.split("\n")[:10]:
                        lines.append(f"    {line}")
        
        return "\n".join(lines)
    
    def _inject_into_system_prompt(
        self,
        system_prompt: str,
        context: str
    ) -> str:
        """Inject context into system prompt.
        
        Args:
            system_prompt: Original system prompt
            context: Context to inject
            
        Returns:
            Modified system prompt
        """
        if not context:
            return system_prompt
        
        # Add context section
        return f"{system_prompt}\n\n{context}"
    
    def _inject_into_user_message(
        self,
        user_message: str,
        context: str
    ) -> str:
        """Inject context into user message.
        
        Args:
            user_message: Original user message
            context: Context to inject
            
        Returns:
            Modified user message
        """
        if not context:
            return user_message
        
        # Prepend context
        return f"{context}\n\n---\n\n{user_message}"


def inject_fast_context(
    result: FastContextResult,
    system_prompt: Optional[str] = None,
    user_message: Optional[str] = None,
    max_tokens: int = 4000,
    format_style: str = "markdown"
) -> Dict[str, str]:
    """Convenience function to inject FastContext results.
    
    Args:
        result: FastContext search result
        system_prompt: Original system prompt
        user_message: Original user message
        max_tokens: Maximum tokens for context
        format_style: Format style ('markdown', 'xml', 'plain')
        
    Returns:
        Dict with 'system_prompt' and 'user_message' keys
    """
    config = InjectionConfig(
        max_tokens=max_tokens,
        format_style=format_style
    )
    injector = ContextInjector(config)
    return injector.inject(result, system_prompt, user_message)
