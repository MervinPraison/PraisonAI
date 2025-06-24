"""Tools package for PraisonAI Agents"""
from importlib import import_module
from typing import Any

# Map of function names to their module and class (if any)
TOOL_MAPPINGS = {
    # Direct functions
    'internet_search': ('.duckduckgo_tools', None),
    'duckduckgo': ('.duckduckgo_tools', None),
    'searxng_search': ('.searxng_tools', None),
    'searxng': ('.searxng_tools', None),
    
    # arXiv Tools
    'search_arxiv': ('.arxiv_tools', None),
    'get_arxiv_paper': ('.arxiv_tools', None),
    'get_papers_by_author': ('.arxiv_tools', None),
    'get_papers_by_category': ('.arxiv_tools', None),
    'arxiv_tools': ('.arxiv_tools', None),
    
    # Wikipedia Tools
    'wiki_search': ('.wikipedia_tools', None),
    'wiki_summary': ('.wikipedia_tools', None),
    'wiki_page': ('.wikipedia_tools', None),
    'wiki_random': ('.wikipedia_tools', None),
    'wiki_language': ('.wikipedia_tools', None),
    'wikipedia_tools': ('.wikipedia_tools', None),
    
    # Newspaper Tools
    'get_article': ('.newspaper_tools', None),
    'get_news_sources': ('.newspaper_tools', None),
    'get_articles_from_source': ('.newspaper_tools', None),
    'get_trending_topics': ('.newspaper_tools', None),
    'newspaper_tools': ('.newspaper_tools', None),
    
    # Spider Tools
    'scrape_page': ('.spider_tools', None),
    'extract_links': ('.spider_tools', None),
    'crawl': ('.spider_tools', None),
    'extract_text': ('.spider_tools', None),
    'spider_tools': ('.spider_tools', None),
    
    # DuckDB Tools
    'query': ('.duckdb_tools', None),
    'create_table': ('.duckdb_tools', None),
    'load_data': ('.duckdb_tools', None),
    'export_data': ('.duckdb_tools', None),
    'get_table_info': ('.duckdb_tools', None),
    'analyze_data': ('.duckdb_tools', None),
    'duckdb_tools': ('.duckdb_tools', None),
    
    # Shell Tools
    'execute_command': ('.shell_tools', None),
    'list_processes': ('.shell_tools', None),
    'kill_process': ('.shell_tools', None),
    'get_system_info': ('.shell_tools', None),
    'shell_tools': ('.shell_tools', None),

    # Calculator Tools
    'evaluate': ('.calculator_tools', None),
    'solve_equation': ('.calculator_tools', None),
    'convert_units': ('.calculator_tools', None),
    'calculate_statistics': ('.calculator_tools', None),
    'calculate_financial': ('.calculator_tools', None),
    'calculator_tools': ('.calculator_tools', None),

    # Class methods from YFinance
    'get_stock_price': ('.yfinance_tools', 'YFinanceTools'),
    'get_stock_info': ('.yfinance_tools', 'YFinanceTools'),
    'get_historical_data': ('.yfinance_tools', 'YFinanceTools'),
    'yfinance': ('.yfinance_tools', 'YFinanceTools'),

    # File Tools
    'read_file': ('.file_tools', 'FileTools'),
    'write_file': ('.file_tools', 'FileTools'),
    'list_files': ('.file_tools', 'FileTools'),
    'get_file_info': ('.file_tools', 'FileTools'),
    'copy_file': ('.file_tools', 'FileTools'),
    'move_file': ('.file_tools', 'FileTools'),
    'delete_file': ('.file_tools', 'FileTools'),
    'file_tools': ('.file_tools', 'FileTools'),

    # CSV Tools
    'read_csv': ('.csv_tools', 'CSVTools'),
    'write_csv': ('.csv_tools', 'CSVTools'),
    'merge_csv': ('.csv_tools', 'CSVTools'),
    'analyze_csv': ('.csv_tools', 'CSVTools'),
    'split_csv': ('.csv_tools', 'CSVTools'),
    'csv_tools': ('.csv_tools', 'CSVTools'),

    # JSON Tools
    'read_json': ('.json_tools', 'JSONTools'),
    'write_json': ('.json_tools', 'JSONTools'),
    'merge_json': ('.json_tools', 'JSONTools'),
    'validate_json': ('.json_tools', 'JSONTools'),
    'analyze_json': ('.json_tools', 'JSONTools'),
    'transform_json': ('.json_tools', 'JSONTools'),
    'json_tools': ('.json_tools', 'JSONTools'),

    # Excel Tools
    'read_excel': ('.excel_tools', 'ExcelTools'),
    'write_excel': ('.excel_tools', 'ExcelTools'),
    'merge_excel': ('.excel_tools', 'ExcelTools'),
    'create_chart': ('.excel_tools', 'ExcelTools'),
    'add_chart_to_sheet': ('.excel_tools', 'ExcelTools'),
    'excel_tools': ('.excel_tools', 'ExcelTools'),

    # XML Tools
    'read_xml': ('.xml_tools', 'XMLTools'),
    'write_xml': ('.xml_tools', 'XMLTools'),
    'transform_xml': ('.xml_tools', 'XMLTools'),
    'validate_xml': ('.xml_tools', 'XMLTools'),
    'xml_to_dict': ('.xml_tools', 'XMLTools'),
    'dict_to_xml': ('.xml_tools', 'XMLTools'),
    'xpath_query': ('.xml_tools', 'XMLTools'),
    'xml_tools': ('.xml_tools', 'XMLTools'),

    # YAML Tools
    'read_yaml': ('.yaml_tools', 'YAMLTools'),
    'write_yaml': ('.yaml_tools', 'YAMLTools'),
    'merge_yaml': ('.yaml_tools', 'YAMLTools'),
    'validate_yaml': ('.yaml_tools', 'YAMLTools'),
    'analyze_yaml': ('.yaml_tools', 'YAMLTools'),
    'transform_yaml': ('.yaml_tools', 'YAMLTools'),
    'yaml_tools': ('.yaml_tools', 'YAMLTools'),

    # Python Tools
    'execute_code': ('.python_tools', 'PythonTools'),
    'analyze_code': ('.python_tools', 'PythonTools'),
    'format_code': ('.python_tools', 'PythonTools'),
    'lint_code': ('.python_tools', 'PythonTools'),
    'disassemble_code': ('.python_tools', 'PythonTools'),
    'python_tools': ('.python_tools', 'PythonTools'),

    # Pandas Tools
    'filter_data': ('.pandas_tools', 'PandasTools'),
    'get_summary': ('.pandas_tools', 'PandasTools'),
    'group_by': ('.pandas_tools', 'PandasTools'),
    'pivot_table': ('.pandas_tools', 'PandasTools'),
    'pandas_tools': ('.pandas_tools', 'PandasTools'),

    # Chain of Thought Training Tools
    'cot_run': ('.train.data.generatecot', 'GenerateCOT'),           # Orchestrates text solution
    'cot_run_dict': ('.train.data.generatecot', 'GenerateCOT'),      # Orchestrates dict-based solution
    'cot_generate': ('.train.data.generatecot', 'GenerateCOT'),      # Generate text solution
    'cot_generate_dict': ('.train.data.generatecot', 'GenerateCOT'), # Generate structured solution
    'cot_improve': ('.train.data.generatecot', 'GenerateCOT'),       # Improve text solution
    'cot_improve_dict': ('.train.data.generatecot', 'GenerateCOT'),  # Improve dict-based solution
    'cot_check': ('.train.data.generatecot', 'GenerateCOT'),         # Check correctness
    'cot_find_error': ('.train.data.generatecot', 'GenerateCOT'),    # Locate error in solution
    'cot_load_answers': ('.train.data.generatecot', 'GenerateCOT'),  # Load QA pairs
    
    # COT Save/Export with QA Pairs
    'cot_save_solutions_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),    # Save with QA pairs
    'cot_append_solutions_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),  # Append with QA pairs
    'cot_export_json_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),       # Export JSON with QA pairs
    'cot_export_csv_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),        # Export CSV with QA pairs
    'cot_append_csv_with_qa_pairs': ('.train.data.generatecot', 'GenerateCOT'),        # Append CSV with QA pairs
    'cot_save': ('.train.data.generatecot', 'GenerateCOT'),                           # Save single QA to file
    'cot_upload_to_huggingface': ('.train.data.generatecot', 'GenerateCOT'),           # Upload dataset to HuggingFace
    'cot_tools': ('.train.data.generatecot', 'GenerateCOT'),                           # Full toolkit access
}

