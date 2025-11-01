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


def test_partner_specific_values_are_normalised(tmp_path: Path) -> None:
    csv_content = dedent(
        """
        configurationNumber,vin,category,make,model,manufactureYear,mileage,engineCode,cubicCapacity,acceleration,fuelType,power,transmissionType,driveWheels,type,carClass,doors,color,availableFrom,firstRegistrationDate,description,pricing_listPrice,pricing_salesPrice,pricing_miniPrice,locationId
        AAU03218IE,U5YPU81BGPL155538,osobowy,Kia,Sportage,2023,29550,,1591.00,11,HYBRYDA (ETYLINA + NAPĘD ELEKTR.),150.00,Automatyczna hydrauliczna (klasyczna),Na przednie koła,SUV,Hatchback,0,Niebieski,2025-06-16 15:01:50,2023-08-01,ABS | ASR | Klimatyzacja | ABS,109900.00,109900.00,109900.00,128
        AAU03225IE,TSMJYBA2S00706179,osobowy,Suzuki,Sx4,2019,95501,,1373.00,,ETYLINA,140.00,Manualna,4x4 (stały),SUV,Hatchback,0,Srebrny,2025-06-17 13:51:54,2019-09-17,NULL,77900.00,77900.00,77900.00,128
        """
    ).strip()
    path = tmp_path / "vehicles.csv"
    path.write_text(csv_content, encoding="utf-8")

    vehicles, errors = load_vehicles_from_csv(path)

    assert not errors
    assert len(vehicles) == 2

    first = vehicles[0]
    assert first.vin == "U5YPU81BGPL155538"
    assert first.category == "PASSENGER"
    assert first.fuel_type == "HYBRID"
    assert first.power == 150
    assert first.cubic_capacity == 1591.0
    assert first.acceleration == 11.0
    assert first.transmission_type == "AUTOMATIC"
    assert first.drive_wheels == "FRONT"
    assert first.vehicle_type == "SUV"
    assert first.available_from and first.available_from.isoformat() == "2025-06-16"
    assert first.first_registration_date and first.first_registration_date.isoformat() == "2023-08-01"
    assert first.description == "ABS\nASR\nKlimatyzacja"
    assert first.engine_code == "-"
    assert first.doors is None
    assert first.location_id is None

    second = vehicles[1]
    assert second.vin == "TSMJYBA2S00706179"
    assert second.drive_wheels == "FOUR"
    assert second.acceleration == 0.0
    assert second.power == 140
