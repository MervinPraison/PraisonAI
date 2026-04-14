"""CLI entry point for PraisonAI Platform server.

Usage:
    python -m praisonai_platform
    python -m praisonai_platform --port 9000 --reload
    python -m praisonai_platform --host 127.0.0.1 --port 8080
"""

import argparse
import sys


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Start the PraisonAI Platform server",
        prog="python -m praisonai_platform"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    
    args = parser.parse_args()
    
    try:
        import uvicorn
        from praisonai_platform.api.app import create_app
        
        uvicorn.run(
            "praisonai_platform.api.app:create_app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            factory=True
        )
    except ImportError as e:
        print(f"Error: Missing required dependency: {e}", file=sys.stderr)
        print("Please install uvicorn: pip install uvicorn", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()