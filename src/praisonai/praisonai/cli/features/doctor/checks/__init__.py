"""
Doctor checks package.

Contains all individual check implementations organized by category.
"""

# Import all check modules to register them
def register_all_checks():
    """Register all doctor checks."""
    from . import env_checks
    from . import config_checks
    from . import tools_checks
    from . import db_checks
    from . import mcp_checks
    from . import obs_checks
    from . import skills_checks
    from . import memory_checks
    from . import permissions_checks
    from . import network_checks
    from . import performance_checks
    from . import selftest_checks
    from . import serve_checks
    from . import lsp_checks
    from . import acp_checks