_instances = {}  # Cache for class instances

def __getattr__(name: str) -> Any:
    """Smart lazy loading of tools with class method support."""
    if name not in TOOL_MAPPINGS:
        raise AttributeError(f"module '{__package__}' has no attribute '{name}'")
    
    module_path, class_name = TOOL_MAPPINGS[name]
    
    if class_name is None:
        # Direct function import
        module = import_module(module_path, __package__)
        if name in [
            'duckduckgo', 'internet_search', 'searxng_search', 'searxng',
            'search_arxiv', 'get_arxiv_paper', 'get_papers_by_author', 'get_papers_by_category',
            'wiki_search', 'wiki_summary', 'wiki_page', 'wiki_random', 'wiki_language',
            'get_article', 'get_news_sources', 'get_articles_from_source', 'get_trending_topics',
            'scrape_page', 'extract_links', 'crawl', 'extract_text',
            'query', 'create_table', 'load_data', 'export_data', 'get_table_info', 'analyze_data',
            'execute_command', 'list_processes', 'kill_process', 'get_system_info',
            'evaluate', 'solve_equation', 'convert_units', 'calculate_statistics', 'calculate_financial'
        ]:
            return getattr(module, name)
        if name in ['file_tools', 'pandas_tools', 'wikipedia_tools',
                   'newspaper_tools', 'arxiv_tools', 'spider_tools', 'duckdb_tools', 'csv_tools', 'json_tools', 'excel_tools', 'xml_tools', 'yaml_tools', 'calculator_tools', 'python_tools', 'shell_tools', 'cot_tools']:
            return module  # Returns the callable module
        return getattr(module, name)
    else:
        # Class method import
        if class_name not in _instances:
            module = import_module(module_path, __package__)
            class_ = getattr(module, class_name)
            _instances[class_name] = class_()
        
        # Get the method and bind it to the instance
        method = getattr(_instances[class_name], name)
        return method

__all__ = list(TOOL_MAPPINGS.keys())