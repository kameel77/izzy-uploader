from pathlib import Path
from textwrap import dedent

import pytest

from izzy_uploader.csv_loader import load_vehicles_from_csv


def test_loads_valid_vehicle(tmp_path: Path) -> None:
    csv_content = dedent(
        """
        configurationNumber,vin,make,model,manufactureYear,pricing_salesPrice
        V1,1FTFW1E50JFC12345,Ford,F-150,2019,12345.67
        """
    ).strip()
    path = tmp_path / "vehicles.csv"
    path.write_text(csv_content, encoding="utf-8")

    vehicles, errors = load_vehicles_from_csv(path)

    assert not errors
    assert len(vehicles) == 1
    vehicle = vehicles[0]
    assert vehicle.external_id == "V1"
    assert vehicle.sales_price == pytest.approx(12345.67)


def test_invalid_rows_return_errors(tmp_path: Path) -> None:
    csv_content = dedent(
        """
        configurationNumber,vin,make,model,manufactureYear
        ,,Ford,F-150,2019
        """
    ).strip()
    path = tmp_path / "vehicles.csv"
    path.write_text(csv_content, encoding="utf-8")

    vehicles, errors = load_vehicles_from_csv(path)

    assert not vehicles
    assert errors
    assert "Missing required CSV fields" in errors[0]
