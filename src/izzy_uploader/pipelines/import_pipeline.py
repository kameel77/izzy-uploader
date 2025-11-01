"""Pipeline orchestrator responsible for synchronising vehicles with Izzylease."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Set

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

    def as_dict(self) -> dict[str, int]:
        return {
            "created": self.created,
            "updated": self.updated,
            "price_updates": self.price_updates,
            "closed": self.closed,
            "errors": len(self.errors),
        }


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
            report.errors.append(str(exc))
            return report

        for vehicle in desired.values():
            self._upsert_vehicle(vehicle, report)

        if close_missing:
            self._close_missing_vehicles(set(desired), report)

        try:
            self._state_store.save()
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to persist vehicle state")
            report.errors.append(f"Failed to persist synchronisation state: {exc}")

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
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Failed to update vehicle %s", car_label)
                report.errors.append(f"{car_label}: update failed: {exc}")
        else:
            try:
                created_id = self._client.create_vehicle(vehicle)
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Failed to create vehicle %s", car_label)
                report.errors.append(f"{car_label}: creation failed: {exc}")
                return

            self._state_store.upsert(vin_label, created_id, vehicle.configuration_number)
            report.created += 1

    def _close_missing_vehicles(self, desired_vins: Set[str], report: PipelineReport) -> None:
        known_vins = set(self._state_store.known_vins())
        for vin in known_vins - desired_vins:
            car_id = self._state_store.get_car_id(vin)
            if not car_id:
                continue
            try:
                self._client.delete_vehicle(car_id)
                self._state_store.remove(vin)
                report.closed += 1
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Failed to delete vehicle with VIN %s", vin)
                report.errors.append(f"{vin}: deletion failed: {exc}")
