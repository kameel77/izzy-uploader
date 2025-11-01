"""CSV parsing utilities for the Izzy Uploader service."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from .models import Vehicle, vehicle_from_row
from .normalizers import clean_row


class CsvValidationError(Exception):
    """Raised when the CSV file contains invalid data."""

    def __init__(self, errors: Sequence[str]):
        super().__init__("\n".join(errors))
        self.errors = list(errors)


def load_vehicles_from_csv(path: Path) -> Tuple[List[Vehicle], List[str]]:
    """Load vehicles from a CSV file returning records and validation errors."""

    vehicles: List[Vehicle] = []
    errors: List[str] = []

    with path.open("r", newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        line_number = 1  # account for header
        for row in reader:
            line_number += 1
            try:
                vehicles.append(vehicle_from_row(clean_row(row)))
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(f"Line {line_number}: {exc}")

    return vehicles, errors


def assert_no_errors(errors: Iterable[str]) -> None:
    errors = list(errors)
    if errors:
        raise CsvValidationError(errors)
