"""
Basic TUI Usage Example for PraisonAI.

This example demonstrates how to launch the interactive TUI.
"""

import os

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)


def main():
    """Launch the TUI."""
    try:
        from praisonai.cli.features.tui import run_tui
        
        # Launch with default settings
        run_tui()
        
    except ImportError:
        print("Textual is required for TUI. Install with:")
        print("  pip install praisonai[tui]")
        exit(1)


if __name__ == "__main__":
    main()
