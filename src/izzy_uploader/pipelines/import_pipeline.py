"""Pipeline orchestrator responsible for synchronising vehicles with Izzylease."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

from ..client import IzzyleaseClient
from ..models import Vehicle, unique_vins
from ..state import VehicleStateStore

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


class VehicleSynchronizer:
    """Coordinates vehicle synchronisation with the remote API."""

    def __init__(self, client: IzzyleaseClient, state_store: VehicleStateStore):
        self._client = client
        self._state_store = state_store

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
            self._record_error(report, None, None, str(exc))
            return report

        for vehicle in desired.values():
            self._upsert_vehicle(vehicle, report)

        if close_missing:
            self._close_missing_vehicles(set(desired), report)

        try:
            self._state_store.save()
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to persist vehicle state")
            self._record_error(
                report,
                None,
                None,
                f"Failed to persist synchronisation state: {exc}",
            )

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
                return
            except Exception as exc:  # pylint: disable=broad-except
                if _is_not_found_error(exc):
                    LOGGER.info(
                        "Remote vehicle %s missing; attempting to recreate it", car_label
                    )
                    self._recreate_vehicle(vehicle, vin_label, report)
                    return
                LOGGER.exception("Failed to update vehicle %s", car_label)
                self._record_error(report, vin_label, state_car_id, f"update failed: {exc}")
                return

        # No known car id – create fresh record.
        self._recreate_vehicle(vehicle, vin_label, report)

    def _recreate_vehicle(self, vehicle: Vehicle, vin_label: str, report: PipelineReport) -> None:
        car_label = vehicle.configuration_number or vin_label
        try:
            created_id = self._client.create_vehicle(vehicle)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to create vehicle %s", car_label)
            self._record_error(report, vin_label, None, f"creation failed: {exc}")
            return

        self._state_store.upsert(vin_label, created_id, vehicle.configuration_number)
        report.created += 1
        report.created_vehicles.append({"vin": vin_label, "car_id": created_id})
        self._state_store.mark_active(vin_label)

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
                self._record_error(report, vin, car_id, f"deletion failed: {exc}")

    def _record_error(
        self,
        report: PipelineReport,
        vin: Optional[str],
        car_id: Optional[str],
        message: str,
    ) -> None:
        report.errors.append(message)
        report.error_details.append(
            {
                "vin": vin,
                "car_id": car_id,
                "error_message": message,
            }
        )


def _is_not_found_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "status 404" in text or ("404" in text and "not found" in text)
