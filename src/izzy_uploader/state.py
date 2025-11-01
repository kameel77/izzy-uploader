"""Persistence helpers for tracking remote vehicle identifiers."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class VehicleStateEntry:
    vin: str
    car_id: str
    configuration_number: Optional[str] = None
    active: bool = True


class VehicleStateStore:
    """Stores mapping between VINs and remote car identifiers."""

    def __init__(self, path: Path):
        self._path = path
        self._entries: Dict[str, VehicleStateEntry] = {}
        self._load()

    # -- public API -------------------------------------------------
    def get_car_id(self, vin: str) -> Optional[str]:
        entry = self._entries.get(vin)
        return entry.car_id if entry else None

    def upsert(self, vin: str, car_id: str, configuration_number: Optional[str]) -> None:
        entry = self._entries.get(vin)
        if entry:
            entry.car_id = car_id
            entry.configuration_number = configuration_number
            entry.active = True
        else:
            self._entries[vin] = VehicleStateEntry(
                vin=vin,
                car_id=car_id,
                configuration_number=configuration_number,
                active=True,
            )

    def mark_deleted(self, vin: str) -> None:
        entry = self._entries.get(vin)
        if entry:
            entry.active = False

    def mark_active(self, vin: str) -> None:
        entry = self._entries.get(vin)
        if entry:
            entry.active = True

    def known_vins(self) -> Iterable[str]:
        return (vin for vin, entry in self._entries.items() if entry.active)

    def save(self) -> None:
        payload = {
            "vehicles": {
                vin: {
                    "car_id": entry.car_id,
                    "configuration_number": entry.configuration_number,
                    "active": entry.active,
                }
                for vin, entry in self._entries.items()
            }
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- internals --------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return

        try:
            raw = self._path.read_text(encoding="utf-8") or "{}"
            data = json.loads(raw)
            vehicles = data.get("vehicles", {})
            if isinstance(vehicles, dict):
                for vin, payload in vehicles.items():
                    if not isinstance(payload, dict):
                        continue
                    car_id = payload.get("car_id")
                    if not isinstance(car_id, str):
                        continue
                    configuration_number = payload.get("configuration_number")
                    if configuration_number is not None and not isinstance(configuration_number, str):
                        configuration_number = None
                    active_raw = payload.get("active")
                    active = active_raw if isinstance(active_raw, bool) else True
                    self._entries[vin] = VehicleStateEntry(
                        vin=vin,
                        car_id=car_id,
                        configuration_number=configuration_number,
                        active=active,
                    )
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Ignoring invalid state file %s: %s", self._path, exc)
            self._entries = {}
