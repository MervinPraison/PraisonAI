"""One rule for the ``llm=`` / ``model=`` alias pair.

They name the same thing, but every class used to resolve a call that passed
both differently: ``Agent`` let ``model=`` win, the media agents let ``llm=``
win, ``CodeAgent`` dropped ``model=`` into ``**kwargs``, and the containers
raised ``TypeError`` for an unknown keyword. Passing both is now refused
everywhere with one directed message.
"""
from __future__ import annotations

from typing import Any, Optional


def resolve_model_alias(llm: Any, model: Any, owner: str) -> Optional[Any]:
    """Return the single model selection from the ``llm=``/``model=`` pair.

    Raises:
        TypeError: if both were given. Guessing a winner silently changes
            which vendor is billed.
    """
    if llm is not None and model is not None:
        raise TypeError(
            f"{owner}() received both llm= and model=. They are the same "
            f"parameter, so passing both is ambiguous. Pass only one; "
            f"model= is the canonical name (llm= is a deprecated alias)."
        )
    return model if model is not None else llm


def resolve_model_name(llm: Any, model: Any, owner: str) -> Optional[Any]:
    """``resolve_model_alias`` plus LLMConfig unwrapping to a model string.

    For classes that store a bare model name and take their own base_url=/
    api_key=, where an LLMConfig would otherwise reach litellm as ``model=``.
    """
    chosen = resolve_model_alias(llm, model, owner)
    from ..config import LLMConfig
    return chosen.model if isinstance(chosen, LLMConfig) else chosen
