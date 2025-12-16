"""
Example 7: Search Tools Deep Dive

This example demonstrates the individual search tools that power Fast Context:
- grep_search: Pattern-based search with regex support
- glob_search: File pattern matching
- read_file: Read file contents with line ranges
- list_directory: Directory listing with filtering
"""

import time
from praisonaiagents.context.fast.search_tools import (
    grep_search,
    glob_search,
    read_file,
    list_directory
)

WORKSPACE = "/Users/praison/praisonai-package/src/praisonai-agents"


def main():
    print("=" * 70)
    print("Search Tools Deep Dive")
    print("=" * 70)
    
    # grep_search
    print("\n1. grep_search - Pattern Search")
    print("-" * 40)
    
    # Simple pattern
    start = time.perf_counter()
    results = grep_search(
        search_path=WORKSPACE,
        pattern="def __init__",
        max_results=10
    )
    elapsed = (time.perf_counter() - start) * 1000
    
    print(f"   Pattern: 'def __init__'")
    print(f"   Matches: {len(results)}")
    print(f"   Time: {elapsed:.0f}ms")
    if results:
        print(f"   First match: {results[0]['path']}:{results[0]['line_number']}")
    
    # Regex pattern
    results = grep_search(
        search_path=WORKSPACE,
        pattern=r"class \w+Agent",
        is_regex=True,
        max_results=10
    )
    print(f"\n   Regex: 'class \\w+Agent'")
    print(f"   Matches: {len(results)}")
    for r in results[:3]:
        print(f"   - {r['path']}:{r['line_number']}: {r['content'][:50]}...")
    
    # Case sensitive
    results_sensitive = grep_search(
        search_path=WORKSPACE,
        pattern="Agent",
        case_sensitive=True,
        max_results=50
    )
    results_insensitive = grep_search(
        search_path=WORKSPACE,
        pattern="agent",
        case_sensitive=False,
        max_results=50
    )
    print(f"\n   Case sensitive 'Agent': {len(results_sensitive)} matches")
    print(f"   Case insensitive 'agent': {len(results_insensitive)} matches")
    
    # With context lines
    results = grep_search(
        search_path=WORKSPACE,
        pattern="class Agent:",
        context_lines=2,
        max_results=3
    )
    print(f"\n   With 2 context lines:")
    if results:
        print(f"   {results[0]['path']}:")
        if results[0].get('context'):
            for line in results[0]['context'].split('\n')[:5]:
                print(f"      {line[:60]}")
    
    # glob_search
    print("\n2. glob_search - File Pattern Matching")
    print("-" * 40)
    
    # Find Python files
    start = time.perf_counter()
    results = glob_search(
        search_path=WORKSPACE,
        pattern="**/*.py",
        max_results=100
    )
    elapsed = (time.perf_counter() - start) * 1000
    
    print(f"   Pattern: '**/*.py'")
    print(f"   Files found: {len(results)}")
    print(f"   Time: {elapsed:.0f}ms")
    
    # Find specific files
    results = glob_search(
        search_path=WORKSPACE,
        pattern="**/agent*.py",
        max_results=20
    )
    print(f"\n   Pattern: '**/agent*.py'")
    print(f"   Files found: {len(results)}")
    for r in results[:5]:
        print(f"   - {r['path']} ({r['size']} bytes)")
    
    # Find test files
    results = glob_search(
        search_path=WORKSPACE,
        pattern="**/test_*.py",
        max_results=50
    )
    print(f"\n   Pattern: '**/test_*.py'")
    print(f"   Test files: {len(results)}")
    
    # read_file
    print("\n3. read_file - Read File Contents")
    print("-" * 40)
    
    # Read entire file
    result = read_file(
        filepath=f"{WORKSPACE}/praisonaiagents/__init__.py",
        max_lines=20
    )
    
    print(f"   File: praisonaiagents/__init__.py")
    print(f"   Success: {result['success']}")
    print(f"   Lines: {result.get('total_lines', 'N/A')}")
    if result['success']:
        lines = result['content'].split('\n')[:5]
        print(f"   Preview:")
        for line in lines:
            print(f"      {line[:60]}")
    
    # Read specific line range
    result = read_file(
        filepath=f"{WORKSPACE}/praisonaiagents/agent/agent.py",
        start_line=1,
        end_line=20
    )
    
    print(f"\n   File: agent/agent.py (lines 1-20)")
    print(f"   Success: {result['success']}")
    if result['success']:
        lines = result['content'].split('\n')[:5]
        print(f"   Preview:")
        for line in lines:
            print(f"      {line[:60]}")
    
    # Read with context
    result = read_file(
        filepath=f"{WORKSPACE}/praisonaiagents/agent/agent.py",
        start_line=100,
        end_line=105,
        context_lines=3
    )
    
    print(f"\n   File: agent/agent.py (lines 100-105 with 3 context lines)")
    print(f"   Success: {result['success']}")
    
    # list_directory
    print("\n4. list_directory - Directory Listing")
    print("-" * 40)
    
    # List root
    result = list_directory(
        dir_path=WORKSPACE,
        recursive=False,
        max_entries=20
    )
    
    print(f"   Directory: {WORKSPACE}")
    print(f"   Success: {result['success']}")
    print(f"   Entries: {len(result.get('entries', []))}")
    
    dirs = [e for e in result.get('entries', []) if e.get('is_dir')]
    files = [e for e in result.get('entries', []) if not e.get('is_dir')]
    print(f"   Directories: {len(dirs)}")
    print(f"   Files: {len(files)}")
    
    # List recursive with depth limit
    result = list_directory(
        dir_path=f"{WORKSPACE}/praisonaiagents",
        recursive=True,
        max_depth=2,
        max_entries=50
    )
    
    print(f"\n   Directory: praisonaiagents (recursive, depth=2)")
    print(f"   Entries: {len(result.get('entries', []))}")
    
    # Show directory structure
    print(f"   Structure:")
    for entry in result.get('entries', [])[:10]:
        prefix = "📁" if entry.get('is_dir') else "📄"
        print(f"      {prefix} {entry['name']}")
    
    print("\n" + "=" * 70)
    print("These search tools power Fast Context's rapid code search!")
    print("=" * 70)


if __name__ == "__main__":
    main()
