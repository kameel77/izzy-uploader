"""Domain models used by the Izzy Uploader service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, Optional


@dataclass
class Vehicle:
    """Represents a vehicle listed in the CSV file and/or on Izzylease."""

    external_id: str
    vin: str
    make: str
    model: str
    manufacture_year: int
    mileage: Optional[int]
    fuel_type: Optional[str]
    power: Optional[int]
    transmission_type: Optional[str]
    drive_wheels: Optional[str]
    vehicle_type: Optional[str]
    car_class: Optional[str]
    doors: Optional[int]
    color: Optional[str]
    available_from: Optional[date]
    first_registration_date: Optional[date]
    description: Optional[str]
    list_price: Optional[float]
    sales_price: Optional[float]
    mini_price: Optional[float]
    location_id: Optional[str]

    def to_api_payload(self) -> Dict[str, Any]:
        """Serialize the vehicle into a payload accepted by the API client."""

        return {
            "externalId": self.external_id,
            "vin": self.vin,
            "make": self.make,
            "model": self.model,
            "manufactureYear": self.manufacture_year,
            "mileage": self.mileage,
            "fuelType": self.fuel_type,
            "power": self.power,
            "transmissionType": self.transmission_type,
            "driveWheels": self.drive_wheels,
            "type": self.vehicle_type,
            "carClass": self.car_class,
            "doors": self.doors,
            "color": self.color,
            "availableFrom": _serialize_date(self.available_from),
            "firstRegistrationDate": _serialize_date(self.first_registration_date),
            "description": self.description,
            "pricing": {
                "listPrice": self.list_price,
                "salesPrice": self.sales_price,
                "miniPrice": self.mini_price,
            },
            "locationId": self.location_id,
        }

    def requires_price_discount_flag(self, current_price: Optional[float]) -> bool:
        """Determine whether the vehicle price decreased compared to the current API state."""

        if self.sales_price is None or current_price is None:
            return False
        return self.sales_price < current_price


def _serialize_date(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid integer value: {value}") from exc


def parse_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid float value: {value}") from exc


def parse_date(value: Optional[str]) -> Optional[date]:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date value: {value}") from exc


def vehicle_from_row(row: Dict[str, str]) -> Vehicle:
    """Create a :class:`Vehicle` instance from a CSV row."""

    required = {
        "configurationNumber": row.get("configurationNumber"),
        "vin": row.get("vin"),
        "make": row.get("make"),
        "model": row.get("model"),
        "manufactureYear": row.get("manufactureYear"),
    }

    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing required CSV fields: {', '.join(missing)}")

    return Vehicle(
        external_id=required["configurationNumber"],
        vin=required["vin"],
        make=required["make"],
        model=required["model"],
        manufacture_year=int(required["manufactureYear"]),
        mileage=parse_int(row.get("mileage")),
        fuel_type=row.get("fuelType"),
        power=parse_int(row.get("power")),
        transmission_type=row.get("transmissionType"),
        drive_wheels=row.get("driveWheels"),
        vehicle_type=row.get("type"),
        car_class=row.get("carClass"),
        doors=parse_int(row.get("doors")),
        color=row.get("color"),
        available_from=parse_date(row.get("availableFrom")),
        first_registration_date=parse_date(row.get("firstRegistrationDate")),
        description=row.get("description"),
        list_price=parse_float(row.get("pricing_listPrice")),
        sales_price=parse_float(row.get("pricing_salesPrice")),
        mini_price=parse_float(row.get("pricing_miniPrice")),
        location_id=row.get("locationId"),
    )


def unique_external_ids(vehicles: Iterable[Vehicle]) -> Dict[str, Vehicle]:
    """Return a dictionary of vehicles keyed by their external identifier."""

    result: Dict[str, Vehicle] = {}
    for vehicle in vehicles:
        if vehicle.external_id in result:
            raise ValueError(
                f"Duplicate vehicle external id detected: {vehicle.external_id}"
            )
        result[vehicle.external_id] = vehicle
    return result
