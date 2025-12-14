"""HTTP client for interacting with the Izzylease API."""
from __future__ import annotations

import json
import logging
import uuid
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

    def upload_car_image(self, car_id: str, content: bytes, *, content_type: str, filename: str) -> str:
        """Upload a car image and return its identifier."""

        boundary = uuid.uuid4().hex
        multipart_body = self._build_multipart_body(boundary, content, content_type, filename)

        response = self._request(
            "POST",
            f"/external/cars/{car_id}/images",
            data=multipart_body,
            extra_headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

        try:
            return str(response["imageId"])
        except (KeyError, TypeError) as exc:
            raise RuntimeError("Unexpected response while uploading car image") from exc

    def delete_car_image(self, car_id: str, image_id: str) -> None:
        """Delete a car image from the platform."""

        self._request("DELETE", f"/external/cars/{car_id}/images/{image_id}")

    # -- HTTP helper -------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = f"{self._config.api_base_url}{path}"
        if json_payload is not None and data is not None:
            raise ValueError("Provide either json_payload or data, not both")

        headers = {
            "Authorization": f"Bearer {self._token_provider.get_token()}",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
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

    def _build_multipart_body(
        self, boundary: str, content: bytes, content_type: str, filename: str
    ) -> bytes:
        """Construct a multipart/form-data body for image upload."""

        parts = [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{filename}"'.encode(),
            f"Content-Type: {content_type}".encode(),
            b"",
            content,
            f"--{boundary}--".encode(),
            b"",
        ]
        return b"\r\n".join(parts)
