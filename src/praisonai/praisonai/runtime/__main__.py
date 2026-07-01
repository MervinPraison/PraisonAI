"""Shim entrypoint: ``python -m praisonai.runtime`` boots the moved runtime.

Delegates to :mod:`praisonai_code.runtime.__main__` (moved in step C1).
"""

import sys

from praisonai_code.runtime.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
