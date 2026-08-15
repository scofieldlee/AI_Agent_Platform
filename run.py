#!/usr/bin/env python
"""
Development server launcher.

Usage:
    python run.py              # Start dev server on port 8000
    python run.py --port 9000  # Custom port
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="AI Agent Platform - Dev Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--reload", action="store_true", default=True, help="Auto-reload on file changes")
    args = parser.parse_args()

    # Use the project venv's uvicorn
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
