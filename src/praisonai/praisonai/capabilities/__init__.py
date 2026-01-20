"""
PraisonAI Capabilities Module

This module provides LiteLLM endpoint capability parity for PraisonAI.
All capabilities are lazy-loaded to minimize import overhead.

Capabilities:
- audio: Transcription and text-to-speech
- images: Image generation and editing
- videos: Video generation
- files: File upload and management
- batches: Batch processing
- vector_stores: Vector store management
- embeddings: Text embeddings
- rerank: Document reranking
- moderations: Content moderation
- ocr: Optical character recognition
- assistants: OpenAI-style assistants
- fine_tuning: Model fine-tuning
- responses: Response management
- passthrough: Generic API passthrough
- containers: Container management
- search: Search capabilities
- a2a: Agent-to-agent gateway
"""

__all__ = [
    # Audio
    'transcribe',
    'atranscribe',
    'speech',
    'aspeech',
    # Images
    'image_generate',
    'aimage_generate',
    'image_edit',
    'aimage_edit',
    # Videos
    'video_generate',
    'avideo_generate',
    # Files
    'file_create',
    'afile_create',
    'file_list',
    'afile_list',
    'file_retrieve',
    'afile_retrieve',
    'file_delete',
    'afile_delete',
    'file_content',
    'afile_content',
    # Batches
    'batch_create',
    'abatch_create',
    'batch_list',
    'abatch_list',
    'batch_retrieve',
    'abatch_retrieve',
    'batch_cancel',
    'abatch_cancel',
    # Vector Stores
    'vector_store_create',
    'avector_store_create',
    'vector_store_search',
    'avector_store_search',
    # Embeddings
    'embed',
    'aembed',
    'embedding',  # Alias for embed
    'aembedding',  # Alias for aembed
    # Rerank
    'rerank',
    'arerank',
    # Moderations
    'moderate',
    'amoderate',
    # OCR
    'ocr',
    'aocr',
    # Assistants
    'assistant_create',
    'aassistant_create',
    'assistant_list',
    'aassistant_list',
    # Fine-tuning
    'fine_tuning_create',
    'afine_tuning_create',
    'fine_tuning_list',
    'afine_tuning_list',
    # Responses
    'responses_create',
    'aresponses_create',
    # Passthrough
    'passthrough',
    'apassthrough',
    # Containers
    'container_create',
    'acontainer_create',
    # Search
    'search',
    'asearch',
    # A2A
    'a2a_send',
    'aa2a_send',
    # Completions
    'chat_completion',
    'achat_completion',
    'text_completion',
    'atext_completion',
    # Messages
    'messages_create',
    'amessages_create',
    'count_tokens',
    'acount_tokens',
    # Guardrails
    'apply_guardrail',
    'aapply_guardrail',
    # RAG
    'rag_query',
    'arag_query',
    # Realtime
    'realtime_connect',
    'arealtime_connect',
    'realtime_send',
    'arealtime_send',
    # Skills
    'skill_list',
    'askill_list',
    'skill_load',
    'askill_load',
    # MCP
    'mcp_list_tools',
    'amcp_list_tools',
    'mcp_call_tool',
    'amcp_call_tool',
    # Vector Store Files
    'vector_store_file_create',
    'avector_store_file_create',
    'vector_store_file_list',
    'avector_store_file_list',
    'vector_store_file_delete',
    'avector_store_file_delete',
    # Container Files
    'container_file_read',
    'acontainer_file_read',
    'container_file_write',
    'acontainer_file_write',
    'container_file_list',
    'acontainer_file_list',
    # Result types
    'TranscriptionResult',
    'SpeechResult',
    'ImageResult',
    'FileResult',
    'BatchResult',
    'VectorStoreResult',
    'EmbeddingResult',
    'RerankResult',
    'ModerationResult',
    'OCRResult',
    'CompletionResult',
    'MessageResult',
    'TokenCountResult',
    'GuardrailResult',
    'RAGResult',
    'RealtimeSession',
    'RealtimeEvent',
    'SkillResult',
    'MCPResult',
    'MCPToolCallResult',
    'VectorStoreFileResult',
    'ContainerFileResult',
]

