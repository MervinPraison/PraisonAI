"""Pure resolvers for ``Agent.__init__`` parameters (G-19).

Each function turns one user-facing parameter into what ``Agent`` stores, so the
logic is unit-testable without building an agent. Names carry an ``agent_``
infix because ``config.resolve_<param>`` already exists with different
defaults (for example ``resolve_caching(None)`` returns ``None``).
"""

from typing import Any, Dict, Optional, Tuple

from .feature_configs import CachingConfig, KnowledgeConfig, PlanningConfig, ReflectionConfig, TemplateConfig
from .param_resolver import ArrayMode, resolve
from .presets import CACHING_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS


def resolve_agent_caching(caching: Any) -> Tuple[Optional[CachingConfig], bool, Optional[bool]]:
    """``caching=`` -> ``(config, cache, prompt_caching)``.

    ``None`` and ``True`` mean the default (enabled); ``False`` disables it and
    gives no config; presets, dicts and ``CachingConfig`` are resolved as before.
    """
    if caching is None or caching is True:
        config = CachingConfig()
    elif caching is False:
        config = None
    elif isinstance(caching, CachingConfig):
        config = caching
    else:
        config = resolve(
            value=caching,
            param_name="caching",
            config_class=CachingConfig,
            presets=CACHING_PRESETS,
            default=CachingConfig(),
        )
    if config:
        return config, config.enabled, config.prompt_caching
    if caching is False:
        return None, False, None
    return config, True, None


def resolve_agent_templates(templates: Any) -> Tuple[Optional[TemplateConfig], Optional[str], Optional[str], Optional[str], bool]:
    """``templates=`` -> ``(config, system_template, prompt_template, response_template, use_system_prompt)``.

    ``None`` (and, as before, a value ``resolve`` cannot turn into a config)
    means no templates and the default system prompt.
    """
    if templates is None:
        config = None
    elif isinstance(templates, TemplateConfig):
        config = templates
    elif isinstance(templates, dict):
        config = TemplateConfig(**templates)
    else:
        config = resolve(value=templates, param_name="templates", config_class=TemplateConfig, default=None)
    if config:
        return config, config.system, config.prompt, config.response, config.use_system_prompt
    return config, None, None, None, True


def resolve_agent_planning(planning: Any) -> Tuple[Optional[PlanningConfig], Dict[str, Any]]:
    """``planning=`` -> ``(config, overrides)``.

    *overrides* holds only the ``planning`` / ``planning_tools`` /
    ``planning_reasoning`` / ``plan_mode`` values this parameter sets; keys it
    does not set keep the caller's current value, as the inline block did.
    """
    if planning is None or planning is False:
        config = None
    elif planning is True:
        config = PlanningConfig()
    elif isinstance(planning, PlanningConfig):
        config = planning
    else:
        config = resolve(
            value=planning,
            param_name="planning",
            config_class=PlanningConfig,
            presets=PLANNING_PRESETS,
            string_mode="llm_model",
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=None,
        )
    if config is not None:
        if isinstance(config, PlanningConfig):
            return config, {"planning": True, "planning_tools": config.tools,
                            "planning_reasoning": config.reasoning, "plan_mode": config.read_only}
        return config, {"planning": bool(config)}
    return config, {"planning": False}


def resolve_agent_reflection(reflection: Any) -> Tuple[Optional[ReflectionConfig], Dict[str, Any]]:
    """``reflection=`` -> ``(config, overrides)``.

    *overrides* holds only the ``self_reflect`` / ``min_reflect`` /
    ``max_reflect`` / ``reflect_llm`` / ``reflect_prompt`` values this
    parameter sets; ``None`` sets nothing, as the inline block did.
    """
    if reflection is None or reflection is False:
        config = None
    elif reflection is True:
        config = ReflectionConfig()
    elif isinstance(reflection, ReflectionConfig):
        config = reflection
    else:
        config = resolve(
            value=reflection,
            param_name="reflection",
            config_class=ReflectionConfig,
            presets=REFLECTION_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=None,
        )
    if config is not None:
        if isinstance(config, ReflectionConfig):
            return config, {"self_reflect": True, "min_reflect": config.min_iterations,
                            "max_reflect": config.max_iterations, "reflect_llm": config.llm,
                            "reflect_prompt": config.prompt}
        return config, {"self_reflect": bool(config)}
    if reflection is True:
        return config, {"self_reflect": True}
    if reflection is False:
        return config, {"self_reflect": False}
    return config, {}


