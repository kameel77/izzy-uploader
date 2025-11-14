"""CSV parsing utilities for the Izzy Uploader service."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .models import Vehicle, vehicle_from_row
from .normalizers import clean_row


class CsvValidationError(Exception):
    """Raised when the CSV file contains invalid data."""

    def __init__(self, errors: Sequence[str]):
        super().__init__("\n".join(errors))
        self.errors = list(errors)


@dataclass(frozen=True)
class CsvRowError:
    """Represents a validation error tied to a specific CSV row."""

    line_number: int
    message: str
    vin: Optional[str] = None

    def format_for_display(self) -> str:
        label = f"Wiersz {self.line_number}"
        if self.vin:
            label += f" (VIN: {self.vin})"
        return f"{label}: {self.message}"


def load_vehicles_from_csv(path: Path) -> Tuple[List[Vehicle], List[CsvRowError]]:
    """Load vehicles from a CSV file returning records and validation errors."""

    vehicles: List[Vehicle] = []
    errors: List[CsvRowError] = []

    with path.open("r", newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        line_number = 1  # account for header
        for row in reader:
            line_number += 1
            try:
                vehicles.append(vehicle_from_row(clean_row(row)))
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(
                    CsvRowError(
                        line_number=line_number,
                        message=str(exc),
                        vin=(row.get("vin") or "").strip() or None,
                    )
                )

    return vehicles, errors


def assert_no_errors(errors: Iterable[CsvRowError]) -> None:
    collected = list(errors)
    if collected:
        raise CsvValidationError([error.format_for_display() for error in collected])
