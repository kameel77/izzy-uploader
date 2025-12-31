"""Pipeline orchestrator responsible for synchronising vehicles with Izzylease."""
from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set
from urllib.error import URLError

from ..client import IzzyleaseClient
from ..models import Vehicle, unique_vins
from ..state import ImageStateStore, VehicleStateStore

LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineReport:
    """Detailed report returned after synchronisation."""

    created: int = 0
    updated: int = 0
    price_updates: int = 0  # kept for CLI compatibility, always zero in new flow
    closed: int = 0
    errors: List[str] = field(default_factory=list)
    error_details: List[dict] = field(default_factory=list)
    created_vehicles: List[dict] = field(default_factory=list)
    updated_vehicles: List[dict] = field(default_factory=list)
    deleted_vehicles: List[dict] = field(default_factory=list)

    def as_dict(self, *, include_details: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "created": self.created,
            "updated": self.updated,
            "price_updates": self.price_updates,
            "closed": self.closed,
            "errors": len(self.errors),
        }
        if include_details:
            payload["detail"] = {
                "created": self.created_vehicles,
                "updated": self.updated_vehicles,
                "deleted": self.deleted_vehicles,
                "errors": self.error_details,
            }
        return payload

    def record_error(
        self,
        message: str,
        vin: Optional[str] = None,
        car_id: Optional[str] = None,
    ) -> None:
        self.errors.append(message)
        self.error_details.append(
            {
                "vin": vin,
                "car_id": car_id,
                "error_message": message,
            }
        )


