from decimal import Decimal
from pathlib import Path
from typing import Dict, List

from izzy_uploader.models import Vehicle
from izzy_uploader.pipelines.import_pipeline import PipelineReport, VehicleSynchronizer
from izzy_uploader.state import VehicleStateStore


class FakeClient:
    def __init__(self) -> None:
        self.created: Dict[str, Vehicle] = {}
        self.updated: Dict[str, Vehicle] = {}
        self.deleted: List[str] = []

    def create_vehicle(self, vehicle: Vehicle) -> str:
        car_id = f"id-{vehicle.vin}"
        self.created[vehicle.vin] = vehicle
        return car_id

    def update_vehicle(self, car_id: str, vehicle: Vehicle) -> None:
        self.updated[car_id] = vehicle

    def delete_vehicle(self, car_id: str) -> None:
        self.deleted.append(car_id)


def make_vehicle(vin: str, sales_price: str, *, configuration_number: str | None = None) -> Vehicle:
    return Vehicle(
        configuration_number=configuration_number,
        vin=vin,
        category="PASSENGER",
        make="Test",
        model="Model",
        manufacture_year=2020,
        mileage=1000,
        engine_code="ECODE",
        cubic_capacity=1998.0,
        acceleration=7.2,
        fuel_type="PETROL",
        power=180,
        transmission_type="AUTOMATIC",
        drive_wheels="FRONT",
        vehicle_type="SALOON",
        doors=4,
        color="Blue",
        list_price=Decimal("200000"),
        sales_price=Decimal(sales_price),
    )


def test_pipeline_creates_and_updates(tmp_path: Path) -> None:
    client = FakeClient()
    state_store = VehicleStateStore(tmp_path / "state.json")
    # Pre-populate state so VIN-B is treated as existing.
    state_store.upsert("VIN-B", "id-VIN-B", "B")

    synchronizer = VehicleSynchronizer(client, state_store)
    vehicles = [
        make_vehicle("VIN-A", "180000", configuration_number="A"),
        make_vehicle("VIN-B", "170000", configuration_number="B"),
    ]

    report = synchronizer.run(vehicles, close_missing=True, update_prices=True)

    assert isinstance(report, PipelineReport)
    assert report.created == 1
    assert report.updated == 1
    assert report.closed == 0
    assert report.errors == []
    assert report.created_vehicles == [{"vin": "VIN-A", "car_id": "id-VIN-A"}]
    assert report.updated_vehicles == [{"vin": "VIN-B", "car_id": "id-VIN-B"}]
    assert report.deleted_vehicles == []

    assert "VIN-A" in client.created
    assert "id-VIN-B" in client.updated
    # Ensure state now remembers VIN-A as well.
    assert state_store.get_car_id("VIN-A") == "id-VIN-A"


def test_pipeline_closes_missing_when_requested(tmp_path: Path) -> None:
    client = FakeClient()
    state_store = VehicleStateStore(tmp_path / "state.json")
    state_store.upsert("VIN-A", "id-VIN-A", "A")
    state_store.upsert("VIN-B", "id-VIN-B", "B")

    synchronizer = VehicleSynchronizer(client, state_store)
    vehicles = [make_vehicle("VIN-A", "150000", configuration_number="A")]

    report = synchronizer.run(vehicles, close_missing=True)

    assert report.closed == 1
    assert client.deleted == ["id-VIN-B"]
    # VIN-B remains in the state store but marked as inactive so it can be reactivated later.
    assert state_store.get_car_id("VIN-B") == "id-VIN-B"
    assert "VIN-B" not in list(state_store.known_vins())
    assert report.deleted_vehicles == [{"vin": "VIN-B", "car_id": "id-VIN-B"}]


def test_pipeline_collects_errors_when_api_fails(tmp_path: Path) -> None:
    class FailingClient(FakeClient):
        def update_vehicle(self, car_id: str, vehicle: Vehicle) -> None:
            raise RuntimeError("boom")

    client = FailingClient()
    state_store = VehicleStateStore(tmp_path / "state.json")
    state_store.upsert("VIN-A", "id-VIN-A", "A")

    synchronizer = VehicleSynchronizer(client, state_store)
    vehicles = [make_vehicle("VIN-A", "150000", configuration_number="A")]
    report = synchronizer.run(vehicles, close_missing=False)

    assert report.updated == 0
    assert report.errors
    assert "update failed" in report.errors[0]
    assert report.error_details == [
        {
            "vin": "VIN-A",
            "car_id": "id-VIN-A",
            "error_message": "update failed: boom",
        }
    ]


def test_pipeline_reactivates_deleted_vehicle(tmp_path: Path) -> None:
    client = FakeClient()
    state_store = VehicleStateStore(tmp_path / "state.json")
    state_store.upsert("VIN-A", "id-VIN-A", "A")
    state_store.mark_deleted("VIN-A")

    synchronizer = VehicleSynchronizer(client, state_store)
    vehicles = [make_vehicle("VIN-A", "150000", configuration_number="A")]

    report = synchronizer.run(vehicles, close_missing=False)

    assert report.created == 0
    assert report.updated == 1
    assert report.updated_vehicles == [{"vin": "VIN-A", "car_id": "id-VIN-A"}]
    assert "VIN-A" in list(state_store.known_vins())


def test_pipeline_recreates_vehicle_if_remote_missing(tmp_path: Path) -> None:
    class MissingClient(FakeClient):
        def update_vehicle(self, car_id: str, vehicle: Vehicle) -> None:
            raise RuntimeError("API request failed with status 404: Not Found")

        def create_vehicle(self, vehicle: Vehicle) -> str:
            car_id = f"new-{vehicle.vin}"
            self.created[vehicle.vin] = vehicle
            return car_id

    client = MissingClient()
    state_store = VehicleStateStore(tmp_path / "state.json")
    state_store.upsert("VIN-A", "stale-id", "A")

    synchronizer = VehicleSynchronizer(client, state_store)
    vehicles = [make_vehicle("VIN-A", "150000", configuration_number="A")]

    report = synchronizer.run(vehicles, close_missing=False)

    assert report.created == 1
    assert report.updated == 0
    assert report.created_vehicles == [{"vin": "VIN-A", "car_id": "new-VIN-A"}]
    assert state_store.get_car_id("VIN-A") == "new-VIN-A"
    assert "VIN-A" in list(state_store.known_vins())