def resolve_agent_knowledge(knowledge: Any, user_retrieval_config: Any
                            ) -> Tuple[Any, Any, Any, Optional[Dict[str, Any]]]:
    """``knowledge=`` -> ``(config, knowledge, retrieval_config, embedder_config)``.

    ``knowledge`` comes back as what Agent hands to Knowledge: the sources
    list, a live instance, or ``None``. ``retrieval_config`` is the dict
    derived from a ``KnowledgeConfig`` with ``user_retrieval_config``
    (``Agent(retrieval_config=)``) merged on top.
    """
    retrieval_config = None
    embedder_config = None
    
    # Fast path: None/False -> no knowledge (skip resolve() call)
    if knowledge is None or knowledge is False:
        _knowledge_config = None
    elif knowledge is True:
        _knowledge_config = KnowledgeConfig()
    elif isinstance(knowledge, KnowledgeConfig):
        _knowledge_config = knowledge
    elif isinstance(knowledge, list):
        _knowledge_config = KnowledgeConfig(sources=knowledge)
    elif hasattr(knowledge, 'search') and hasattr(knowledge, 'add'):
        _knowledge_config = knowledge  # Knowledge instance passthrough
    else:
        _knowledge_config = resolve(
            value=knowledge,
            param_name="knowledge",
            config_class=KnowledgeConfig,
            instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
            array_mode=ArrayMode.SOURCES_WITH_CONFIG,
            string_mode="path_as_source",
            default=None,
        )
    
    if _knowledge_config is not None:
        if hasattr(_knowledge_config, 'search') and hasattr(_knowledge_config, 'add'):
            # Knowledge instance - pass through
            knowledge = _knowledge_config
        elif isinstance(_knowledge_config, KnowledgeConfig):
            embedder_config = _knowledge_config.embedder_config
            # Every declared field is forwarded. Previously only top_k /
            # rerank survived: 'threshold' was spelled 'min_score' by
            # RetrievalConfig.from_dict, 'rerank_model' had no field at
            # all, and chunking + vector_store were never forwarded, so
            # those settings were silently inert.
            _chunker = _knowledge_config.chunker or {}
            _strategy = _knowledge_config.chunking_strategy
            _strategy = getattr(_strategy, 'value', _strategy)
            _vector_store = _knowledge_config.vector_store or {}
            retrieval_config = {
                'enabled': _knowledge_config.auto_retrieve,
                'top_k': _knowledge_config.retrieval_k,
                'min_score': _knowledge_config.retrieval_threshold,
                'rerank': _knowledge_config.rerank,
                'rerank_model': _knowledge_config.rerank_model,
                'chunking_strategy': _chunker.get('type', _strategy),
                'chunk_size': _chunker.get('chunk_size', _knowledge_config.chunk_size),
                'chunk_overlap': _chunker.get(
                    'chunk_overlap', _knowledge_config.chunk_overlap),
            }
            if _vector_store:
                _vs = dict(_vector_store)
                _vs_provider = _vs.pop('provider', None)
                if _vs_provider:
                    retrieval_config['vector_store_provider'] = _vs_provider
                _vs_inner = _vs.pop('config', None)
                if isinstance(_vs_inner, dict):
                    _vs.update(_vs_inner)
                if 'collection_name' in _vs:
                    retrieval_config['collection_name'] = _vs.pop('collection_name')
                if 'path' in _vs:
                    retrieval_config['persist_path'] = _vs.pop('path')
                if _vs:
                    retrieval_config['vector_store_config'] = _vs
            # Forward embedder settings so they reach Knowledge (mem0).
            # embedder is a provider shorthand (e.g. "gemini"); embedder_config
            # is the full mem0 embedder dict. Only override when explicitly set.
            if _knowledge_config.embedder and _knowledge_config.embedder != "openai":
                retrieval_config.setdefault('embedder_provider', _knowledge_config.embedder)
            if _knowledge_config.embedder_config:
                retrieval_config.setdefault('embedder_config', _knowledge_config.embedder_config)
            # `config=` is an escape hatch for keys the dataclass does not
            # model. It now overrides the resolved values instead of
            # replacing the whole dict, which silently reset retrieval_k.
            if _knowledge_config.config:
                retrieval_config.update(_knowledge_config.config)
            knowledge = _knowledge_config.sources if _knowledge_config.sources else None
        elif isinstance(_knowledge_config, list):
            knowledge = _knowledge_config
    elif knowledge is False:
        knowledge = None

    # Explicit retrieval_config= (the RAG tuning surface shown in the docs
    # and docstring examples) is merged on top of whatever the knowledge=
    # param derived. A dict overrides the derived keys; a RetrievalConfig
    # instance (or when no knowledge= was given) replaces it wholesale so
    # the downstream RetrievalConfig resolver (in Agent.__init__) receives it unchanged.
    if user_retrieval_config is not None:
        if isinstance(user_retrieval_config, dict) and isinstance(retrieval_config, dict):
            retrieval_config.update(user_retrieval_config)
        else:
            retrieval_config = user_retrieval_config
    return _knowledge_config, knowledge, retrieval_config, embedder_config
