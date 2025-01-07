"""Tools package for PraisonAI Agents"""
from importlib import import_module
from typing import Any

# Map of function names to their module and class (if any)
TOOL_MAPPINGS = {
    # Direct functions
    'internet_search': ('.duckduckgo_tools', None),
    'duckduckgo': ('.duckduckgo_tools', None),
    
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

    # Calculator Tools
    'evaluate': ('.calculator_tools', 'CalculatorTools'),
    'solve_equation': ('.calculator_tools', 'CalculatorTools'),
    'convert_units': ('.calculator_tools', 'CalculatorTools'),
    'calculate_statistics': ('.calculator_tools', 'CalculatorTools'),
    'calculate_financial': ('.calculator_tools', 'CalculatorTools'),
    'calculator_tools': ('.calculator_tools', 'CalculatorTools'),

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

    # Wikipedia Tools
    'search': ('.wikipedia_tools', 'WikipediaTools'),
    'get_wikipedia_summary': ('.wikipedia_tools', 'WikipediaTools'),
    'get_wikipedia_page': ('.wikipedia_tools', 'WikipediaTools'),
    'get_random_wikipedia': ('.wikipedia_tools', 'WikipediaTools'),
    'set_wikipedia_language': ('.wikipedia_tools', 'WikipediaTools'),
    'wikipedia_tools': ('.wikipedia_tools', 'WikipediaTools'),

    # Newspaper Tools
    'get_article': ('.newspaper_tools', 'NewspaperTools'),
    'get_news_sources': ('.newspaper_tools', 'NewspaperTools'),
    'get_articles_from_source': ('.newspaper_tools', 'NewspaperTools'),
    'get_trending_topics': ('.newspaper_tools', 'NewspaperTools'),
    'newspaper_tools': ('.newspaper_tools', 'NewspaperTools'),

    # arXiv Tools
    'search_arxiv': ('.arxiv_tools', 'ArxivTools'),
    'get_arxiv_paper': ('.arxiv_tools', 'ArxivTools'),
    'get_papers_by_author': ('.arxiv_tools', 'ArxivTools'),
    'get_papers_by_category': ('.arxiv_tools', 'ArxivTools'),
    'arxiv_tools': ('.arxiv_tools', 'ArxivTools'),

    # Spider Tools
    'scrape_page': ('.spider_tools', 'SpiderTools'),
    'extract_links': ('.spider_tools', 'SpiderTools'),
    'crawl': ('.spider_tools', 'SpiderTools'),
    'extract_text': ('.spider_tools', 'SpiderTools'),
    'spider_tools': ('.spider_tools', 'SpiderTools'),

    # DuckDB Tools
    'query': ('.duckdb_tools', 'DuckDBTools'),
    'create_table': ('.duckdb_tools', 'DuckDBTools'),
    'load_data': ('.duckdb_tools', 'DuckDBTools'),
    'export_data': ('.duckdb_tools', 'DuckDBTools'),
    'get_table_info': ('.duckdb_tools', 'DuckDBTools'),
    'analyze_data': ('.duckdb_tools', 'DuckDBTools'),
    'duckdb_tools': ('.duckdb_tools', 'DuckDBTools'),

    # Shell Tools
    'execute_command': ('.shell_tools', 'ShellTools'),
    'list_processes': ('.shell_tools', 'ShellTools'),
    'kill_process': ('.shell_tools', 'ShellTools'),
    'get_system_info': ('.shell_tools', 'ShellTools'),
    'shell_tools': ('.shell_tools', 'ShellTools'),
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
        if name in ['duckduckgo', 'file_tools', 'pandas_tools', 'wikipedia_tools',
                   'newspaper_tools', 'arxiv_tools', 'spider_tools', 'duckdb_tools', 'csv_tools', 'json_tools', 'excel_tools', 'xml_tools', 'yaml_tools', 'calculator_tools', 'python_tools', 'shell_tools']:
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