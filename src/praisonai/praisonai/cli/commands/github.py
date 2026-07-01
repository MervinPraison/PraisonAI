"""Backward-compatibility shim for :mod:`praisonai.cli.commands.github`.

The implementation moved to :mod:`praisonai_code.cli.commands.github` as part
of the praisonai-code extraction (issue #2516 / parent #2512).

This shim aliases the moved module into ``sys.modules`` under the old dotted
path so that:

* ``from praisonai.cli.commands.github import X`` keeps working, and
* ``unittest.mock.patch("praisonai.cli.commands.github.X")`` patches the very
  same module object that the implementation executes against.
"""

import sys as _sys

from praisonai_code.cli.commands import github as _impl

# Make the old dotted path resolve to the exact same module object so that
# attribute patching / monkeypatching stays transparent across both paths.
_sys.modules[__name__] = _impl
