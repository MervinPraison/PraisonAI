"""
Example 5: File and Symbol Indexing

This example demonstrates the file and symbol indexing capabilities
that power Fast Context's rapid search.

Features:
- FileIndexer: Index file metadata for fast lookups
- SymbolIndexer: Extract code symbols (functions, classes, imports)
- Support for Python, JavaScript, TypeScript, Go, Rust, Java
"""

import time
from praisonaiagents.context.fast.indexer import (
    FileIndexer,
    SymbolIndexer,
    SymbolType
)

WORKSPACE = "/Users/praison/praisonai-package/src/praisonai-agents"


def main():
    print("=" * 70)
    print("File and Symbol Indexing")
    print("=" * 70)
    
    # File Indexer
    print("\n1. File Indexer")
    print("-" * 40)
    
    start = time.perf_counter()
    file_indexer = FileIndexer(workspace_path=WORKSPACE)
    file_count = file_indexer.index()
    file_time = (time.perf_counter() - start) * 1000
    
    print(f"   Indexed {file_count} files in {file_time:.0f}ms")
    
    stats = file_indexer.get_stats()
    print(f"   Total size: {stats['total_size_mb']} MB")
    print(f"   Extensions: {list(stats['extensions'].keys())[:5]}")
    
    # Find files by pattern
    print("\n   Finding files by pattern:")
    py_files = file_indexer.find_by_pattern("**/*.py")
    print(f"   - Python files (*.py): {len(py_files)}")
    
    agent_files = file_indexer.find_by_pattern("**/agent*.py")
    print(f"   - Agent files (agent*.py): {len(agent_files)}")
    
    # Find files by name
    print("\n   Finding files by name:")
    init_files = file_indexer.find_by_name("__init__.py", exact=True)
    print(f"   - __init__.py files: {len(init_files)}")
    
    agent_matches = file_indexer.find_by_name("agent")
    print(f"   - Files containing 'agent': {len(agent_matches)}")
    
    # Symbol Indexer
    print("\n2. Symbol Indexer")
    print("-" * 40)
    
    start = time.perf_counter()
    symbol_indexer = SymbolIndexer(workspace_path=WORKSPACE)
    symbol_count = symbol_indexer.index()
    symbol_time = (time.perf_counter() - start) * 1000
    
    print(f"   Indexed {symbol_count} symbols in {symbol_time:.0f}ms")
    
    stats = symbol_indexer.get_stats()
    print(f"   Files indexed: {stats['total_files']}")
    print(f"   Symbols by type:")
    for sym_type, count in stats['by_type'].items():
        print(f"      - {sym_type}: {count}")
    
    # Find symbols by name
    print("\n   Finding symbols by name:")
    
    agent_symbols = symbol_indexer.find_by_name("Agent", exact=True)
    print(f"   - 'Agent' (exact): {len(agent_symbols)} symbols")
    for sym in agent_symbols[:3]:
        print(f"      {sym.symbol_type.value}: {sym.name} in {sym.file_path}:{sym.line_number}")
    
    chat_symbols = symbol_indexer.find_by_name("chat")
    print(f"   - 'chat' (partial): {len(chat_symbols)} symbols")
    for sym in chat_symbols[:3]:
        print(f"      {sym.symbol_type.value}: {sym.name} in {sym.file_path}:{sym.line_number}")
    
    # Find symbols by type
    print("\n   Finding symbols by type:")
    
    classes = symbol_indexer.find_by_type(SymbolType.CLASS)
    print(f"   - Classes: {len(classes)}")
    for cls in classes[:5]:
        print(f"      class {cls.name} in {cls.file_path}:{cls.line_number}")
    
    functions = symbol_indexer.find_by_type(SymbolType.FUNCTION)
    print(f"   - Functions: {len(functions)}")
    
    methods = symbol_indexer.find_by_type(SymbolType.METHOD)
    print(f"   - Methods: {len(methods)}")
    
    imports = symbol_indexer.find_by_type(SymbolType.IMPORT)
    print(f"   - Imports: {len(imports)}")
    
    # Performance comparison
    print("\n3. Performance Summary")
    print("-" * 40)
    
    print(f"   File indexing: {file_time:.0f}ms for {file_count} files")
    print(f"   Symbol indexing: {symbol_time:.0f}ms for {symbol_count} symbols")
    print(f"   Files per second: {file_count / (file_time / 1000):.0f}")
    print(f"   Symbols per second: {symbol_count / (symbol_time / 1000):.0f}")
    
    print("\n" + "=" * 70)
    print("Indexing enables instant lookups for files and symbols!")
    print("=" * 70)


if __name__ == "__main__":
    main()
