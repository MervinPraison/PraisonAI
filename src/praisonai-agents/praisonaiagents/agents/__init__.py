"""Agents module for managing multiple AI agents"""
from .agents import Agents, PraisonAIAgents
from .autoagents import AutoAgents
from .auto_rag_agent import AutoRagAgent, AutoRagConfig, RetrievalPolicy
from .protocols import MergeStrategyProtocol, FirstWinsMerge, ConcatMerge, DictMerge

__all__ = [
    'Agents', 'PraisonAIAgents', 'AutoAgents',
    'AutoRagAgent', 'AutoRagConfig', 'RetrievalPolicy',
    'MergeStrategyProtocol', 'FirstWinsMerge', 'ConcatMerge', 'DictMerge',
]
