"""Pipeline orchestrator responsible for synchronising vehicles with Izzylease."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from ..client import IzzyleaseClient
from ..models import Vehicle, unique_external_ids

LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineReport:
    """Detailed report returned after synchronisation."""

    created: int = 0
    updated: int = 0
    price_updates: int = 0
    closed: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, int]:
        return {
            "created": self.created,
            "updated": self.updated,
            "price_updates": self.price_updates,
            "closed": self.closed,
            "errors": len(self.errors),
        }


class VehicleSynchronizer:
    """Coordinates vehicle synchronisation with the remote API."""

    def __init__(self, client: IzzyleaseClient):
        self._client = client

    def run(
        self,
        vehicles: Iterable[Vehicle],
        *,
        close_missing: bool = False,
        update_prices: bool = False,
    ) -> PipelineReport:
        report = PipelineReport()
        try:
            vehicle_lookup = self._client.build_vehicle_lookup()
        except Exception as exc:  # pylint: disable=broad-except
            report.errors.append(f"Failed to fetch remote vehicles: {exc}")
            return report

        desired = unique_external_ids(vehicles)
        existing_ids: Set[str] = set(vehicle_lookup)

        for vehicle in desired.values():
            if vehicle.external_id in existing_ids:
                self._handle_existing_vehicle(vehicle, vehicle_lookup, report, update_prices)
            else:
                self._handle_new_vehicle(vehicle, report)

        if close_missing:
            to_close = existing_ids - set(desired)
            for external_id in to_close:
                self._close_vehicle(external_id, report)

        return report

    # -- helpers ---------------------------------------------------------
    def _handle_existing_vehicle(
        self,
        vehicle: Vehicle,
        vehicle_lookup: Dict[str, Dict[str, object]],
        report: PipelineReport,
        update_prices: bool,
    ) -> None:
        try:
            self._client.update_vehicle(vehicle)
            report.updated += 1
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to update vehicle %s", vehicle.external_id)
            report.errors.append(f"{vehicle.external_id}: update failed: {exc}")
            return

        if not update_prices:
            return

        current = vehicle_lookup.get(vehicle.external_id, {})
        current_price = _extract_price(current)
        if vehicle.sales_price is None:
            return

        notify_discount = vehicle.requires_price_discount_flag(current_price)
        if current_price is not None and current_price == vehicle.sales_price and not notify_discount:
            return

        try:
            self._client.update_price(
                vehicle.external_id, vehicle.sales_price, notify_discount
            )
            report.price_updates += 1
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to update price for %s", vehicle.external_id)
            report.errors.append(f"{vehicle.external_id}: price update failed: {exc}")

    def _handle_new_vehicle(self, vehicle: Vehicle, report: PipelineReport) -> None:
        try:
            self._client.create_vehicle(vehicle)
            report.created += 1
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to create vehicle %s", vehicle.external_id)
            report.errors.append(f"{vehicle.external_id}: creation failed: {exc}")

    def _close_vehicle(self, external_id: str, report: PipelineReport) -> None:
        try:
            self._client.close_vehicle(external_id)
            report.closed += 1
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to close vehicle %s", external_id)
            report.errors.append(f"{external_id}: close failed: {exc}")


def _extract_price(vehicle_payload: Dict[str, object]) -> Optional[float]:
    pricing = vehicle_payload.get("pricing") if isinstance(vehicle_payload, dict) else None
    if isinstance(pricing, dict):
        value = pricing.get("salesPrice")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):  # pragma: no cover - defensive guard
            LOGGER.warning("Unexpected price value for payload %s", vehicle_payload)
            return None
    return None
