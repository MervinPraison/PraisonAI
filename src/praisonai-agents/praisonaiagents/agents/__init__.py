"""Agents module for managing multiple AI agents.

AgentManager is the primary class for multi-agent coordination.
Agents is a deprecated alias for backward compatibility.
"""
from .agents import AgentManager, Agents, PraisonAIAgents
from .autoagents import AutoAgents
from .auto_rag_agent import AutoRagAgent, AutoRagConfig, RetrievalPolicy
from .protocols import MergeStrategyProtocol, FirstWinsMerge, ConcatMerge, DictMerge

__all__ = [
    'AgentManager',  # Primary class (v0.14.16+)
    'Agents',  # Deprecated alias for AgentManager
    'PraisonAIAgents',  # Deprecated alias for AgentManager
    'AutoAgents',
    'AutoRagAgent', 'AutoRagConfig', 'RetrievalPolicy',
    'MergeStrategyProtocol', 'FirstWinsMerge', 'ConcatMerge', 'DictMerge',
]
