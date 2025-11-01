"""Authentication helpers for acquiring OAuth access tokens."""
from __future__ import annotations

import json
import ssl
import threading
import time
from typing import Optional
from urllib import error, parse, request

try:  # pragma: no cover - optional dependency
    import certifi
except ImportError:  # pragma: no cover - optional dependency
    certifi = None


class OAuthTokenError(RuntimeError):
    """Raised when fetching an OAuth access token fails."""


class OAuthTokenProvider:
    """Fetches and caches OAuth2 access tokens using the client credentials flow."""

    def __init__(self, token_url: str, client_id: str, client_secret: str, *, timeout: float = 10.0):
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout
        self._lock = threading.Lock()
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._ssl_context = _build_default_ssl_context()

    def get_token(self) -> str:
        """Return a valid access token, refreshing it when necessary."""

        with self._lock:
            if self._access_token and time.time() < self._expires_at:
                return self._access_token
            return self._refresh_token()

    # ------------------------------------------------------------------ #
    def _refresh_token(self) -> str:
        payload = parse.urlencode(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        req = request.Request(self._token_url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(  # type: ignore[arg-type]
                req, timeout=self._timeout, context=self._ssl_context
            ) as resp:
                raw = resp.read()
        except error.URLError as exc:  # pragma: no cover - network failure path
            raise OAuthTokenError(f"Failed to fetch access token: {exc.reason}") from exc

        try:
            data = json.loads(raw.decode("utf-8"))
            token = data["access_token"]
            expires_in = float(data.get("expires_in", 0))
        except (ValueError, KeyError, TypeError) as exc:
            raise OAuthTokenError("Access token response is malformed") from exc

        # Refresh slightly before real expiry to avoid race conditions.
        safety_window = 60.0
        self._access_token = str(token)
        self._expires_at = time.time() + max(0.0, expires_in - safety_window)
        return self._access_token


def _build_default_ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def default_ssl_context() -> ssl.SSLContext:
    """Expose the default SSL context used across the project."""

    return _build_default_ssl_context()
