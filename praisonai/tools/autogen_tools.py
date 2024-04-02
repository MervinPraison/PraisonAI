from crewai_tools import (
    CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool, DirectoryReadTool,
    FileReadTool, TXTSearchTool, JSONSearchTool, MDXSearchTool, PDFSearchTool, RagTool,
    ScrapeElementFromWebsiteTool, ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool, YoutubeChannelSearchTool,
    YoutubeVideoSearchTool
)
from typing import Any
from autogen import register_function

# CodeDocsSearchTool
def autogen_CodeDocsSearchTool(assistant, user_proxy):
    def register_code_docs_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(docs_url: str) -> Any:
            tool_instance = tool_class(docs_url=docs_url)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_code_docs_search_tool(CodeDocsSearchTool, "code_docs_search_tool", "Search documentation in code.", assistant, user_proxy)

# CSVSearchTool
def autogen_CSVSearchTool(assistant, user_proxy):
    def register_csv_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(csv: str) -> Any:
            tool_instance = tool_class(csv=csv)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_csv_search_tool(CSVSearchTool, "csv_search_tool", "Search inside CSV files.", assistant, user_proxy)

# DirectorySearchTool
def autogen_DirectorySearchTool(assistant, user_proxy):
    def register_directory_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(directory: str) -> Any:
            tool_instance = tool_class(directory=directory)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_directory_search_tool(DirectorySearchTool, "directory_search_tool", "Search inside directories.", assistant, user_proxy)

# DOCXSearchTool
def autogen_DOCXSearchTool(assistant, user_proxy):
    def register_docx_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(docx: str) -> Any:
            tool_instance = tool_class(docx=docx)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_docx_search_tool(DOCXSearchTool, "docx_search_tool", "Search inside DOCX files.", assistant, user_proxy)

# DirectoryReadTool
def autogen_DirectoryReadTool(assistant, user_proxy):
    def register_directory_read_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(directory: str) -> Any:
            tool_instance = tool_class(directory=directory)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_directory_read_tool(DirectoryReadTool, "directory_read_tool", "Read contents of a directory.", assistant, user_proxy)

# FileReadTool
def autogen_FileReadTool(assistant, user_proxy):
    def register_file_read_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(file_path: str) -> Any:
            tool_instance = tool_class(file_path=file_path)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_file_read_tool(FileReadTool, "file_read_tool", "Read from a file.", assistant, user_proxy)

# TXTSearchTool
def autogen_TXTSearchTool(assistant, user_proxy):
    def register_txt_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(txt: str) -> Any:
            tool_instance = tool_class(txt=txt)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_txt_search_tool(TXTSearchTool, "txt_search_tool", "Search inside TXT files.", assistant, user_proxy)

# JSONSearchTool
def autogen_JSONSearchTool(assistant, user_proxy):
    def register_json_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(json_path: str) -> Any:
            tool_instance = tool_class(json_path=json_path)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_json_search_tool(JSONSearchTool, "json_search_tool", "Search inside JSON files.", assistant, user_proxy)

# MDXSearchTool
def autogen_MDXSearchTool(assistant, user_proxy):
    def register_mdx_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(mdx: str) -> Any:
            tool_instance = tool_class(mdx=mdx)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_mdx_search_tool(MDXSearchTool, "mdx_search_tool", "Search inside MDX files.", assistant, user_proxy)

# PDFSearchTool
def autogen_PDFSearchTool(assistant, user_proxy):
    def register_pdf_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(pdf: str) -> Any:
            tool_instance = tool_class(pdf=pdf)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_pdf_search_tool(PDFSearchTool, "pdf_search_tool", "Search inside PDF files.", assistant, user_proxy)

# RagTool
def autogen_RagTool(assistant, user_proxy):
    def register_rag_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(data: Any) -> Any:
            tool_instance = tool_class(data=data)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_rag_tool(RagTool, "rag_tool", "A knowledge base tool.", assistant, user_proxy)

# ScrapeElementFromWebsiteTool
def autogen_ScrapeElementFromWebsiteTool(assistant, user_proxy):
    def register_scrape_element_from_website_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(website_url: str) -> Any:
            tool_instance = tool_class(website_url=website_url)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_scrape_element_from_website_tool(ScrapeElementFromWebsiteTool, "scrape_element_from_website_tool", "Scrape elements from a website.", assistant, user_proxy)

# ScrapeWebsiteTool 
def autogen_ScrapeWebsiteTool(assistant, user_proxy):
    def register_scrape_website_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(website_url: str) -> Any:
            tool_instance = tool_class(website_url=website_url)
            return tool_instance.run()

        register_function(
            tool_func,
            caller=assistant,  # The assistant agent can suggest calls to the tool.
            executor=user_proxy,  # The user proxy agent can execute the tool calls.
            name=tool_name,  # By default, the function name is used as the tool name.
            description=tool_description,  # A description of the tool.
        )
    register_scrape_website_tool(ScrapeWebsiteTool, "scrape_website_tool", "A tool for scraping specific websites", assistant, user_proxy)

# WebsiteSearchTool
def autogen_WebsiteSearchTool(assistant, user_proxy):
    def register_website_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(website: str) -> Any:
            tool_instance = tool_class(website=website)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_website_search_tool(WebsiteSearchTool, "website_search_tool", "Search a website.", assistant, user_proxy)

# XMLSearchTool
def autogen_XMLSearchTool(assistant, user_proxy):
    def register_xml_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(xml: str) -> Any:
            tool_instance = tool_class(xml=xml)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_xml_search_tool(XMLSearchTool, "xml_search_tool", "Search inside XML files.", assistant, user_proxy)

# YoutubeChannelSearchTool
def autogen_YoutubeChannelSearchTool(assistant, user_proxy):
    def register_youtube_channel_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(youtube_channel_handle: str) -> Any:
            tool_instance = tool_class(youtube_channel_handle=youtube_channel_handle)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_youtube_channel_search_tool(YoutubeChannelSearchTool, "youtube_channel_search_tool", "Search a YouTube channel.", assistant, user_proxy)

# YoutubeVideoSearchTool
def autogen_YoutubeVideoSearchTool(assistant, user_proxy):
    def register_youtube_video_search_tool(tool_class, tool_name, tool_description, assistant, user_proxy):
        def tool_func(youtube_video_url: str) -> Any:
            tool_instance = tool_class(youtube_video_url=youtube_video_url)
            return tool_instance.run()
        register_function(tool_func, caller=assistant, executor=user_proxy, name=tool_name, description=tool_description)
    register_youtube_video_search_tool(YoutubeVideoSearchTool, "youtube_video_search_tool", "Search a YouTube video.", assistant, user_proxy)
