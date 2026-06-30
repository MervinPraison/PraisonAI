"""
Chat handler mixin for the Agent class.

Contains chat management, response processing, and message formatting.
Extracted from agent.py for better modularity and maintainability.
"""

import logging

logger = logging.getLogger(__name__)


class ChatHandlerMixin:
    """Mixin reserved for chat coordination on the Agent class.

    This is a documented placeholder retained for the public mixin surface.
    Concrete chat logic (``chat``/``achat``, history management, and response
    processing) lives in ``ChatMixin``/``SessionManagerMixin``.
    """
    pass