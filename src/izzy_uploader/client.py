"""HTTP client for interacting with the Izzylease API."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from urllib import error, request

from .auth import OAuthTokenProvider, default_ssl_context
from .config import ServiceConfig
from .models import CarRemovalReason, Vehicle

LOGGER = logging.getLogger(__name__)


class IzzyleaseClient:
    """Wrapper around the Izzylease dealer API."""

    def __init__(self, config: ServiceConfig, token_provider: Optional[OAuthTokenProvider] = None):
        self._config = config
        self._token_provider = token_provider or OAuthTokenProvider(
            config.token_url,
            config.client_id,
            config.client_secret,
            timeout=config.timeout,
        )
        self._ssl_context = default_ssl_context()

    # -- API helpers -------------------------------------------------
    def create_vehicle(self, vehicle: Vehicle) -> str:
        """Create a vehicle and return the created car identifier."""

        LOGGER.debug("Creating vehicle %s", vehicle.configuration_number or vehicle.vin)
        payload = vehicle.to_api_payload()
        response = self._request("POST", "/external/cars", json_payload=payload)
        try:
            return str(response["id"])
        except (KeyError, TypeError) as exc:
            raise RuntimeError("Unexpected response while creating vehicle") from exc

    def update_vehicle(self, car_id: str, vehicle: Vehicle) -> None:
        """Update an existing vehicle."""

        LOGGER.debug("Updating vehicle %s", car_id)
        self._request(
            "PUT",
            f"/external/cars/{car_id}",
            json_payload=vehicle.to_api_payload(),
        )

    def delete_vehicle(self, car_id: str, reason: CarRemovalReason = CarRemovalReason.DELETED) -> None:
        """Remove a vehicle from the platform."""

        LOGGER.debug("Deleting vehicle %s with reason %s", car_id, reason.value)
        body: Dict[str, Any] = {"reason": reason.value}
        self._request("DELETE", f"/external/cars/{car_id}", json_payload=body)

    # -- HTTP helper -------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self._config.api_base_url}{path}"
        data: Optional[bytes] = None
        headers = {
            "Authorization": f"Bearer {self._token_provider.get_token()}",
            "Accept": "application/json",
        }
        if json_payload is not None:
            data = json.dumps(json_payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        LOGGER.debug("Request %s %s payload=%s", method, url, json_payload)
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(  # type: ignore[arg-type]
                req, timeout=self._config.timeout, context=self._ssl_context
            ) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network failure path
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"API request failed with status {exc.code}: {body or exc.reason}"
            ) from exc
        except error.URLError as exc:  # pragma: no cover - network failure path
            raise RuntimeError(f"API request failed: {exc.reason}") from exc
