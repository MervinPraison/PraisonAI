"""Moved to :mod:`praisonai_sandbox.compute.e2b`.

The vendor implementations moved into praisonai-sandbox, which already carries
one optional extra per vendor -- reaching one provider no longer requires the
whole wrapper.

This module *becomes* the new one rather than re-exporting from it. A plain
``from ... import X`` shim looks equivalent until someone monkeypatches a
module-level name through the old path: the patch lands on the shim and the
real module never sees it. Aliasing in ``sys.modules`` keeps every existing
import, attribute and patch working against one shared module object.
"""

import sys

from praisonai_sandbox.compute import e2b as _moved

sys.modules[__name__] = _moved