class VehicleSynchronizer:
    """Coordinates vehicle synchronisation with the remote API."""

    def __init__(self, client: IzzyleaseClient, state_store: VehicleStateStore, image_state_store: Optional[ImageStateStore] = None):
        self._client = client
        self._state_store = state_store
        self._image_state_store = image_state_store

    def run(
        self,
        vehicles: Iterable[Vehicle],
        *,
        close_missing: bool = False,
        update_prices: bool = False,  # retained for backward compatibility
    ) -> PipelineReport:
        report = PipelineReport()

        try:
            desired = unique_vins(vehicles)
        except ValueError as exc:
            report.record_error(str(exc))
            return report

        for vehicle in desired.values():
            self._upsert_vehicle(vehicle, report)

        if close_missing:
            self._close_missing_vehicles(set(desired), report)

        try:
            self._state_store.save()
            if self._image_state_store:
                self._image_state_store.save()
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to persist vehicle state")
            report.record_error(f"Failed to persist synchronisation state: {exc}")

        return report

    # -- helpers ---------------------------------------------------------
    def _upsert_vehicle(self, vehicle: Vehicle, report: PipelineReport) -> None:
        vin_label = vehicle.vin
        state_car_id = self._state_store.get_car_id(vin_label)
        car_label = vehicle.configuration_number or vin_label

        if state_car_id:
            try:
                self._client.update_vehicle(state_car_id, vehicle)
                report.updated += 1
                report.updated_vehicles.append({"vin": vin_label, "car_id": state_car_id})
                self._state_store.mark_active(vin_label)

                # Upload images if available and not already uploaded
                if self._image_state_store and (vehicle.featured_photo or vehicle.other_photos):
                    self._ensure_vehicle_images_uploaded(state_car_id, vehicle, report)

                return
            except Exception as exc:  # pylint: disable=broad-except
                if _is_not_found_error(exc):
                    LOGGER.info(
                        "Remote vehicle %s missing; attempting to recreate it", car_label
                    )
                    self._recreate_vehicle(vehicle, vin_label, report)
                    return
                LOGGER.exception("Failed to update vehicle %s", car_label)
                report.record_error(f"update failed: {exc}", vin=vin_label, car_id=state_car_id)
                return

        # No known car id – create fresh record.
        self._recreate_vehicle(vehicle, vin_label, report)

    def _recreate_vehicle(self, vehicle: Vehicle, vin_label: str, report: PipelineReport) -> None:
        car_label = vehicle.configuration_number or vin_label
        try:
            created_id = self._client.create_vehicle(vehicle)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to create vehicle %s", car_label)
            report.record_error(f"creation failed: {exc}", vin=vin_label)
            return

        self._state_store.upsert(vin_label, created_id, vehicle.configuration_number)
        report.created += 1
        report.created_vehicles.append({"vin": vin_label, "car_id": created_id})
        self._state_store.mark_active(vin_label)

        # Upload images if available
        if self._image_state_store and (vehicle.featured_photo or vehicle.other_photos):
            self._upload_vehicle_images(created_id, vehicle, report)

    def _ensure_vehicle_images_uploaded(self, car_id: str, vehicle: Vehicle, report: PipelineReport) -> None:
        """Ensure all vehicle images are uploaded, avoiding duplicates."""
        if not self._image_state_store:
            return

        # Check if we have any images to upload
        if not vehicle.featured_photo and not vehicle.other_photos:
            return

        # Get currently uploaded images for this vehicle
        uploaded_images = set(self._image_state_store.get_images(car_id))

        # Collect all image URLs that should be uploaded
        expected_urls = []
        if vehicle.featured_photo:
            expected_urls.append(vehicle.featured_photo)
        expected_urls.extend(vehicle.other_photos)

        # Upload any missing images
        for url in expected_urls:
            # For now, we'll upload all images since we don't track URL-to-ID mapping
            # In a production system, you'd want to track which URLs have been uploaded
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    image_data = response.read()
                    content_type = response.headers.get('Content-Type', 'image/jpeg')
                    filename = url.split('/')[-1] or 'image.jpg'

                image_id = self._client.upload_car_image(car_id, image_data, content_type=content_type, filename=filename)
                if image_id not in uploaded_images:
                    self._image_state_store.add_image(car_id, image_id)
                    LOGGER.info("Uploaded new image %s for existing vehicle %s", url, car_id)
                else:
                    LOGGER.debug("Image %s already uploaded for vehicle %s", url, car_id)
            except (URLError, Exception) as exc:
                LOGGER.exception("Failed to upload image %s for existing vehicle %s", url, car_id)
                report.record_error(f"image upload failed for {url}: {exc}", vin=vehicle.vin, car_id=car_id)

    def _upload_vehicle_images(self, car_id: str, vehicle: Vehicle, report: PipelineReport) -> None:
        """Download and upload images for a vehicle."""
        assert self._image_state_store is not None

        # Collect all image URLs
        image_urls = []
        if vehicle.featured_photo:
            image_urls.append(vehicle.featured_photo)
        image_urls.extend(vehicle.other_photos)

        for url in image_urls:
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    image_data = response.read()
                    content_type = response.headers.get('Content-Type', 'image/jpeg')
                    filename = url.split('/')[-1] or 'image.jpg'

                image_id = self._client.upload_car_image(car_id, image_data, content_type=content_type, filename=filename)
                self._image_state_store.add_image(car_id, image_id)
                LOGGER.info("Uploaded image %s for vehicle %s", url, car_id)
            except (URLError, Exception) as exc:
                LOGGER.exception("Failed to upload image %s for vehicle %s", url, car_id)
                report.record_error(f"image upload failed for {url}: {exc}", vin=vehicle.vin, car_id=car_id)

    def _close_missing_vehicles(self, desired_vins: Set[str], report: PipelineReport) -> None:
        known_vins = set(self._state_store.known_vins())
        for vin in known_vins - desired_vins:
            car_id = self._state_store.get_car_id(vin)
            if not car_id:
                continue
            try:
                self._client.delete_vehicle(car_id)
                self._state_store.mark_deleted(vin)
                report.closed += 1
                report.deleted_vehicles.append({"vin": vin, "car_id": car_id})
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Failed to delete vehicle with VIN %s", vin)
                report.record_error(f"deletion failed: {exc}", vin=vin, car_id=car_id)


def _is_not_found_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "status 404" in text or ("404" in text and "not found" in text)
