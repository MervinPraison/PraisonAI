"""
Deep Research Agent Module

This module provides the DeepResearchAgent class for automating complex research 
workflows using Deep Research APIs from multiple providers:

- **OpenAI**: o3-deep-research, o4-mini-deep-research (via Responses API)
- **Gemini**: deep-research-pro (via Interactions API)

The agent automatically detects the provider based on the model name and uses
the appropriate API.

Example:
    from praisonaiagents import DeepResearchAgent
    
    # OpenAI Deep Research
    agent = DeepResearchAgent(
        name="Research Assistant",
        model="o3-deep-research",
        instructions="You are a professional researcher..."
    )
    
    # Gemini Deep Research
    agent = DeepResearchAgent(
        name="Research Assistant", 
        model="deep-research-pro",
        instructions="You are a professional researcher..."
    )
    
    result = agent.research("What are the economic impacts of AI on healthcare?")
    print(result.report)
    for citation in result.citations:
        print(f"- {citation.title}: {citation.url}")
"""

import os
import logging
import time
import asyncio
from typing import List, Optional, Any, Dict, Literal
from dataclasses import dataclass, field
from enum import Enum


# Data classes for Deep Research response types
@dataclass
class Citation:
    """Represents a citation in the research report."""
    title: str
    url: str
    start_index: int = 0
    end_index: int = 0
    
    def __repr__(self):
        return f"Citation(title='{self.title}', url='{self.url}')"


@dataclass
class ReasoningStep:
    """Represents a reasoning step in the research process."""
    text: str
    type: str = "reasoning"
    
    def __repr__(self):
        return f"ReasoningStep(text='{self.text[:50]}...')" if len(self.text) > 50 else f"ReasoningStep(text='{self.text}')"


@dataclass
class WebSearchCall:
    """Represents a web search call made during research."""
    query: str
    status: str
    
    def __repr__(self):
        return f"WebSearchCall(query='{self.query}', status='{self.status}')"


@dataclass
class CodeExecutionStep:
    """Represents a code execution step during research."""
    input_code: str
    output: Optional[str] = None
    
    def __repr__(self):
        return f"CodeExecutionStep(input='{self.input_code[:50]}...')" if len(self.input_code) > 50 else f"CodeExecutionStep(input='{self.input_code}')"


@dataclass
class MCPCall:
    """Represents an MCP tool call during research."""
    name: str
    server_label: str
    arguments: Dict[str, Any]
    
    def __repr__(self):
        return f"MCPCall(name='{self.name}', server='{self.server_label}')"


@dataclass
class FileSearchCall:
    """Represents a file search call (Gemini-specific)."""
    store_names: List[str]
    
    def __repr__(self):
        return f"FileSearchCall(stores={self.store_names})"


@dataclass
class DeepResearchResponse:
    """
    Complete response from a Deep Research query.
    
    Attributes:
        report: The final research report text
        citations: List of citations with source metadata
        reasoning_steps: List of reasoning steps taken
        web_searches: List of web search queries executed
        code_executions: List of code execution steps
        mcp_calls: List of MCP tool calls
        file_searches: List of file search calls (Gemini)
        provider: The provider used (openai, gemini, litellm)
        interaction_id: Interaction ID (Gemini) or Response ID (OpenAI)
        raw_response: The raw API response object
    """
    report: str
    citations: List[Citation] = field(default_factory=list)
    reasoning_steps: List[ReasoningStep] = field(default_factory=list)
    web_searches: List[WebSearchCall] = field(default_factory=list)
    code_executions: List[CodeExecutionStep] = field(default_factory=list)
    mcp_calls: List[MCPCall] = field(default_factory=list)
    file_searches: List[FileSearchCall] = field(default_factory=list)
    provider: str = "openai"
    interaction_id: Optional[str] = None
    raw_response: Optional[Any] = None
    
    def get_citation_text(self, citation: Citation) -> str:
        """Extract the text that a citation refers to."""
        if citation.start_index and citation.end_index:
            return self.report[citation.start_index:citation.end_index]
        return ""
    
    def get_all_sources(self) -> List[Dict[str, str]]:
        """Get a list of all unique sources cited."""
        seen = set()
        sources = []
        for c in self.citations:
            if c.url not in seen:
                seen.add(c.url)
                sources.append({"title": c.title, "url": c.url})
        return sources


class Provider(Enum):
    """Supported Deep Research providers."""
    OPENAI = "openai"
    GEMINI = "gemini"
    LITELLM = "litellm"


