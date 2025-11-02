"""WSGI entrypoint for production servers."""
from __future__ import annotations

from .app import create_app

# Lazily instantiate the application for gunicorn/uwsgi
app = create_app()

__all__ = ["app"]
