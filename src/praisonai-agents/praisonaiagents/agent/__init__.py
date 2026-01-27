"""Agent module for AI agents - uses lazy loading for performance"""

# Lazy loading cache
_lazy_cache = {}

def __getattr__(name):
    """Lazy load agent classes to avoid importing rich at startup."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    # Core Agent - always needed
    if name == 'Agent':
        from .agent import Agent
        _lazy_cache[name] = Agent
        return Agent
    
    # Specialized agents - lazy loaded (import rich)
    if name == 'ImageAgent':
        from .image_agent import ImageAgent
        _lazy_cache[name] = ImageAgent
        return ImageAgent
    elif name == 'VideoAgent':
        from .video_agent import VideoAgent
        _lazy_cache[name] = VideoAgent
        return VideoAgent
    elif name == 'VideoConfig':
        from .video_agent import VideoConfig
        _lazy_cache[name] = VideoConfig
        return VideoConfig
    elif name == 'AudioAgent':
        from .audio_agent import AudioAgent
        _lazy_cache[name] = AudioAgent
        return AudioAgent
    elif name == 'AudioConfig':
        from .audio_agent import AudioConfig
        _lazy_cache[name] = AudioConfig
        return AudioConfig
    elif name == 'OCRAgent':
        from .ocr_agent import OCRAgent
        _lazy_cache[name] = OCRAgent
        return OCRAgent
    elif name == 'OCRConfig':
        from .ocr_agent import OCRConfig
        _lazy_cache[name] = OCRConfig
        return OCRConfig
    elif name == 'ContextAgent':
        from .context_agent import ContextAgent
        _lazy_cache[name] = ContextAgent
        return ContextAgent
    elif name == 'create_context_agent':
        from .context_agent import create_context_agent
        _lazy_cache[name] = create_context_agent
        return create_context_agent
    elif name == 'RouterAgent':
        from .router_agent import RouterAgent
        _lazy_cache[name] = RouterAgent
        return RouterAgent
    elif name == 'VisionAgent':
        from .vision_agent import VisionAgent
        _lazy_cache[name] = VisionAgent
        return VisionAgent
    elif name == 'VisionConfig':
        from .vision_agent import VisionConfig
        _lazy_cache[name] = VisionConfig
        return VisionConfig
    elif name == 'EmbeddingAgent':
        from .embedding_agent import EmbeddingAgent
        _lazy_cache[name] = EmbeddingAgent
        return EmbeddingAgent
    elif name == 'EmbeddingConfig':
        from .embedding_agent import EmbeddingConfig
        _lazy_cache[name] = EmbeddingConfig
        return EmbeddingConfig
    elif name == 'RealtimeAgent':
        from .realtime_agent import RealtimeAgent
        _lazy_cache[name] = RealtimeAgent
        return RealtimeAgent
    elif name == 'RealtimeConfig':
        from .realtime_agent import RealtimeConfig
        _lazy_cache[name] = RealtimeConfig
        return RealtimeConfig
    elif name == 'CodeAgent':
        from .code_agent import CodeAgent
        _lazy_cache[name] = CodeAgent
        return CodeAgent
    elif name == 'CodeConfig':
        from .code_agent import CodeConfig
        _lazy_cache[name] = CodeConfig
        return CodeConfig
    
    # Handoff - lightweight
    _handoff_names = {
        'Handoff', 'handoff', 'handoff_filters', 
        'RECOMMENDED_PROMPT_PREFIX', 'prompt_with_handoff_instructions',
        'HandoffConfig', 'HandoffResult', 'HandoffInputData',
        'ContextPolicy', 'HandoffError', 'HandoffCycleError', 
        'HandoffDepthError', 'HandoffTimeoutError'
    }
    if name in _handoff_names:
        from . import handoff as _handoff_module
        value = getattr(_handoff_module, name)
        _lazy_cache[name] = value
        return value
    
    # Deep research agent
    _deep_research_names = {
        'DeepResearchAgent', 'DeepResearchResponse', 'Citation',
        'ReasoningStep', 'WebSearchCall', 'CodeExecutionStep',
        'MCPCall', 'FileSearchCall', 'Provider'
    }
    if name in _deep_research_names:
        from . import deep_research_agent as _dr_module
        value = getattr(_dr_module, name)
        _lazy_cache[name] = value
        return value
    
    # Query rewriter agent
    _query_rewriter_names = {'QueryRewriterAgent', 'RewriteStrategy', 'RewriteResult'}
    if name in _query_rewriter_names:
        from . import query_rewriter_agent as _qr_module
        value = getattr(_qr_module, name)
        _lazy_cache[name] = value
        return value
    
    # Prompt expander agent
    _prompt_expander_names = {'PromptExpanderAgent', 'ExpandStrategy', 'ExpandResult'}
    if name in _prompt_expander_names:
        from . import prompt_expander_agent as _pe_module
        value = getattr(_pe_module, name)
        _lazy_cache[name] = value
        return value
    
    # Protocols - lightweight
    _protocol_names = {
        'AgentProtocol', 'RunnableAgentProtocol', 'ToolAwareAgentProtocol',
        'MemoryAwareAgentProtocol', 'FullAgentProtocol', 'ContextEngineerProtocol'
    }
    if name in _protocol_names:
        from . import protocols as _protocols_module
        value = getattr(_protocols_module, name)
        _lazy_cache[name] = value
        return value
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'Agent',
    'ImageAgent',
    'VideoAgent',
    'VideoConfig',
    'AudioAgent',
    'AudioConfig',
    'OCRAgent',
    'OCRConfig',
    'VisionAgent',
    'VisionConfig',
    'EmbeddingAgent',
    'EmbeddingConfig',
    'RealtimeAgent',
    'RealtimeConfig',
    'CodeAgent',
    'CodeConfig',
    'ContextAgent',
    'create_context_agent',
    'Handoff',
    'handoff',
    'handoff_filters',
    'RECOMMENDED_PROMPT_PREFIX',
    'prompt_with_handoff_instructions',
    'HandoffConfig',
    'HandoffResult',
    'HandoffInputData',
    'ContextPolicy',
    'HandoffError',
    'HandoffCycleError',
    'HandoffDepthError',
    'HandoffTimeoutError',
    'RouterAgent',
    'DeepResearchAgent',
    'DeepResearchResponse',
    'Citation',
    'ReasoningStep',
    'WebSearchCall',
    'CodeExecutionStep',
    'MCPCall',
    'FileSearchCall',
    'Provider',
    'QueryRewriterAgent',
    'RewriteStrategy',
    'RewriteResult',
    'PromptExpanderAgent',
    'ExpandStrategy',
    'ExpandResult',
    # Protocols
    'AgentProtocol',
    'RunnableAgentProtocol',
    'ToolAwareAgentProtocol',
    'MemoryAwareAgentProtocol',
    'FullAgentProtocol',
    'ContextEngineerProtocol',
]