class DeepResearchAgent:
    """
    Agent for performing deep research using multiple provider APIs.
    
    Supports:
    - **OpenAI Deep Research**: o3-deep-research, o4-mini-deep-research
    - **Gemini Deep Research**: deep-research-pro-preview
    - **LiteLLM**: Unified interface for OpenAI models
    
    The provider is auto-detected based on the model name, or can be explicitly set.
    
    Example:
        # OpenAI (default)
        agent = DeepResearchAgent(
            model="o3-deep-research",
            instructions="You are a professional researcher."
        )
        
        # Gemini
        agent = DeepResearchAgent(
            model="deep-research-pro",
            instructions="You are a professional researcher."
        )
        
        # Using LiteLLM
        agent = DeepResearchAgent(
            model="o3-deep-research",
            use_litellm=True
        )
        
        result = agent.research("Research the economic impact of AI on healthcare.")
        print(result.report)
    """
    
    # OpenAI Deep Research models
    OPENAI_MODELS = {
        "o3-deep-research": "o3-deep-research-2025-06-26",
        "o3-deep-research-2025-06-26": "o3-deep-research-2025-06-26",
        "o4-mini-deep-research": "o4-mini-deep-research-2025-06-26",
        "o4-mini-deep-research-2025-06-26": "o4-mini-deep-research-2025-06-26",
    }
    
    # Gemini Deep Research models
    GEMINI_MODELS = {
        "deep-research-pro": "deep-research-pro-preview-12-2025",
        "deep-research-pro-preview": "deep-research-pro-preview-12-2025",
        "deep-research-pro-preview-12-2025": "deep-research-pro-preview-12-2025",
        "gemini-deep-research": "deep-research-pro-preview-12-2025",
    }
    
    # Default models
    DEFAULT_OPENAI_MODEL = "o3-deep-research-2025-06-26"
    DEFAULT_GEMINI_MODEL = "deep-research-pro-preview-12-2025"
    
    def __init__(
        self,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        model: str = "o3-deep-research",
        provider: Optional[Literal["openai", "gemini", "litellm", "auto"]] = "auto",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        verbose: bool = True,
        summary_mode: Literal["auto", "detailed", "concise"] = "auto",
        enable_web_search: bool = True,
        enable_code_interpreter: bool = False,
        enable_file_search: bool = False,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        file_search_stores: Optional[List[str]] = None,
        use_litellm: bool = False,
        poll_interval: int = 10,
        max_wait_time: int = 3600,
    ):
        """
        Initialize a DeepResearchAgent.
        
        Args:
            name: Name of the agent for identification
            instructions: System instructions that define the agent's behavior
            model: Deep Research model to use:
                - OpenAI: "o3-deep-research", "o4-mini-deep-research"
                - Gemini: "deep-research-pro", "deep-research-pro-preview"
            provider: Provider to use ("openai", "gemini", "litellm", or "auto")
            api_key: API key (defaults to OPENAI_API_KEY or GEMINI_API_KEY)
            base_url: Custom base URL for API endpoints
            verbose: Enable detailed logging and progress updates
            summary_mode: Summary detail level - "auto", "detailed", or "concise"
            enable_web_search: Enable web search tool
            enable_code_interpreter: Enable code interpreter for data analysis
            enable_file_search: Enable file search (Gemini only)
            mcp_servers: List of MCP server configurations (OpenAI only)
            file_search_stores: File search store names (Gemini only)
            use_litellm: Use LiteLLM for OpenAI models
            poll_interval: Seconds between status polls (Gemini background mode)
            max_wait_time: Maximum seconds to wait for research completion
        """
        self.name = name or "DeepResearchAgent"
        # Default instructions for comprehensive research
        default_instructions = """
You are a professional research analyst. When conducting research:
- Include specific figures, trends, statistics, and measurable outcomes
- Prioritize reliable, up-to-date sources: peer-reviewed research, official organizations, regulatory agencies
- Include inline citations and return all source metadata
- Be analytical, avoid generalities, and ensure data-backed reasoning
- Structure your response with clear headers and formatting
- If creating comparisons, use tables for clarity
"""
        self.instructions = instructions or default_instructions
        self.verbose = verbose
        self.summary_mode = summary_mode
        self.enable_web_search = enable_web_search
        self.enable_code_interpreter = enable_code_interpreter
        self.enable_file_search = enable_file_search
        self.mcp_servers = mcp_servers or []
        self.file_search_stores = file_search_stores or []
        self.use_litellm = use_litellm
        self.poll_interval = poll_interval
        self.max_wait_time = max_wait_time
        self.base_url = base_url
        
        # Detect provider from model name
        self.provider = self._detect_provider(model, provider)
        
        # Resolve model name
        if self.provider == Provider.GEMINI:
            self.model = self.GEMINI_MODELS.get(model, model)
        else:
            self.model = self.OPENAI_MODELS.get(model, model)
        
        # Set up API key
        self._setup_api_key(api_key)
        
        # Initialize clients lazily
        self._openai_client = None
        self._async_openai_client = None
        self._gemini_client = None
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
        
        if self.verbose:
            self.logger.debug(f"DeepResearchAgent initialized: provider={self.provider.value}, model={self.model}")
    
    def _detect_provider(
        self, 
        model: str, 
        provider: Optional[str]
    ) -> Provider:
        """Detect the provider based on model name or explicit setting."""
        if provider and provider != "auto":
            if provider == "litellm":
                return Provider.LITELLM
            elif provider == "gemini":
                return Provider.GEMINI
            else:
                return Provider.OPENAI
        
        # Auto-detect from model name
        model_lower = model.lower()
        
        if any(g in model_lower for g in ["gemini", "deep-research-pro"]):
            return Provider.GEMINI
        elif self.use_litellm:
            return Provider.LITELLM
        else:
            return Provider.OPENAI
    
    def _setup_api_key(self, api_key: Optional[str]):
        """Set up the API key based on provider."""
        if api_key:
            self.api_key = api_key
        elif self.provider == Provider.GEMINI:
            self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required for Gemini Deep Research."
                )
        else:
            self.api_key = os.environ.get("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError(
                    "OPENAI_API_KEY environment variable is required for OpenAI Deep Research."
                )
    
    @property
    def openai_client(self):
        """Get the synchronous OpenAI client (lazy initialization)."""
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._openai_client
    
    @property
    def async_openai_client(self):
        """Get the asynchronous OpenAI client (lazy initialization)."""
        if self._async_openai_client is None:
            from openai import AsyncOpenAI
            self._async_openai_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._async_openai_client
    
    @property
    def gemini_client(self):
        """Get the Gemini client (lazy initialization)."""
        if self._gemini_client is None:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "google-genai package is required for Gemini Deep Research. "
                    "Install with: pip install google-genai"
                )
        return self._gemini_client
    
    def _build_openai_tools(
        self,
        web_search: bool = True,
        code_interpreter: bool = False,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build tools list for OpenAI Deep Research API."""
        tools = []
        
        if web_search:
            tools.append({"type": "web_search_preview"})
        
        if code_interpreter:
            tools.append({
                "type": "code_interpreter",
                "container": {
                    "type": "auto",
                    "file_ids": file_ids or []
                }
            })
        
        if mcp_servers:
            for server in mcp_servers:
                tools.append({
                    "type": "mcp",
                    "server_label": server.get("label", "mcp_server"),
                    "server_url": server.get("url"),
                    "require_approval": server.get("require_approval", "never")
                })
        
        return tools
    
    def _build_gemini_tools(
        self,
        file_search: bool = False,
        file_search_stores: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build tools list for Gemini Deep Research API."""
        tools = []
        
        # Gemini has google_search and url_context enabled by default
        # Only need to add file_search if requested
        if file_search and file_search_stores:
            tools.append({
                "type": "file_search",
                "file_search_store_names": file_search_stores
            })
        
        return tools
    
    def _parse_openai_response(self, response: Any) -> DeepResearchResponse:
        """Parse OpenAI Deep Research API response."""
        report = ""
        citations = []
        reasoning_steps = []
        web_searches = []
        code_executions = []
        mcp_calls = []
        
        for item in response.output:
            item_type = getattr(item, 'type', None)
            
            if item_type == "message":
                if hasattr(item, 'content') and item.content:
                    for content_item in item.content:
                        if hasattr(content_item, 'text'):
                            report = content_item.text
                        if hasattr(content_item, 'annotations'):
                            for ann in content_item.annotations:
                                citations.append(Citation(
                                    title=getattr(ann, 'title', ''),
                                    url=getattr(ann, 'url', ''),
                                    start_index=getattr(ann, 'start_index', 0),
                                    end_index=getattr(ann, 'end_index', 0)
                                ))
            
            elif item_type == "reasoning":
                if hasattr(item, 'summary'):
                    for s in item.summary:
                        reasoning_steps.append(ReasoningStep(
                            text=getattr(s, 'text', str(s))
                        ))
            
            elif item_type == "web_search_call":
                action = getattr(item, 'action', {})
                query = action.get('query', '') if isinstance(action, dict) else ''
                status = getattr(item, 'status', 'unknown')
                web_searches.append(WebSearchCall(query=query, status=status))
            
            elif item_type == "code_interpreter_call":
                code_executions.append(CodeExecutionStep(
                    input_code=getattr(item, 'input', ''),
                    output=getattr(item, 'output', None)
                ))
            
            elif item_type == "mcp_call":
                if hasattr(item, 'arguments') and item.arguments:
                    mcp_calls.append(MCPCall(
                        name=getattr(item, 'name', ''),
                        server_label=getattr(item, 'server_label', ''),
                        arguments=item.arguments
                    ))
        
        return DeepResearchResponse(
            report=report,
            citations=citations,
            reasoning_steps=reasoning_steps,
            web_searches=web_searches,
            code_executions=code_executions,
            mcp_calls=mcp_calls,
            provider="openai",
            interaction_id=getattr(response, 'id', None),
            raw_response=response
        )
    
    def _parse_gemini_response(
        self, 
        interaction: Any, 
        fallback_text: str = "",
        fallback_reasoning: Optional[List[ReasoningStep]] = None
    ) -> DeepResearchResponse:
        """Parse Gemini Deep Research API response.
        
        Args:
            interaction: The Gemini interaction object
            fallback_text: Accumulated text from streaming (used if outputs parsing fails)
            fallback_reasoning: Reasoning steps collected during streaming
        """
        report = ""
        citations = []
        reasoning_steps = fallback_reasoning or []
        
        # Try multiple attribute paths for Gemini output structure
        # Path 1: Direct outputs with text attribute
        if hasattr(interaction, 'outputs') and interaction.outputs:
            last_output = interaction.outputs[-1]
            if hasattr(last_output, 'text') and last_output.text:
                report = last_output.text
            elif hasattr(last_output, 'content'):
                # Gemini nested structure: content.parts[0].text
                content = last_output.content
                if hasattr(content, 'parts') and content.parts:
                    first_part = content.parts[0]
                    if hasattr(first_part, 'text'):
                        report = first_part.text
                    else:
                        report = str(first_part)
                elif hasattr(content, 'text'):
                    report = content.text
                else:
                    report = str(content)
        
        # Path 2: Direct result attribute
        if not report and hasattr(interaction, 'result'):
            result = interaction.result
            if hasattr(result, 'text'):
                report = result.text
            else:
                report = str(result)
        
        # Path 3: Response attribute  
        if not report and hasattr(interaction, 'response'):
            resp = interaction.response
            if hasattr(resp, 'text'):
                report = resp.text
            elif hasattr(resp, 'content'):
                report = str(resp.content)
        
        # Path 4: Fallback to streamed content (critical fix)
        if not report and fallback_text:
            report = fallback_text
            if self.verbose:
                self.logger.debug("Using fallback streamed text for report")
        
        # Try to extract citations from grounding metadata
        if hasattr(interaction, 'outputs') and interaction.outputs:
            for output in interaction.outputs:
                if hasattr(output, 'grounding_metadata'):
                    metadata = output.grounding_metadata
                    if hasattr(metadata, 'grounding_chunks'):
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web:
                                citations.append(Citation(
                                    title=getattr(chunk.web, 'title', ''),
                                    url=getattr(chunk.web, 'uri', ''),
                                ))
        
        # Log warning if report is empty
        if not report:
            self.logger.warning(
                "Gemini response parsing returned empty report. "
                f"Interaction ID: {getattr(interaction, 'id', 'unknown')}, "
                f"Status: {getattr(interaction, 'status', 'unknown')}"
            )
        
        return DeepResearchResponse(
            report=report,
            citations=citations,
            reasoning_steps=reasoning_steps,
            provider="gemini",
            interaction_id=getattr(interaction, 'id', None),
            raw_response=interaction
        )
    
    def _parse_litellm_response(self, response: Any) -> DeepResearchResponse:
        """Parse LiteLLM response (same structure as OpenAI)."""
        return self._parse_openai_response(response)
    
    def _research_openai(
        self,
        query: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        summary_mode: Optional[str] = None,
        web_search: bool = True,
        code_interpreter: bool = False,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        file_ids: Optional[List[str]] = None,
        stream: bool = False,
    ) -> DeepResearchResponse:
        """Perform research using OpenAI Deep Research API."""
        input_messages = []
        
        system_instructions = instructions or self.instructions
        if system_instructions:
            input_messages.append({
                "role": "developer",
                "content": [{"type": "input_text", "text": system_instructions}]
            })
        
        input_messages.append({
            "role": "user",
            "content": [{"type": "input_text", "text": query}]
        })
        
        tools = self._build_openai_tools(
            web_search=web_search,
            code_interpreter=code_interpreter,
            mcp_servers=mcp_servers,
            file_ids=file_ids
        )
        
        if stream:
            return self._research_openai_streaming(
                input_messages=input_messages,
                model=model or self.model,
                summary_mode=summary_mode or self.summary_mode,
                tools=tools
            )
        
        response = self.openai_client.responses.create(
            model=model or self.model,
            input=input_messages,
            reasoning={"summary": summary_mode or self.summary_mode},
            tools=tools if tools else None
        )
        
        return self._parse_openai_response(response)
    
    def _research_openai_streaming(
        self,
        input_messages: List[Dict[str, Any]],
        model: str,
        summary_mode: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> DeepResearchResponse:
        """
        Perform OpenAI research with streaming for real-time progress updates.
        
        Streaming provides:
        - Real-time reasoning summaries (buffered per paragraph)
        - Web search progress updates
        - Incremental text output
        """
        response_id = None
        final_text = ""
        citations = []
        reasoning_steps = []
        web_searches = []
        code_executions = []
        mcp_calls = []
        
        # Buffer for accumulating reasoning text before display
        reasoning_buffer = ""
        
        if self.verbose:
            print("\n" + "=" * 60)
            print("🔍 OPENAI DEEP RESEARCH (Streaming)")
            print("=" * 60 + "\n")
        
        try:
            stream = self.openai_client.responses.create(
                model=model,
                input=input_messages,
                reasoning={"summary": summary_mode},
                tools=tools if tools else None,
                stream=True
            )
            
            for event in stream:
                event_type = getattr(event, 'type', None)
                
                # Capture response ID
                if event_type == "response.created":
                    response_id = getattr(event.response, 'id', None)
                    if self.verbose:
                        print(f"📋 Research started: {response_id}\n")
                
                # Handle reasoning/thinking updates - buffer tokens
                elif event_type == "response.reasoning_summary_text.delta":
                    text = getattr(event, 'delta', '')
                    if text:
                        reasoning_buffer += text
                
                # When reasoning paragraph is complete, display it
                elif event_type == "response.reasoning_summary_text.done":
                    text = getattr(event, 'text', '')
                    if text:
                        reasoning_steps.append(ReasoningStep(text=text))
                        if self.verbose:
                            # Display the complete thought with single 💭
                            print(f"💭 {text}\n", flush=True)
                    reasoning_buffer = ""  # Reset buffer
                
                # Handle web search events
                elif event_type == "response.web_search_call.searching":
                    query = getattr(event, 'query', '')
                    if self.verbose:
                        print(f"🔎 Searching: {query}", flush=True)
                    web_searches.append(WebSearchCall(query=query, status="searching"))
                
                elif event_type == "response.web_search_call.completed":
                    if self.verbose:
                        print("   ✓ Search completed", flush=True)
                
                # Handle output text streaming
                elif event_type == "response.output_text.delta":
                    text = getattr(event, 'delta', '')
                    final_text += text
                    if self.verbose:
                        print(text, end="", flush=True)
                
                # Handle code interpreter events
                elif event_type == "response.code_interpreter_call.code.delta":
                    code = getattr(event, 'delta', '')
                    if self.verbose:
                        print(f"💻 {code}", end="", flush=True)
                
                elif event_type == "response.code_interpreter_call.completed":
                    input_code = getattr(event, 'code', '')
                    output = getattr(event, 'output', '')
                    code_executions.append(CodeExecutionStep(input_code=input_code, output=output))
                
                # Handle MCP events
                elif event_type == "response.mcp_call.arguments.delta":
                    if self.verbose:
                        args = getattr(event, 'delta', '')
                        print(f"🔧 MCP: {args}", end="", flush=True)
                
                # Handle completion
                elif event_type == "response.completed":
                    if self.verbose:
                        print("\n\n" + "=" * 60)
                        print("✅ Research Complete")
                        print("=" * 60 + "\n")
                    
                    # Parse the final response for citations
                    response = getattr(event, 'response', None)
                    if response:
                        return self._parse_openai_response(response)
            
        except Exception as e:
            self.logger.error(f"OpenAI streaming error: {e}")
            raise
        
        # Fallback: construct response from streamed content
        return DeepResearchResponse(
            report=final_text,
            citations=citations,
            reasoning_steps=reasoning_steps,
            web_searches=web_searches,
            code_executions=code_executions,
            mcp_calls=mcp_calls,
            provider="openai",
            interaction_id=response_id
        )
    
    def _research_litellm(
        self,
        query: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        summary_mode: Optional[str] = None,
        web_search: bool = True,
        code_interpreter: bool = False,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> DeepResearchResponse:
        """Perform research using LiteLLM (OpenAI Responses API bridge)."""
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "litellm package is required for LiteLLM provider. "
                "Install with: pip install litellm"
            )
        
        tools = self._build_openai_tools(
            web_search=web_search,
            code_interpreter=code_interpreter,
            mcp_servers=mcp_servers,
            file_ids=file_ids
        )
        
        # Build input for LiteLLM responses
        input_content = query
        if instructions or self.instructions:
            system_instructions = instructions or self.instructions
            input_content = f"{system_instructions}\n\n{query}"
        
        response = litellm.responses(
            model=model or self.model,
            input=input_content,
            tools=tools if tools else None
        )
        
        return self._parse_litellm_response(response)
    
    def _research_gemini(
        self,
        query: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        file_search: bool = False,
        file_search_stores: Optional[List[str]] = None,
        stream: bool = False,
    ) -> DeepResearchResponse:
        """Perform research using Gemini Deep Research API (Interactions API)."""
        # Build input with instructions
        input_text = query
        if instructions or self.instructions:
            system_instructions = instructions or self.instructions
            input_text = f"{system_instructions}\n\n{query}"
        
        tools = self._build_gemini_tools(
            file_search=file_search,
            file_search_stores=file_search_stores
        )
        
        # Create interaction with background=True (required for Deep Research)
        create_params = {
            "input": input_text,
            "agent": model or self.model,
            "background": True,
        }
        
        if tools:
            create_params["tools"] = tools
        
        # Use streaming for real-time progress updates
        if stream:
            return self._research_gemini_streaming(create_params)
        
        # Non-streaming: poll for completion
        interaction = self.gemini_client.interactions.create(**create_params)
        
        if self.verbose:
            self.logger.debug(f"Gemini research started: {interaction.id}")
        
        start_time = time.time()
        while True:
            interaction = self.gemini_client.interactions.get(interaction.id)
            
            if interaction.status == "completed":
                if self.verbose:
                    self.logger.debug("Gemini research completed")
                break
            elif interaction.status == "failed":
                error = getattr(interaction, 'error', 'Unknown error')
                raise RuntimeError(f"Gemini Deep Research failed: {error}")
            elif interaction.status == "cancelled":
                raise RuntimeError("Gemini Deep Research was cancelled")
            
            elapsed = time.time() - start_time
            if elapsed > self.max_wait_time:
                raise TimeoutError(
                    f"Gemini Deep Research timed out after {self.max_wait_time}s"
                )
            
            if self.verbose:
                self.logger.debug(f"Research in progress... ({elapsed:.0f}s)")
            
            time.sleep(self.poll_interval)
        
        return self._parse_gemini_response(interaction)
    
    def _research_gemini_streaming(
        self,
        create_params: Dict[str, Any],
    ) -> DeepResearchResponse:
        """
        Perform Gemini research with streaming for real-time progress updates.
        
        Streaming provides:
        - Real-time thinking summaries (research progress)
        - Incremental text output as it's generated
        - Better user experience for long-running research
        """
        # Enable streaming with thinking summaries
        create_params["stream"] = True
        create_params["agent_config"] = {
            "type": "deep-research",
            "thinking_summaries": "auto"
        }
        
        interaction_id = None
        last_event_id = None
        final_text = ""
        reasoning_steps = []
        is_complete = False
        
        if self.verbose:
            print("\n" + "=" * 60)
            print("🔍 GEMINI DEEP RESEARCH (Streaming)")
            print("=" * 60 + "\n")
        
        try:
            stream = self.gemini_client.interactions.create(**create_params)
            
            for chunk in stream:
                # Capture interaction ID for reconnection
                if chunk.event_type == "interaction.start":
                    interaction_id = chunk.interaction.id
                    if self.verbose:
                        print(f"📋 Research started: {interaction_id}\n")
                
                # Track event ID for potential reconnection
                if hasattr(chunk, 'event_id') and chunk.event_id:
                    last_event_id = chunk.event_id
                
                # Handle content deltas
                if chunk.event_type == "content.delta":
                    delta = chunk.delta
                    if hasattr(delta, 'type'):
                        if delta.type == "text":
                            # Stream final report text
                            text = delta.text if hasattr(delta, 'text') else ""
                            final_text += text
                            if self.verbose:
                                print(text, end="", flush=True)
                        elif delta.type == "thought_summary":
                            # Show thinking/reasoning progress
                            thought = ""
                            if hasattr(delta, 'content') and hasattr(delta.content, 'text'):
                                thought = delta.content.text
                            elif hasattr(delta, 'text'):
                                thought = delta.text
                            if thought:
                                reasoning_steps.append(ReasoningStep(text=thought))
                                if self.verbose:
                                    print(f"💭 {thought}", flush=True)
                
                # Check for completion
                if chunk.event_type == "interaction.complete":
                    is_complete = True
                    if self.verbose:
                        print("\n\n" + "=" * 60)
                        print("✅ Research Complete")
                        print("=" * 60 + "\n")
                    
                    # Poll until interaction status is actually 'completed'
                    # (workaround for timing issue where GET returns stale status)
                    if interaction_id:
                        max_poll_attempts = 30  # 30 seconds max
                        for attempt in range(max_poll_attempts):
                            final_interaction = self.gemini_client.interactions.get(interaction_id)
                            if final_interaction.status == "completed":
                                return self._parse_gemini_response(
                                    final_interaction, 
                                    fallback_text=final_text,
                                    fallback_reasoning=reasoning_steps
                                )
                            elif final_interaction.status in ["failed", "cancelled"]:
                                raise RuntimeError(f"Research {final_interaction.status}")
                            time.sleep(1)
                        
                        # If still not completed, use fallback
                        if self.verbose:
                            self.logger.warning("Interaction not completed after polling, using streamed content")
                        return DeepResearchResponse(
                            report=final_text,
                            reasoning_steps=reasoning_steps,
                            provider="gemini",
                            interaction_id=interaction_id
                        )
                
                elif chunk.event_type == "error":
                    error_msg = getattr(chunk, 'error', 'Unknown streaming error')
                    raise RuntimeError(f"Gemini streaming error: {error_msg}")
        
        except Exception as e:
            # Handle reconnection if needed
            if interaction_id and not is_complete:
                if self.verbose:
                    print(f"\n⚠️ Connection interrupted, attempting to resume...")
                return self._resume_gemini_stream(interaction_id, last_event_id, final_text, reasoning_steps)
            raise
        
        # Fallback: construct response from streamed content
        return DeepResearchResponse(
            report=final_text,
            reasoning_steps=reasoning_steps,
            provider="gemini",
            interaction_id=interaction_id
        )
    
    def _resume_gemini_stream(
        self,
        interaction_id: str,
        last_event_id: Optional[str],
        accumulated_text: str,
        reasoning_steps: List[ReasoningStep],
    ) -> DeepResearchResponse:
        """Resume a Gemini stream after connection interruption."""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                time.sleep(2)  # Brief pause before retry
                
                get_params = {"id": interaction_id, "stream": True}
                if last_event_id:
                    get_params["last_event_id"] = last_event_id
                
                resume_stream = self.gemini_client.interactions.get(**get_params)
                
                for chunk in resume_stream:
                    if hasattr(chunk, 'event_id') and chunk.event_id:
                        last_event_id = chunk.event_id
                    
                    if chunk.event_type == "content.delta":
                        delta = chunk.delta
                        if hasattr(delta, 'type'):
                            if delta.type == "text":
                                text = delta.text if hasattr(delta, 'text') else ""
                                accumulated_text += text
                                if self.verbose:
                                    print(text, end="", flush=True)
                            elif delta.type == "thought_summary":
                                thought = ""
                                if hasattr(delta, 'content') and hasattr(delta.content, 'text'):
                                    thought = delta.content.text
                                if thought:
                                    reasoning_steps.append(ReasoningStep(text=thought))
                                    if self.verbose:
                                        print(f"💭 {thought}", flush=True)
                    
                    if chunk.event_type == "interaction.complete":
                        if self.verbose:
                            print("\n\n✅ Research Complete (resumed)")
                        final_interaction = self.gemini_client.interactions.get(interaction_id)
                        return self._parse_gemini_response(
                            final_interaction,
                            fallback_text=accumulated_text,
                            fallback_reasoning=reasoning_steps
                        )
                
            except Exception as e:
                retry_count += 1
                if self.verbose:
                    print(f"\n⚠️ Retry {retry_count}/{max_retries} failed: {e}")
        
        # Final fallback: poll for completion
        if self.verbose:
            print("\n⚠️ Streaming failed, falling back to polling...")
        
        while True:
            interaction = self.gemini_client.interactions.get(interaction_id)
            if interaction.status == "completed":
                return self._parse_gemini_response(
                    interaction,
                    fallback_text=accumulated_text,
                    fallback_reasoning=reasoning_steps
                )
            elif interaction.status in ["failed", "cancelled"]:
                raise RuntimeError(f"Research {interaction.status}")
            time.sleep(self.poll_interval)
    
    def research(
        self,
        query: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        summary_mode: Optional[Literal["auto", "detailed", "concise"]] = None,
        web_search: Optional[bool] = None,
        code_interpreter: Optional[bool] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        file_ids: Optional[List[str]] = None,
        file_search: Optional[bool] = None,
        file_search_stores: Optional[List[str]] = None,
        stream: bool = True,
    ) -> DeepResearchResponse:
        """
        Perform a deep research query.
        
        Args:
            query: The research question or topic to investigate
            instructions: Override the agent's default instructions
            model: Override the default model
            summary_mode: Summary mode ("auto", "detailed", "concise") - OpenAI only
            web_search: Enable web search - OpenAI only
            code_interpreter: Enable code interpreter - OpenAI only
            mcp_servers: MCP server configurations - OpenAI only
            file_ids: File IDs for code interpreter - OpenAI only
            file_search: Enable file search - Gemini only
            file_search_stores: File search store names - Gemini only
            stream: Enable streaming for real-time progress (default: True)
            
        Returns:
            DeepResearchResponse containing the report, citations, and metadata
            
        Example:
            # Standard research
            result = agent.research(
                "What are the latest developments in quantum computing?",
                summary_mode="detailed"
            )
            
            # Streaming research (Gemini) - shows real-time progress
            result = agent.research(
                "Research AI trends",
                stream=True  # Real-time thinking summaries
            )
            print(result.report)
        """
        start_time = time.time()
        
        if self.verbose and not stream:
            self.logger.debug(f"Starting {self.provider.value} deep research: {query[:100]}...")
        
        try:
            if self.provider == Provider.GEMINI:
                result = self._research_gemini(
                    query=query,
                    instructions=instructions,
                    model=model,
                    file_search=file_search if file_search is not None else self.enable_file_search,
                    file_search_stores=file_search_stores or self.file_search_stores,
                    stream=stream,
                )
            elif self.provider == Provider.LITELLM:
                result = self._research_litellm(
                    query=query,
                    instructions=instructions,
                    model=model,
                    summary_mode=summary_mode or self.summary_mode,
                    web_search=web_search if web_search is not None else self.enable_web_search,
                    code_interpreter=code_interpreter if code_interpreter is not None else self.enable_code_interpreter,
                    mcp_servers=(mcp_servers or []) + self.mcp_servers,
                    file_ids=file_ids,
                )
            else:  # OpenAI
                result = self._research_openai(
                    query=query,
                    instructions=instructions,
                    model=model,
                    summary_mode=summary_mode or self.summary_mode,
                    web_search=web_search if web_search is not None else self.enable_web_search,
                    code_interpreter=code_interpreter if code_interpreter is not None else self.enable_code_interpreter,
                    mcp_servers=(mcp_servers or []) + self.mcp_servers,
                    file_ids=file_ids,
                    stream=stream,
                )
        except Exception as e:
            self.logger.error(f"Deep Research error: {e}")
            raise
        
        elapsed = time.time() - start_time
        if self.verbose:
            self.logger.debug(f"Deep research completed in {elapsed:.1f}s")
            self.logger.debug(f"Report length: {len(result.report)} chars, Citations: {len(result.citations)}")
        
        return result
    
    async def aresearch(
        self,
        query: str,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        summary_mode: Optional[Literal["auto", "detailed", "concise"]] = None,
        web_search: Optional[bool] = None,
        code_interpreter: Optional[bool] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        file_ids: Optional[List[str]] = None,
        file_search: Optional[bool] = None,
        file_search_stores: Optional[List[str]] = None,
    ) -> DeepResearchResponse:
        """
        Async version of research().
        
        For Gemini, this still uses polling but with async sleep.
        For OpenAI, uses the async client.
        """
        start_time = time.time()
        
        if self.verbose:
            self.logger.debug(f"Starting async {self.provider.value} deep research: {query[:100]}...")
        
        try:
            if self.provider == Provider.GEMINI:
                # Gemini async - run sync in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._research_gemini(
                        query=query,
                        instructions=instructions,
                        model=model,
                        file_search=file_search if file_search is not None else self.enable_file_search,
                        file_search_stores=file_search_stores or self.file_search_stores,
                    )
                )
            elif self.provider == Provider.LITELLM:
                # LiteLLM async
                try:
                    import litellm
                except ImportError:
                    raise ImportError("litellm package required")
                
                tools = self._build_openai_tools(
                    web_search=web_search if web_search is not None else self.enable_web_search,
                    code_interpreter=code_interpreter if code_interpreter is not None else self.enable_code_interpreter,
                    mcp_servers=(mcp_servers or []) + self.mcp_servers,
                    file_ids=file_ids,
                )
                
                input_content = query
                if instructions or self.instructions:
                    system_instructions = instructions or self.instructions
                    input_content = f"{system_instructions}\n\n{query}"
                
                response = await litellm.aresponses(
                    model=model or self.model,
                    input=input_content,
                    tools=tools if tools else None
                )
                result = self._parse_litellm_response(response)
            else:  # OpenAI async
                input_messages = []
                system_instructions = instructions or self.instructions
                if system_instructions:
                    input_messages.append({
                        "role": "developer",
                        "content": [{"type": "input_text", "text": system_instructions}]
                    })
                input_messages.append({
                    "role": "user",
                    "content": [{"type": "input_text", "text": query}]
                })
                
                tools = self._build_openai_tools(
                    web_search=web_search if web_search is not None else self.enable_web_search,
                    code_interpreter=code_interpreter if code_interpreter is not None else self.enable_code_interpreter,
                    mcp_servers=(mcp_servers or []) + self.mcp_servers,
                    file_ids=file_ids,
                )
                
                response = await self.async_openai_client.responses.create(
                    model=model or self.model,
                    input=input_messages,
                    reasoning={"summary": summary_mode or self.summary_mode},
                    tools=tools if tools else None
                )
                result = self._parse_openai_response(response)
                
        except Exception as e:
            self.logger.error(f"Async Deep Research error: {e}")
            raise
        
        elapsed = time.time() - start_time
        if self.verbose:
            self.logger.debug(f"Async deep research completed in {elapsed:.1f}s")
        
        return result
    
    def follow_up(
        self,
        query: str,
        previous_interaction_id: str,
        model: Optional[str] = None,
    ) -> DeepResearchResponse:
        """
        Ask a follow-up question based on a previous research interaction.
        
        Only supported for Gemini provider.
        
        Args:
            query: The follow-up question
            previous_interaction_id: ID from a previous research response
            model: Model to use (defaults to gemini-3-pro for follow-ups)
            
        Returns:
            DeepResearchResponse with the follow-up answer
        """
        if self.provider != Provider.GEMINI:
            raise NotImplementedError(
                "Follow-up questions are only supported for Gemini provider"
            )
        
        interaction = self.gemini_client.interactions.create(
            input=query,
            model=model or "gemini-3-pro-preview",
            previous_interaction_id=previous_interaction_id
        )
        
        return self._parse_gemini_response(interaction)
    
    def clarify(
        self,
        query: str,
        model: Optional[str] = None,
    ) -> str:
        """
        Generate clarifying questions for a research query.
        
        Args:
            query: The initial research query
            model: Model to use for generating questions
            
        Returns:
            String containing clarifying questions
        """
        clarifying_prompt = '''
You will be given a research task by a user. Your job is NOT to complete the task yet, 
but instead to ask clarifying questions that would help produce a more specific, 
efficient, and relevant answer.

GUIDELINES:
1. Ask questions that are directly necessary to scope the research output
2. Identify essential attributes not specified (preferences, time frame, budget, audience)
3. Do not invent preferences - ask about them clearly and neutrally
4. Use a bulleted list for multiple questions
5. Prioritize 3-6 questions that would most reduce ambiguity
6. Include examples where helpful
7. Keep the tone conversational and helpful
'''
        
        if self.provider == Provider.GEMINI:
            interaction = self.gemini_client.interactions.create(
                input=f"{clarifying_prompt}\n\nUser query: {query}",
                model=model or "gemini-2.5-flash"
            )
            return interaction.outputs[-1].text if interaction.outputs else ""
        else:
            response = self.openai_client.responses.create(
                model=model or "gpt-4.1-2025-04-14",
                instructions=clarifying_prompt,
                input=query
            )
            return response.output[0].content[0].text
    
    def rewrite_query(
        self,
        query: str,
        model: Optional[str] = None,
    ) -> str:
        """
        Rewrite a research query to be more specific and detailed.
        
        Args:
            query: The initial research query
            model: Model to use for rewriting
            
        Returns:
            Rewritten, more detailed query
        """
        rewriting_prompt = '''
You will be given a research task by a user. Your job is to produce a set of 
instructions for a researcher that will complete the task. Do NOT complete the 
task yourself, just provide instructions on how to complete it.

GUIDELINES:
1. Maximize Specificity and Detail - include all known preferences and key dimensions
2. Fill in Unstated But Necessary Dimensions as Open-Ended
3. Avoid Unwarranted Assumptions - if not provided, state it's flexible
4. Use the First Person - phrase from the user's perspective
5. Request Tables when they would help organize information
6. Include expected output format with appropriate headers
7. Specify sources to prioritize if relevant
'''
        
        if self.provider == Provider.GEMINI:
            interaction = self.gemini_client.interactions.create(
                input=f"{rewriting_prompt}\n\nUser query: {query}",
                model=model or "gemini-2.5-flash"
            )
            return interaction.outputs[-1].text if interaction.outputs else ""
        else:
            response = self.openai_client.responses.create(
                model=model or "gpt-4.1-2025-04-14",
                instructions=rewriting_prompt,
                input=query
            )
            return response.output[0].content[0].text
    
    def __repr__(self):
        return f"DeepResearchAgent(name='{self.name}', provider='{self.provider.value}', model='{self.model}')"
