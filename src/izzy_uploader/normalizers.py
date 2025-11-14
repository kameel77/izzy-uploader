"""Utilities for cleaning and normalising raw CSV data before validation."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Optional

CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"
DEFAULT_LOCATION_MAP_PATH = CONFIG_ROOT / "location_map.json"
LOCATION_MAP_ENV = "IZZYLEASE_LOCATION_MAP_FILE"
DEFAULT_ENGINE_CODE = "-"


def clean_row(row: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of *row* with partner-specific quirks normalised."""

    cleaned: Dict[str, str] = {key: _prepare_value(value) for key, value in row.items()}

    cleaned["category"] = _map_enum(cleaned.get("category"), CATEGORY_MAP)
    cleaned["fuelType"] = _map_enum(cleaned.get("fuelType"), FUEL_MAP)
    cleaned["transmissionType"] = _map_enum(cleaned.get("transmissionType"), TRANSMISSION_MAP)
    cleaned["driveWheels"] = _map_enum(cleaned.get("driveWheels"), DRIVE_WHEELS_MAP)
    cleaned["type"] = _map_enum(cleaned.get("type"), VEHICLE_TYPE_MAP)
    cleaned["segment"] = _normalise_segment(cleaned.get("segment"))
    cleaned["carClass"] = _map_enum(
        cleaned.get("carClass"), CAR_CLASS_MAP, default_upper=False, allow_empty=True
    )

    if not cleaned["carClass"]:
        cleaned["carClass"] = _infer_car_class(cleaned)

    if cleaned.get("engineCode") == "":
        cleaned["engineCode"] = DEFAULT_ENGINE_CODE

    cleaned["manufactureYear"] = _normalise_integer(cleaned.get("manufactureYear"))
    cleaned["mileage"] = _normalise_integer(cleaned.get("mileage"))
    cleaned["power"] = _normalise_integer(cleaned.get("power"))
    cleaned["doors"] = _normalise_integer(cleaned.get("doors"), allow_zero=True)

    cleaned["cubicCapacity"] = _normalise_decimal(cleaned.get("cubicCapacity"))
    cleaned["acceleration"] = _normalise_decimal(cleaned.get("acceleration"))
    cleaned["pricing_listPrice"] = _normalise_decimal(cleaned.get("pricing_listPrice"))
    cleaned["pricing_salesPrice"] = _normalise_decimal(cleaned.get("pricing_salesPrice"))
    cleaned["pricing_miniPrice"] = _normalise_decimal(cleaned.get("pricing_miniPrice"))

    cleaned["availableFrom"] = _normalise_date(cleaned.get("availableFrom"))
    cleaned["firstRegistrationDate"] = _normalise_date(cleaned.get("firstRegistrationDate"))

    # Descriptions frequently contain the literal "NULL" – treat it as missing.
    if cleaned.get("description") == "":
        cleaned["description"] = ""
    elif cleaned.get("description"):
        cleaned["description"] = _normalise_description(cleaned["description"])

    cleaned["locationId"] = _map_location(cleaned.get("locationId"))

    return cleaned


def _prepare_value(value: Optional[str]) -> str:
    if value is None:
        return ""
    result = value.strip()
    if result.upper() == "NULL":
        return ""
    return result


def _normalise_integer(raw: str, *, allow_zero: bool = False) -> str:
    if not raw:
        return "" if not allow_zero else "0"
    value = _prepare_numeric(raw)
    if value is None:
        return "" if not allow_zero else "0"
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError):
        return "" if not allow_zero else "0"
    if not allow_zero and decimal_value == 0:
        return ""
    return str(int(decimal_value.to_integral_value(rounding=ROUND_HALF_UP)))


def _normalise_decimal(raw: str) -> str:
    if not raw:
        return ""
    value = _prepare_numeric(raw)
    if value is None:
        return ""
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError):
        return ""
    normalised = decimal_value.normalize()
    return format(normalised, "f")


def _prepare_numeric(raw: str) -> Optional[str]:
    if raw is None:
        return None
    value = raw.replace(" ", "").replace(",", ".")
    return value if value else None


def _normalise_date(raw: str) -> str:
    if not raw:
        return ""
    # Accept YYYY-MM-DD or timestamp with time component.
    parts = raw.split(" ")
    return parts[0]


def _map_enum(
    value: Optional[str],
    mapping: Dict[str, str],
    *,
    default_upper: bool = True,
    allow_empty: bool = False,
) -> str:
    if not value:
        return "" if allow_empty else ""

    if mapping is TRANSMISSION_MAP and value:
        raw_upper = value.upper()
        if "DSG" in raw_upper or "DCT" in raw_upper:
            return "AUTOMATIC"
    if mapping is DRIVE_WHEELS_MAP and value:
        raw_upper = value.upper()
        if "4X4" in raw_upper:
            return "FOUR"

    key = _normalise_key(value)
    mapped = mapping.get(key)
    if mapped:
        return mapped
    return value.strip().upper() if default_upper else ""


