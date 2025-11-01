"""Domain models used by the Izzy Uploader service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, Iterable, Optional


class CarRemovalReason(Enum):
    """Reasons understood by the API when removing a vehicle."""

    DELETED = "DELETED"
    SOLD = "SOLD"


@dataclass
class Vehicle:
    """Represents a vehicle listed in the CSV file and/or on Izzylease."""

    vin: str
    category: str
    make: str
    model: str
    manufacture_year: int
    mileage: int
    engine_code: Optional[str]
    cubic_capacity: float
    acceleration: Optional[float]
    fuel_type: str
    power: int
    transmission_type: str
    drive_wheels: str
    vehicle_type: str
    doors: Optional[int]
    color: str
    list_price: Decimal
    sales_price: Decimal
    configuration_number: Optional[str] = None
    car_class: Optional[str] = None
    available_from: Optional[date] = None
    first_registration_date: Optional[date] = None
    description: Optional[str] = None
    registration_number: Optional[str] = None
    location_id: Optional[str] = None
    car_id: Optional[str] = None

    def to_api_payload(self) -> Dict[str, Any]:
        """Serialise the vehicle to the payload expected by the dealer API."""

        payload: Dict[str, Any] = {
            "configurationNumber": self.configuration_number,
            "vin": self.vin,
            "category": self.category,
            "make": self.make,
            "model": self.model,
            "manufactureYear": self.manufacture_year,
            "mileage": self.mileage,
            "engineCode": self.engine_code,
            "cubicCapacity": self.cubic_capacity,
            "acceleration": self.acceleration,
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
                "listPrice": _format_money(self.list_price),
                "salesPrice": _format_money(self.sales_price),
            },
            "registrationNumber": self.registration_number,
            "locationId": self.location_id,
        }

        # Drop keys with ``None`` values to keep the payload leaner.
        return {key: value for key, value in payload.items() if value is not None}


def vehicle_from_row(row: Dict[str, str]) -> Vehicle:
    """Create a :class:`Vehicle` instance from a CSV row."""

    missing: list[str] = []

    def require(key: str) -> str:
        value = row.get(key)
        if value is None or value == "":
            missing.append(key)
            return ""
        return value

    vin = require("vin")
    category = _normalise_enum(require("category"))
    make = require("make")
    model = require("model")
    manufacture_year = _parse_int(require("manufactureYear"), "manufactureYear")
    mileage = _parse_int(require("mileage"), "mileage")
    engine_code = row.get("engineCode") or None
    cubic_capacity = _parse_float(require("cubicCapacity"), "cubicCapacity")
    raw_acceleration = row.get("acceleration") or ""
    acceleration = _parse_float(raw_acceleration, "acceleration") if raw_acceleration else 0.0
    fuel_type = _normalise_enum(require("fuelType"))
    power = _parse_int(require("power"), "power")
    transmission_type = _normalise_enum(require("transmissionType"))
    drive_wheels = _normalise_drive_wheels(require("driveWheels"))
    vehicle_type = _normalise_enum(require("type"))
    raw_doors = row.get("doors") or ""
    doors = _parse_int(raw_doors, "doors") if raw_doors else None
    if doors == 0:
        doors = None
    color = require("color")
    list_price = _parse_decimal(require("pricing_listPrice"), "pricing_listPrice")
    sales_price = _parse_decimal(require("pricing_salesPrice"), "pricing_salesPrice")

    if missing:
        raise ValueError(f"Missing required CSV fields: {', '.join(sorted(set(missing)))}")

    return Vehicle(
        configuration_number=row.get("configurationNumber") or None,
        vin=vin,
        category=category,
        make=make,
        model=model,
        manufacture_year=manufacture_year,
        mileage=mileage,
        engine_code=engine_code,
        cubic_capacity=cubic_capacity,
        acceleration=acceleration,
        fuel_type=fuel_type,
        power=power,
        transmission_type=transmission_type,
        drive_wheels=drive_wheels,
        vehicle_type=vehicle_type,
        car_class=_normalise_optional_enum(row.get("carClass")),
        doors=doors,
        color=color,
        available_from=_parse_date(row.get("availableFrom")),
        first_registration_date=_parse_date(row.get("firstRegistrationDate")),
        description=row.get("description") or None,
        list_price=list_price,
        sales_price=sales_price,
        registration_number=row.get("registrationNumber") or None,
        location_id=row.get("locationId") or None,
    )


def unique_vins(vehicles: Iterable[Vehicle]) -> Dict[str, Vehicle]:
    """Return a VIN-keyed dictionary, ensuring no duplicates are present."""

    unique: Dict[str, Vehicle] = {}
    for vehicle in vehicles:
        if vehicle.vin in unique:
            raise ValueError(f"Duplicate vehicle VIN detected: {vehicle.vin}")
        unique[vehicle.vin] = vehicle
    return unique


def _serialize_date(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _parse_int(value: str, field: str) -> int:
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid integer value for '{field}': {value}") from exc
    return int(decimal_value.to_integral_value(rounding=ROUND_HALF_UP))


def _parse_float(value: str, field: str) -> float:
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for '{field}': {value}") from exc
    return float(decimal_value)


def _parse_decimal(value: str, field: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid monetary value for '{field}': {value}") from exc
    return amount


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date value: {value}") from exc


def _format_money(amount: Decimal) -> str:
    # Normalise the representation to avoid exponential notation in JSON.
    quantised = amount.normalize()
    return format(quantised, "f")


def _normalise_enum(value: str) -> str:
    return value.strip().upper()


def _normalise_optional_enum(value: Optional[str]) -> Optional[str]:
    if value is None or value.strip() == "":
        return None
    return _normalise_enum(value)


def _normalise_drive_wheels(value: str) -> str:
    cleaned = value.strip().lower()
    mapping = {
        "4x4": "FOUR",
        "4wd": "FOUR",
        "awd": "FOUR",
        "four": "FOUR",
        "front": "FRONT",
        "fwd": "FRONT",
        "rear": "REAR",
        "rwd": "REAR",
        "back": "REAR",
    }
    if cleaned in mapping:
        return mapping[cleaned]
    return _normalise_enum(value)
