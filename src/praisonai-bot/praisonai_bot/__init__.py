"""PraisonAI bots and gateway runtime package."""

from __future__ import annotations

__version__ = "0.0.1"

_LAZY_EXPORTS = {
    "Bot": ("praisonai_bot.bots.bot", "Bot"),
    "BotOS": ("praisonai_bot.bots.botos", "BotOS"),
    "WebSocketGateway": ("praisonai_bot.gateway.server", "WebSocketGateway"),
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        mod_path, attr = _LAZY_EXPORTS[name]
        import importlib

        mod = importlib.import_module(mod_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Bot", "BotOS", "WebSocketGateway", "__version__"]
