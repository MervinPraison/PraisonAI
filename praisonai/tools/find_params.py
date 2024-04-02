from crewai_tools import (
    CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool, DirectoryReadTool,
    FileReadTool, TXTSearchTool, JSONSearchTool, MDXSearchTool, PDFSearchTool, RagTool,
    ScrapeElementFromWebsiteTool, ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool, YoutubeChannelSearchTool,
    YoutubeVideoSearchTool
)
import inspect

# Assuming the tool classes are imported correctly as in the original request

tools_classes = {
    'CodeDocsSearchTool': CodeDocsSearchTool,
    'CSVSearchTool': CSVSearchTool,
    'DirectorySearchTool': DirectorySearchTool,
    'DOCXSearchTool': DOCXSearchTool,
    'DirectoryReadTool': DirectoryReadTool,
    'FileReadTool': FileReadTool,
    'TXTSearchTool': TXTSearchTool,
    'JSONSearchTool': JSONSearchTool,
    'MDXSearchTool': MDXSearchTool,
    'PDFSearchTool': PDFSearchTool,
    'RagTool': RagTool,
    'ScrapeElementFromWebsiteTool': ScrapeElementFromWebsiteTool,
    'ScrapeWebsiteTool': ScrapeWebsiteTool,
    'WebsiteSearchTool': WebsiteSearchTool,
    'XMLSearchTool': XMLSearchTool,
    'YoutubeChannelSearchTool': YoutubeChannelSearchTool,
    'YoutubeVideoSearchTool': YoutubeVideoSearchTool,
}

for tool_name, tool_class in tools_classes.items():
    # Inspect the constructor (__init__) to get its parameters, excluding 'self'
    constructor_params = inspect.signature(tool_class.__init__).parameters
    param_names = [p for p in constructor_params if p != 'self']

    # Attempt to instantiate the tool with dummy or default values for parameters
    try:
        # Creating a dummy parameters dict with None or empty values based on parameter name
        dummy_params = {param: None if param != 'website_url' else 'http://example.com' for param in param_names}
        instance = tool_class(**dummy_params)
        tool_description = getattr(instance, "description", "No description attribute")
    except Exception as e:
        tool_description = f"Error instantiating tool for description extraction: {str(e)}"

    # Printing tool class name, its constructor parameters, and description
    print(f"Tool Class: {tool_name}")
    print(f"Constructor Parameters: {', '.join(param_names)}")
    print(f"Description: {tool_description}\n")

# Tool Class: CodeDocsSearchTool
# Constructor Parameters: docs_url, kwargs
# Description: Search a Code Docs content(search_query: 'string', docs_url: 'string') - A tool that can be used to semantic search a query from a Code Docs content.

# Tool Class: CSVSearchTool
# Constructor Parameters: csv, kwargs
# Description: Search a CSV's content(search_query: 'string', csv: 'string') - A tool that can be used to semantic search a query from a CSV's content.

# Tool Class: DirectorySearchTool
# Constructor Parameters: directory, kwargs
# Description: Search a directory's content(search_query: 'string', directory: 'string') - A tool that can be used to semantic search a query from a directory's content.

# Tool Class: DOCXSearchTool
# Constructor Parameters: docx, kwargs
# Description: Search a DOCX's content(search_query: 'string', docx: 'string') - A tool that can be used to semantic search a query from a DOCX's content.

# Tool Class: DirectoryReadTool
# Constructor Parameters: directory, kwargs
# Description: List files in directory(directory: 'string') - A tool that can be used to recursively list a directory's content.

# Tool Class: FileReadTool
# Constructor Parameters: file_path, kwargs
# Description: Read a file's content(file_path: 'string') - A tool that can be used to read a file's content.

# Tool Class: TXTSearchTool
# Constructor Parameters: txt, kwargs
# Description: Search a txt's content(search_query: 'string', txt: 'string') - A tool that can be used to semantic search a query from a txt's content.

# Tool Class: JSONSearchTool
# Constructor Parameters: json_path, kwargs
# Description: Search a JSON's content(search_query: 'string', json_path: 'string') - A tool that can be used to semantic search a query from a JSON's content.

# Tool Class: MDXSearchTool
# Constructor Parameters: mdx, kwargs
# Description: Search a MDX's content(search_query: 'string', mdx: 'string') - A tool that can be used to semantic search a query from a MDX's content.

# Tool Class: PDFSearchTool
# Constructor Parameters: pdf, kwargs
# Description: Search a PDF's content(query: 'string', pdf: 'string') - A tool that can be used to semantic search a query from a PDF's content.

# Tool Class: RagTool
# Constructor Parameters: data
# Description: Knowledge base(query: 'string') - A knowledge base that can be used to answer questions.

# Tool Class: ScrapeElementFromWebsiteTool
# Constructor Parameters: website_url, cookies, css_element, kwargs
# Description: Read a website content() - A tool that can be used to read http://example.com's content.

# Tool Class: ScrapeWebsiteTool
# Constructor Parameters: website_url, cookies, kwargs
# Description: Read website content() - A tool that can be used to read http://example.com's content.

# Tool Class: WebsiteSearchTool
# Constructor Parameters: website, kwargs
# Description: Search in a specific website(search_query: 'string', website: 'string') - A tool that can be used to semantic search a query from a specific URL content.

# Tool Class: XMLSearchTool
# Constructor Parameters: xml, kwargs
# Description: Search a XML's content(search_query: 'string', xml: 'string') - A tool that can be used to semantic search a query from a XML's content.

# Tool Class: YoutubeChannelSearchTool
# Constructor Parameters: youtube_channel_handle, kwargs
# Description: Search a Youtube Channels content(search_query: 'string', youtube_channel_handle: 'string') - A tool that can be used to semantic search a query from a Youtube Channels content.

# Tool Class: YoutubeVideoSearchTool
# Constructor Parameters: youtube_video_url, kwargs
# Description: Search a Youtube Video content(search_query: 'string', youtube_video_url: 'string') - A tool that can be used to semantic search a query from a Youtube Video content.