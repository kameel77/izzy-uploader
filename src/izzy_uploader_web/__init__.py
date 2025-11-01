"""Web application entry point for the Izzy Uploader."""
from __future__ import annotations

from .app import create_app

__all__ = ["create_app"]


def main() -> None:
    """Run development server when executed as a module."""

    app = create_app()
    app.run(debug=True)


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    main()