def _map_location(value: Optional[str]) -> str:
    if not value:
        return ""
    mapping = _load_location_map()
    partner_id = value.strip()
    return mapping.get(partner_id, "")


def _load_location_map() -> Dict[str, str]:
    if not hasattr(_load_location_map, "_cache"):
        mapping_path = get_location_map_path()
        if mapping_path.exists():
            try:
                with mapping_path.open("r", encoding="utf-8") as handle:
                    _load_location_map._cache = json.load(handle)
            except (OSError, json.JSONDecodeError):
                _load_location_map._cache = {}
        else:
            _load_location_map._cache = {}
    return dict(getattr(_load_location_map, "_cache"))


def _normalise_key(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def _normalise_description(value: str) -> str:
    parts = [part.strip() for part in re.split(r"\s*\|\s*", value) if part.strip()]
    if not parts:
        return value.strip()
    deduplicated = []
    seen = set()
    for item in parts:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)
    return "\n".join(deduplicated)


def get_location_map_path() -> Path:
    """Return the path to the partner → location mapping file."""

    configured = os.getenv(LOCATION_MAP_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_LOCATION_MAP_PATH


def load_location_map() -> Dict[str, str]:
    """Return a copy of the location mapping."""

    return _load_location_map()


def save_location_map(mapping: Dict[str, str]) -> None:
    """Persist *mapping* to disk under the configured location map path."""

    path = get_location_map_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    refresh_location_map()


def refresh_location_map() -> None:
    """Clear cached mapping so future lookups reload the file."""

    if hasattr(_load_location_map, "_cache"):
        delattr(_load_location_map, "_cache")


def _normalise_segment(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.strip().upper()


def _infer_car_class(cleaned: Dict[str, str]) -> str:
    """Infer car class based on core vehicle parameters."""

    power = _safe_int(cleaned.get("power"))
    cubic_capacity = _safe_int(cleaned.get("cubicCapacity"))
    doors = _safe_int(cleaned.get("doors"))
    vehicle_type = (cleaned.get("type") or "").upper()
    segment = (cleaned.get("segment") or "").upper()

    if (
        power >= 250
        or cubic_capacity >= 3000
        or (vehicle_type == "COUPE" and power >= 200)
        or (vehicle_type in {"CABRIOLET", "KABRIOLET"} and power >= 180)
    ):
        return "ADRENALINE"

    if doors >= 4 and vehicle_type in {"ESTATE", "SUV", "MINIVAN"} and power < 250:
        return "FAMILY"

    if (
        vehicle_type in {"SALOON", "SEDAN"}
        and doors == 4
        and segment in {"D", "E"}
        and power < 250
    ):
        return "BUSINESS"

    return "SWEET"


def _safe_int(value: Optional[str]) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


CATEGORY_MAP = {
    "osobowy": "PASSENGER",
    "dostawczy": "DELIVERY",
}

FUEL_MAP = {
    "etylina": "PETROL",
    "benzyna": "PETROL",
    "olejnapedowy": "DIESEL",
    "diesel": "DIESEL",
    "hybrydaetylnanapedelektryczny": "HYBRID",
    "hybrydaetylinanapedelektr": "HYBRID",
    "hybrydapluginelektric": "HYBRID",
    "hybrydaetylnaplusnapedelektryczny": "HYBRID",
    "hybrydowy": "HYBRID",
    "lpg": "LPG",
    "elektryczny": "ELECTRIC",
}

TRANSMISSION_MAP = {
    "automatycznahydraulicznaklasyczna": "AUTOMATIC",
    "automatyczna": "AUTOMATIC",
    "automatycznadwusprzegowadctdsg": "AUTOMATIC",
    "manualna": "MANUAL",
    "automat": "AUTOMATIC",
}

DRIVE_WHEELS_MAP = {
    "naprzedniekola": "FRONT",
    "naprzedniekoa": "FRONT",
    "naprzod": "FRONT",
    "naautonomiczneprzod": "FRONT",
    "natylniekola": "REAR",
    "4x4": "FOUR",
    "4x4staly": "FOUR",
    "4x4stay": "FOUR",
    "4x4automatyczny": "FOUR",
    "4wd": "FOUR",
}

VEHICLE_TYPE_MAP = {
    "suv": "SUV",
    "kombi": "ESTATE",
    "minivan": "MINIVAN",
    "coupe": "COUPE",
    "kabriolet": "CABRIOLET",
    "hatchback": "HATCHBACK",
    "van": "VAN",
    "sedan": "SALOON",
    "limuzyna": "SALOON",
    "autamiejskie": "HATCHBACK",
    "kompakt": "HATCHBACK",
}

CAR_CLASS_MAP = {
    "business": "BUSINESS",
    "family": "FAMILY",
    "sweet": "SWEET",
    "adrenaline": "ADRENALINE",
}
