# praisonai/inc/__init__.py
# Lazy loading - PraisonAIModel is only imported when accessed
# This avoids the ~3500ms langchain_openai import at CLI startup

def __getattr__(name):
    """Lazy load PraisonAIModel only when accessed."""
    if name == "PraisonAIModel":
        from .models import PraisonAIModel
        return PraisonAIModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["PraisonAIModel"]