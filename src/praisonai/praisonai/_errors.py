"""Private root for wrapper exceptions.

Joins every ``praisonai.*`` error to the core SDK hierarchy so downstream code
can catch them all with ``except praisonaiagents.PraisonAIError``. Concrete
classes keep their stdlib parents (``ValueError``, ``RuntimeError``,
``TimeoutError``) via multiple inheritance, so existing ``except`` sites are
unaffected.
"""

from praisonaiagents.errors import PraisonAIError


class _WrapperError(PraisonAIError):
    """Base for wrapper errors; keeps plain ``str(e)`` and original ``args``."""

    def __init__(self, *args):
        PraisonAIError.__init__(self, str(args[0]) if args else "")
        self.args = args

    # Core's __str__ decorates with category/agent/run id; wrapper errors are
    # shown verbatim to CLI users, so keep the stdlib formatting.
    __str__ = Exception.__str__
