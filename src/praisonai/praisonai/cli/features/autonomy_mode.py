"""Compatibility alias for the CLI autonomy handlers and their enums."""

import sys as _sys

from praisonai_code.cli.features import autonomy_mode as _impl

_sys.modules[__name__] = _impl
