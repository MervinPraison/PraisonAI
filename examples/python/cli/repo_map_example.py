"""
Repository Map Example for PraisonAI CLI.

Intelligent codebase mapping with symbol extraction.
Docs: https://docs.praison.ai/cli/repo-map
"""

from praisonai.cli.features import RepoMapHandler

# Initialize with current directory
handler = RepoMapHandler(verbose=True)
repo_map = handler.initialize(root=".")

# Get the repository map
print("=== Repository Map ===")
map_str = handler.get_map()
print(map_str[:500] if len(map_str) > 500 else map_str)
print("..." if len(map_str) > 500 else "")

# Refresh after file changes
handler.refresh()

# Get symbols for a specific file (if exists)
# symbols = handler.get_context("MyClass")
