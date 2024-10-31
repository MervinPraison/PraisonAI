# praisonai/inbuilt_tools/autogen_tools.py

import logging
import inspect

# Try to import praisonai_tools, but don't fail if not available
try:
    from praisonai_tools import (
        CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool,
        DirectoryReadTool, FileReadTool, TXTSearchTool, JSONSearchTool,
        MDXSearchTool, PDFSearchTool, RagTool, ScrapeElementFromWebsiteTool,
        ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool,
        YoutubeChannelSearchTool, YoutubeVideoSearchTool
    )
    TOOLS_AVAILABLE = True
except ImportError:
    TOOLS_AVAILABLE = False

def create_autogen_tool_function(tool_class):
    """
    Create a function that wraps a tool for autogen.
    
    Args:
        tool_class: The tool class to wrap
        
    Returns:
        function: A function that can be used with autogen agents
    """
    if not TOOLS_AVAILABLE:
        return None
        
    def tool_function(assistant, user_proxy):
        """
        Wrapper function for the tool that works with autogen.
        
        Args:
            assistant: The autogen assistant agent
            user_proxy: The autogen user proxy agent
        """
        tool_instance = tool_class()
        
        # Get the tool's run method signature
        sig = inspect.signature(tool_instance.run)
        param_names = list(sig.parameters.keys())
        
        def wrapped_function(*args, **kwargs):
            try:
                # Map positional arguments to named parameters
                named_args = dict(zip(param_names, args))
                # Combine with keyword arguments
                all_args = {**named_args, **kwargs}
                # Run the tool
                result = tool_instance.run(**all_args)
                return str(result)
            except Exception as e:
                logging.error(f"Error running {tool_class.__name__}: {str(e)}")
                return f"Error: {str(e)}"
        
        # Add the function to the assistant's function map
        assistant.register_function(
            function_map={
                tool_class.__name__: wrapped_function
            },
            name_to_args={
                tool_class.__name__: {
                    param: "" for param in param_names
                }
            },
            description=tool_instance.__doc__ or f"Use {tool_class.__name__} to perform operations"
        )
    
    return tool_function if TOOLS_AVAILABLE else None

# Only create tool functions if praisonai_tools is available
if TOOLS_AVAILABLE:
    # Create autogen wrapper functions for each tool
    autogen_CSVSearchTool = create_autogen_tool_function(CSVSearchTool)
    autogen_CodeDocsSearchTool = create_autogen_tool_function(CodeDocsSearchTool)
    autogen_DirectorySearchTool = create_autogen_tool_function(DirectorySearchTool)
    autogen_DOCXSearchTool = create_autogen_tool_function(DOCXSearchTool)
    autogen_DirectoryReadTool = create_autogen_tool_function(DirectoryReadTool)
    autogen_FileReadTool = create_autogen_tool_function(FileReadTool)
    autogen_TXTSearchTool = create_autogen_tool_function(TXTSearchTool)
    autogen_JSONSearchTool = create_autogen_tool_function(JSONSearchTool)
    autogen_MDXSearchTool = create_autogen_tool_function(MDXSearchTool)
    autogen_PDFSearchTool = create_autogen_tool_function(PDFSearchTool)
    autogen_RagTool = create_autogen_tool_function(RagTool)
    autogen_ScrapeElementFromWebsiteTool = create_autogen_tool_function(ScrapeElementFromWebsiteTool)
    autogen_ScrapeWebsiteTool = create_autogen_tool_function(ScrapeWebsiteTool)
    autogen_WebsiteSearchTool = create_autogen_tool_function(WebsiteSearchTool)
    autogen_XMLSearchTool = create_autogen_tool_function(XMLSearchTool)
    autogen_YoutubeChannelSearchTool = create_autogen_tool_function(YoutubeChannelSearchTool)
    autogen_YoutubeVideoSearchTool = create_autogen_tool_function(YoutubeVideoSearchTool)

    # Export all tool functions
    __all__ = [
        'autogen_CSVSearchTool',
        'autogen_CodeDocsSearchTool',
        'autogen_DirectorySearchTool',
        'autogen_DOCXSearchTool',
        'autogen_DirectoryReadTool',
        'autogen_FileReadTool',
        'autogen_TXTSearchTool',
        'autogen_JSONSearchTool',
        'autogen_MDXSearchTool',
        'autogen_PDFSearchTool',
        'autogen_RagTool',
        'autogen_ScrapeElementFromWebsiteTool',
        'autogen_ScrapeWebsiteTool',
        'autogen_WebsiteSearchTool',
        'autogen_XMLSearchTool',
        'autogen_YoutubeChannelSearchTool',
        'autogen_YoutubeVideoSearchTool',
    ]
else:
    # If tools are not available, export an empty list
    __all__ = []