"""Configuration utilities for the Izzy Uploader service."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


class MissingConfiguration(RuntimeError):
    """Raised when required configuration variables are missing."""


@dataclass(frozen=True)
class ServiceConfig:
    """Configuration container used by orchestrators and clients."""

    api_base_url: str
    api_key: str
    timeout: float = 10.0

    @staticmethod
    def from_env(prefix: str = "IZZYLEASE_") -> "ServiceConfig":
        """Create a :class:`ServiceConfig` instance from environment variables.

        Parameters
        ----------
        prefix:
            Prefix used for environment variables. The defaults expect
            ``IZZYLEASE_API_BASE_URL`` and ``IZZYLEASE_API_KEY`` to be provided.
        """

        base_url = _require_env(f"{prefix}API_BASE_URL")
        api_key = _require_env(f"{prefix}API_KEY")
        timeout_raw: Optional[str] = os.getenv(f"{prefix}TIMEOUT", "10")

        try:
            timeout = float(timeout_raw)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
            raise MissingConfiguration(
                f"Invalid timeout value provided via {prefix}TIMEOUT"
            ) from exc

        return ServiceConfig(api_base_url=base_url, api_key=api_key, timeout=timeout)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingConfiguration(f"Missing required configuration variable: {name}")
    return value
