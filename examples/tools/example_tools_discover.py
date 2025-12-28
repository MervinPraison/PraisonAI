"""Example: Discover tools from installed packages."""

# Discover from praisonaiagents built-in tools
try:
    from praisonaiagents.tools import TOOL_MAPPINGS
    print("Built-in tools from praisonaiagents:")
    for name in list(TOOL_MAPPINGS.keys())[:10]:
        print(f"  - {name}")
    print(f"  ... and {len(TOOL_MAPPINGS) - 10} more")
except ImportError:
    print("praisonaiagents not installed")

# Discover from praisonai_tools
try:
    import praisonai_tools
    print("\nTools from praisonai_tools:")
    
    # Check for video module
    try:
        from praisonai_tools import video
        print("  - praisonai_tools.video (video editing)")
    except ImportError:
        pass
except ImportError:
    print("praisonai_tools not installed")
