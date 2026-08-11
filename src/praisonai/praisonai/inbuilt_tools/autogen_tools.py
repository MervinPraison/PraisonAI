# praisonai/inbuilt_tools/autogen_tools.py

# Try to import praisonai_tools, but don't fail if not available.
# This presence probe feeds `inbuilt_tools/__init__.py`'s PRAISONAI_TOOLS_AVAILABLE
# accessor and the release `from praisonai.inbuilt_tools import *` smoke test.
try:
    from praisonai_tools import (  # noqa: F401 — presence probe only
        CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool,
        DirectoryReadTool, FileReadTool, TXTSearchTool, JSONSearchTool,
        MDXSearchTool, PDFSearchTool, RagTool, ScrapeElementFromWebsiteTool,
        ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool,
        YoutubeChannelSearchTool, YoutubeVideoSearchTool
    )
    TOOLS_AVAILABLE = True
except ImportError:
    TOOLS_AVAILABLE = False

# Legacy autogen_<Tool> wrappers and create_autogen_tool_function() removed:
# their only consumer, ToolRegistry.register_builtin_autogen_adapters(), was
# deleted in the #1590 fix. The canonical AutoGen path is now
# framework_adapters/autogen_adapter.py.
__all__ = []
