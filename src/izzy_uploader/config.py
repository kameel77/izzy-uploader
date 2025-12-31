"""Configuration utilities for the Izzy Uploader service."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Dict


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
    image_state_file: Path
    timeout: float = 10.0

    @staticmethod
    def from_env(prefix: str = "IZZYLEASE_", overrides: Optional[Dict[str, str]] = None) -> "ServiceConfig":
        """Create a :class:`ServiceConfig` instance from environment variables.

        Parameters
        ----------
        prefix:
            Prefix used for environment variables. The defaults expect
            ``IZZYLEASE_API_BASE_URL``, ``IZZYLEASE_CLIENT_ID`` i
            ``IZZYLEASE_CLIENT_SECRET``.
        overrides:
            Optional dict with keys like ``API_BASE_URL``, ``CLIENT_ID``, ``CLIENT_SECRET``,
            ``TOKEN_URL``, ``DEALER_ID`` to override env values (used by web UI/API).
        """

        def _read(name: str, required: bool = False) -> str:
            if overrides and name in overrides and overrides[name]:
                return overrides[name]
            if required:
                return _require_env(f"{prefix}{name}")
            return os.getenv(f"{prefix}{name}", "")

        base_url = _read("API_BASE_URL", required=True)
        client_id = _read("CLIENT_ID", required=True)
        client_secret = _read("CLIENT_SECRET", required=True)
        token_url_override = _read("TOKEN_URL")
        token_url = token_url_override or f"{base_url.rstrip('/')}/oauth/token"
        dealer_id_raw = _read("DEALER_ID")
        dealer_id = dealer_id_raw or None
        state_file_env = os.getenv(f"{prefix}STATE_FILE")
        if state_file_env:
            state_file = Path(state_file_env).expanduser().resolve()
        else:
            state_file = Path.home() / ".izzy_uploader" / "state.json"
        image_state_file_env = os.getenv(f"{prefix}IMAGE_STATE_FILE")
        if image_state_file_env:
            image_state_file = Path(image_state_file_env).expanduser().resolve()
        else:
            image_state_file = Path.home() / ".izzy_uploader" / "image_state.json"
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
            image_state_file=image_state_file,
            timeout=timeout,
        )


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingConfiguration(f"Missing required configuration variable: {name}")
    return value
