"""HTTP client for interacting with the Izzylease API."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional
from urllib import error, request

from .config import ServiceConfig
from .models import Vehicle

LOGGER = logging.getLogger(__name__)


class IzzyleaseClient:
    """Wrapper around the Izzylease API."""

    def __init__(self, config: ServiceConfig):
        self._config = config

    # -- API helpers -----------------------------------------------------
    def list_vehicles(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/vehicles")

    def create_vehicle(self, vehicle: Vehicle) -> Dict[str, Any]:
        LOGGER.debug("Creating vehicle %s", vehicle.external_id)
        return self._request("POST", "/vehicles", json_payload=vehicle.to_api_payload())

    def update_vehicle(self, vehicle: Vehicle) -> Dict[str, Any]:
        LOGGER.debug("Updating vehicle %s", vehicle.external_id)
        return self._request(
            "PUT",
            f"/vehicles/{vehicle.external_id}",
            json_payload=vehicle.to_api_payload(),
        )

    def close_vehicle(self, external_id: str) -> Dict[str, Any]:
        LOGGER.debug("Closing vehicle %s", external_id)
        return self._request("POST", f"/vehicles/{external_id}/close")

    def update_price(
        self, external_id: str, price: float, notify_discount: bool
    ) -> Dict[str, Any]:
        LOGGER.debug(
            "Updating price for vehicle %s (price=%s, discount=%s)",
            external_id,
            price,
            notify_discount,
        )
        return self._request(
            "POST",
            f"/vehicles/{external_id}/price",
            json_payload={"price": price, "notifyDiscount": notify_discount},
        )

    # -- Utility helpers -------------------------------------------------
    def build_vehicle_lookup(self) -> Dict[str, Dict[str, Any]]:
        """Return a lookup table by external id for active vehicles."""

        return {item["externalId"]: item for item in self.list_vehicles()}

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
            "Authorization": f"Bearer {self._config.api_key}",
            "Accept": "application/json",
        }
        if json_payload is not None:
            data = json.dumps(json_payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        LOGGER.debug("Request %s %s payload=%s", method, url, json_payload)
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self._config.timeout) as resp:  # type: ignore[arg-type]
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


class VehicleRepositoryProtocol:
    """Protocol implemented by repositories that provide vehicle data."""

    def list(self) -> Iterable[Vehicle]:  # pragma: no cover - interface definition
        raise NotImplementedError
