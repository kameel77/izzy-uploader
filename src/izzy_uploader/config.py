"""Configuration utilities for the Izzy Uploader service."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


class MissingConfiguration(RuntimeError):
    """Raised when required configuration variables are missing."""


@dataclass(frozen=True)
class ServiceConfig:
    """Configuration container used by orchestrators and clients."""

    api_base_url: str
    token_url: str
    client_id: str
    client_secret: str
    dealer_id: Optional[str]
    state_file: Path
    timeout: float = 10.0

    @staticmethod
    def from_env(prefix: str = "IZZYLEASE_") -> "ServiceConfig":
        """Create a :class:`ServiceConfig` instance from environment variables.

        Parameters
        ----------
        prefix:
            Prefix used for environment variables. The defaults expect
            ``IZZYLEASE_API_BASE_URL``, ``IZZYLEASE_CLIENT_ID`` i
            ``IZZYLEASE_CLIENT_SECRET``.
        """

        base_url = _require_env(f"{prefix}API_BASE_URL")
        client_id = _require_env(f"{prefix}CLIENT_ID")
        client_secret = _require_env(f"{prefix}CLIENT_SECRET")
        token_url = os.getenv(f"{prefix}TOKEN_URL") or f"{base_url.rstrip('/')}/oauth/token"
        dealer_id = os.getenv(f"{prefix}DEALER_ID") or None
        state_file_env = os.getenv(f"{prefix}STATE_FILE")
        if state_file_env:
            state_file = Path(state_file_env).expanduser().resolve()
        else:
            state_file = Path.home() / ".izzy_uploader" / "state.json"
        timeout_raw: Optional[str] = os.getenv(f"{prefix}TIMEOUT", "10")

        try:
            timeout = float(timeout_raw)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
            raise MissingConfiguration(
                f"Invalid timeout value provided via {prefix}TIMEOUT"
            ) from exc

        return ServiceConfig(
            api_base_url=base_url.rstrip("/"),
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            dealer_id=dealer_id,
            state_file=state_file,
            timeout=timeout,
        )


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingConfiguration(f"Missing required configuration variable: {name}")
    return value