_ATTR_TO_MODULE = {
    # Audio
    'transcribe': 'audio', 'atranscribe': 'audio', 'speech': 'audio', 'aspeech': 'audio',
    'TranscriptionResult': 'audio', 'SpeechResult': 'audio',
    # Images
    'image_generate': 'images', 'aimage_generate': 'images', 'image_edit': 'images',
    'aimage_edit': 'images', 'ImageResult': 'images',
    # Videos
    'video_generate': 'videos', 'avideo_generate': 'videos',
    # Files
    'file_create': 'files', 'afile_create': 'files', 'file_list': 'files',
    'afile_list': 'files', 'file_retrieve': 'files', 'afile_retrieve': 'files',
    'file_delete': 'files', 'afile_delete': 'files', 'file_content': 'files',
    'afile_content': 'files', 'FileResult': 'files',
    # Batches
    'batch_create': 'batches', 'abatch_create': 'batches', 'batch_list': 'batches',
    'abatch_list': 'batches', 'batch_retrieve': 'batches', 'abatch_retrieve': 'batches',
    'batch_cancel': 'batches', 'abatch_cancel': 'batches', 'BatchResult': 'batches',
    # Vector Stores
    'vector_store_create': 'vector_stores', 'avector_store_create': 'vector_stores',
    'vector_store_search': 'vector_stores', 'avector_store_search': 'vector_stores',
    'VectorStoreResult': 'vector_stores',
    # Embeddings
    'embed': 'embeddings', 'aembed': 'embeddings', 'EmbeddingResult': 'embeddings',
    'embedding': 'embeddings', 'aembedding': 'embeddings',  # Aliases
    # Rerank
    'rerank': 'rerank_module', 'arerank': 'rerank_module', 'RerankResult': 'rerank_module',
    # Moderations
    'moderate': 'moderations', 'amoderate': 'moderations', 'ModerationResult': 'moderations',
    # OCR
    'ocr': 'ocr_module', 'aocr': 'ocr_module', 'OCRResult': 'ocr_module',
    # Assistants
    'assistant_create': 'assistants', 'aassistant_create': 'assistants',
    'assistant_list': 'assistants', 'aassistant_list': 'assistants',
    # Fine-tuning
    'fine_tuning_create': 'fine_tuning', 'afine_tuning_create': 'fine_tuning',
    'fine_tuning_list': 'fine_tuning', 'afine_tuning_list': 'fine_tuning',
    # Responses
    'responses_create': 'responses', 'aresponses_create': 'responses',
    # Passthrough
    'passthrough': 'passthrough_module', 'apassthrough': 'passthrough_module',
    # Containers
    'container_create': 'containers', 'acontainer_create': 'containers',
    # Search
    'search': 'search_module', 'asearch': 'search_module',
    # A2A
    'a2a_send': 'a2a', 'aa2a_send': 'a2a',
    # Completions
    'chat_completion': 'completions', 'achat_completion': 'completions',
    'text_completion': 'completions', 'atext_completion': 'completions',
    'CompletionResult': 'completions',
    # Messages
    'messages_create': 'messages', 'amessages_create': 'messages',
    'count_tokens': 'messages', 'acount_tokens': 'messages',
    'MessageResult': 'messages', 'TokenCountResult': 'messages',
    # Guardrails
    'apply_guardrail': 'guardrails', 'aapply_guardrail': 'guardrails',
    'GuardrailResult': 'guardrails',
    # RAG
    'rag_query': 'rag', 'arag_query': 'rag', 'RAGResult': 'rag',
    # Realtime
    'realtime_connect': 'realtime', 'arealtime_connect': 'realtime',
    'realtime_send': 'realtime', 'arealtime_send': 'realtime',
    'RealtimeSession': 'realtime', 'RealtimeEvent': 'realtime',
    # Skills
    'skill_list': 'skills_module', 'askill_list': 'skills_module',
    'skill_load': 'skills_module', 'askill_load': 'skills_module',
    'SkillResult': 'skills_module',
    # MCP
    'mcp_list_tools': 'mcp', 'amcp_list_tools': 'mcp',
    'mcp_call_tool': 'mcp', 'amcp_call_tool': 'mcp',
    'MCPResult': 'mcp', 'MCPToolCallResult': 'mcp',
    # Vector Store Files
    'vector_store_file_create': 'vector_store_files', 'avector_store_file_create': 'vector_store_files',
    'vector_store_file_list': 'vector_store_files', 'avector_store_file_list': 'vector_store_files',
    'vector_store_file_delete': 'vector_store_files', 'avector_store_file_delete': 'vector_store_files',
    'VectorStoreFileResult': 'vector_store_files',
    # Container Files
    'container_file_read': 'container_files', 'acontainer_file_read': 'container_files',
    'container_file_write': 'container_files', 'acontainer_file_write': 'container_files',
    'container_file_list': 'container_files', 'acontainer_file_list': 'container_files',
    'ContainerFileResult': 'container_files',
}

# Module name mapping (for modules that conflict with function names)
_MODULE_ALIASES = {
    'rerank_module': 'rerank',
    'ocr_module': 'ocr',
    'passthrough_module': 'passthrough',
    'search_module': 'search',
    'skills_module': 'skills',
}

def __getattr__(name):
    """Lazy load capabilities to minimize import overhead."""
    if name in _ATTR_TO_MODULE:
        import importlib
        module_name = _ATTR_TO_MODULE[name]
        # Handle module aliases
        actual_module = _MODULE_ALIASES.get(module_name, module_name)
        module = importlib.import_module(f'.{actual_module}', __package__)
        return getattr(module, name)
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
