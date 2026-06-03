"""Run the PraisonAI Platform server.

Usage::

    python -m praisonai_platform
    python -m praisonai_platform --host 0.0.0.0 --port 8080
"""

import argparse
import os
import sys


def main() -> None:
    default_host = os.environ.get("PLATFORM_HOST", "127.0.0.1")
    parser = argparse.ArgumentParser(description="PraisonAI Platform Server")
    parser.add_argument(
        "--host",
        default=default_host,
        help="Bind host (default: 127.0.0.1, or PLATFORM_HOST env)",
    )
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required to run the platform server. Install with: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    uvicorn.run(
        "praisonai_platform.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
