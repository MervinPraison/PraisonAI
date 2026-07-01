"""Backward-compatibility shim for :mod:`praisonai.cli.commands.replay`.

The implementation moved to :mod:`praisonai_code.cli.commands.replay` as part
of the praisonai-code extraction (issue #2516 / parent #2512).

This shim aliases the moved module into ``sys.modules`` under the old dotted
path so that:

* ``from praisonai.cli.commands.replay import X`` keeps working, and
* ``unittest.mock.patch("praisonai.cli.commands.replay.X")`` patches the very
  same module object that the implementation executes against.
"""

import sys as _sys

from praisonai_code.cli.commands import replay as _impl

# Make the old dotted path resolve to the exact same module object so that
# attribute patching / monkeypatching stays transparent across both paths.
_sys.modules[__name__] = _impl
