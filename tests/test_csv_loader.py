from decimal import Decimal
from pathlib import Path
from textwrap import dedent

from izzy_uploader.csv_loader import load_vehicles_from_csv


def test_loads_valid_vehicle(tmp_path: Path) -> None:
    csv_content = dedent(
        """
        configurationNumber,vin,category,make,model,manufactureYear,mileage,engineCode,cubicCapacity,acceleration,fuelType,power,transmissionType,driveWheels,type,doors,color,pricing_listPrice,pricing_salesPrice
        CONF-1,WBA8E31030K792716,PASSENGER,BMW,Seria 3,2020,15000,B48,1998,7.2,PETROL,184,AUTOMATIC,REAR,SALOON,4,Blue,200000.00,189999.99
        """
    ).strip()
    path = tmp_path / "vehicles.csv"
    path.write_text(csv_content, encoding="utf-8")

    vehicles, errors = load_vehicles_from_csv(path)

    assert not errors
    assert len(vehicles) == 1

    vehicle = vehicles[0]
    assert vehicle.configuration_number == "CONF-1"
    assert vehicle.vin == "WBA8E31030K792716"
    assert vehicle.category == "PASSENGER"
    assert vehicle.list_price == Decimal("200000.00")
    assert vehicle.sales_price == Decimal("189999.99")


def test_invalid_rows_return_errors(tmp_path: Path) -> None:
    csv_content = dedent(
        """
        configurationNumber,vin,category,make,model,manufactureYear,mileage,engineCode,cubicCapacity,acceleration,fuelType,power,transmissionType,driveWheels,type,doors,color,pricing_listPrice,pricing_salesPrice
        CONF-1,,PASSENGER,BMW,Seria 3,2020,15000,B48,1998,7.2,PETROL,184,AUTOMATIC,REAR,SALOON,4,Blue,200000.00,189999.99
        """
    ).strip()
    path = tmp_path / "vehicles.csv"
    path.write_text(csv_content, encoding="utf-8")

    vehicles, errors = load_vehicles_from_csv(path)

    assert not vehicles
    assert errors
    assert "Missing required CSV fields" in errors[0]
