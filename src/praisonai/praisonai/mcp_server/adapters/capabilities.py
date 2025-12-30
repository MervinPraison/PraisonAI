"""
Capabilities Adapter

Maps PraisonAI capabilities (audio, images, embeddings, etc.) to MCP tools.
"""

import logging
from typing import List, Optional

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_capability_tools() -> None:
    """Register all capability-based MCP tools."""
    
    # Audio tools
    @register_tool("praisonai.audio.transcribe")
    def audio_transcribe(
        file_path: str,
        model: str = "whisper-1",
        language: Optional[str] = None,
    ) -> str:
        """Transcribe audio file to text."""
        from praisonai.capabilities import transcribe
        result = transcribe(file=file_path, model=model, language=language)
        return result.text if hasattr(result, "text") else str(result)
    
    @register_tool("praisonai.audio.speech")
    def audio_speech(
        text: str,
        model: str = "tts-1",
        voice: str = "alloy",
    ) -> str:
        """Convert text to speech."""
        from praisonai.capabilities import speech
        result = speech(input=text, model=model, voice=voice)
        return f"Audio generated: {result}"
    
    # Image tools
    @register_tool("praisonai.images.generate")
    def images_generate(
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        n: int = 1,
    ) -> str:
        """Generate images from text prompt."""
        from praisonai.capabilities import image_generate
        result = image_generate(prompt=prompt, model=model, size=size, n=n)
        if hasattr(result, "data"):
            urls = [img.url for img in result.data if hasattr(img, "url")]
            return f"Generated {len(urls)} image(s): {urls}"
        return str(result)
    
    # Embedding tools
    @register_tool("praisonai.embed.create")
    def embed_create(
        text: str,
        model: str = "text-embedding-3-small",
    ) -> str:
        """Create text embeddings."""
        from praisonai.capabilities import embed
        result = embed(input=text, model=model)
        if hasattr(result, "data") and result.data:
            return f"Embedding created with {len(result.data[0].embedding)} dimensions"
        return str(result)
    
    # Moderation tools
    @register_tool("praisonai.moderate.check")
    def moderate_check(text: str) -> str:
        """Check content for policy violations."""
        from praisonai.capabilities import moderate
        result = moderate(input=text)
        if hasattr(result, "results") and result.results:
            flagged = result.results[0].flagged
            return f"Content flagged: {flagged}"
        return str(result)
    
    # Chat completion
    @register_tool("praisonai.chat.completion")
    def chat_completion(
        message: str,
        model: str = "gpt-4o-mini",
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate chat completion."""
        from praisonai.capabilities import chat_completion
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        result = chat_completion(model=model, messages=messages)
        if hasattr(result, "choices") and result.choices:
            return result.choices[0].message.content
        return str(result)
    
    # Rerank
    @register_tool("praisonai.rerank")
    def rerank_documents(
        query: str,
        documents: List[str],
        model: str = "rerank-english-v2.0",
        top_n: int = 5,
    ) -> str:
        """Rerank documents by relevance to query."""
        from praisonai.capabilities import rerank
        result = rerank(query=query, documents=documents, model=model, top_n=top_n)
        return str(result)
    
    # RAG
    @register_tool("praisonai.rag.query")
    def rag_query(
        query: str,
        collection: str = "default",
    ) -> str:
        """Query RAG knowledge base."""
        from praisonai.capabilities import rag_query
        result = rag_query(query=query, collection=collection)
        return str(result)
    
    # Search
    @register_tool("praisonai.search")
    def search_web(query: str) -> str:
        """Search the web."""
        from praisonai.capabilities import search
        result = search(query=query)
        return str(result)
    
    # Guardrails
    @register_tool("praisonai.guardrails.check")
    def guardrails_check(
        text: str,
        guardrail_name: str = "default",
    ) -> str:
        """Apply guardrail to text."""
        from praisonai.capabilities import apply_guardrail
        result = apply_guardrail(text=text, guardrail_name=guardrail_name)
        return str(result)
    
    logger.info("Registered capability MCP tools")


def register_all_tools() -> None:
    """Register all MCP tools from all adapters."""
    register_capability_tools()
    
    # Import and register other adapters
    try:
        from .agents import register_agent_tools
        register_agent_tools()
    except ImportError:
        logger.debug("Agent tools adapter not available")
    
    try:
        from .memory import register_memory_tools
        register_memory_tools()
    except ImportError:
        logger.debug("Memory tools adapter not available")
    
    try:
        from .knowledge import register_knowledge_tools
        register_knowledge_tools()
    except ImportError:
        logger.debug("Knowledge tools adapter not available")
    
    logger.info("All MCP tools registered")
