from dataclasses import dataclass
from typing import Dict, List

from izzy_uploader.models import Vehicle
from izzy_uploader.pipelines.import_pipeline import PipelineReport, VehicleSynchronizer


@dataclass
class FakeClient:
    vehicles: Dict[str, Dict[str, object]]
    created: List[str]
    updated: List[str]
    closed: List[str]
    price_updates: List[Dict[str, object]]

    def build_vehicle_lookup(self) -> Dict[str, Dict[str, object]]:
        return dict(self.vehicles)

    def create_vehicle(self, vehicle: Vehicle) -> None:
        self.created.append(vehicle.external_id)
        self.vehicles[vehicle.external_id] = {"externalId": vehicle.external_id, "pricing": {"salesPrice": vehicle.sales_price}}

    def update_vehicle(self, vehicle: Vehicle) -> None:
        self.updated.append(vehicle.external_id)
        self.vehicles[vehicle.external_id] = {"externalId": vehicle.external_id, "pricing": {"salesPrice": vehicle.sales_price}}

    def close_vehicle(self, external_id: str) -> None:
        self.closed.append(external_id)
        self.vehicles.pop(external_id, None)

    def update_price(self, external_id: str, price: float, notify_discount: bool) -> None:
        self.price_updates.append({"external_id": external_id, "price": price, "notify_discount": notify_discount})
        self.vehicles[external_id]["pricing"]["salesPrice"] = price


def make_vehicle(external_id: str, sales_price: float) -> Vehicle:
    return Vehicle(
        external_id=external_id,
        vin="VIN-" + external_id,
        make="Test",
        model="Model",
        manufacture_year=2020,
        mileage=None,
        fuel_type=None,
        power=None,
        transmission_type=None,
        drive_wheels=None,
        vehicle_type=None,
        car_class=None,
        doors=None,
        color=None,
        available_from=None,
        first_registration_date=None,
        description=None,
        list_price=None,
        sales_price=sales_price,
        mini_price=None,
        location_id=None,
    )


def test_pipeline_creates_and_updates(tmp_path) -> None:
    client = FakeClient(
        vehicles={
            "B": {"externalId": "B", "pricing": {"salesPrice": 15000.0}},
        },
        created=[],
        updated=[],
        closed=[],
        price_updates=[],
    )
    synchronizer = VehicleSynchronizer(client)  # type: ignore[arg-type]

    vehicles = [make_vehicle("A", 12000.0), make_vehicle("B", 14000.0)]
    report = synchronizer.run(vehicles, close_missing=True, update_prices=True)

    assert isinstance(report, PipelineReport)
    assert report.created == 1
    assert report.updated == 1
    assert report.closed == 0  # because CSV had both A and B
    assert report.price_updates == 1
    assert report.errors == []

    assert client.created == ["A"]
    assert client.updated == ["B"]
    assert client.price_updates == [
        {"external_id": "B", "price": 14000.0, "notify_discount": True}
    ]


def test_pipeline_closes_missing_when_requested() -> None:
    client = FakeClient(
        vehicles={
            "A": {"externalId": "A", "pricing": {"salesPrice": 10000.0}},
            "B": {"externalId": "B", "pricing": {"salesPrice": 10000.0}},
        },
        created=[],
        updated=[],
        closed=[],
        price_updates=[],
    )
    synchronizer = VehicleSynchronizer(client)  # type: ignore[arg-type]

    vehicles = [make_vehicle("A", 10000.0)]
    report = synchronizer.run(vehicles, close_missing=True, update_prices=False)

    assert report.closed == 1
    assert client.closed == ["B"]


def test_pipeline_collects_errors_when_api_fails() -> None:
    class FailingClient(FakeClient):
        def update_vehicle(self, vehicle: Vehicle) -> None:
            raise RuntimeError("boom")

    client = FailingClient(
        vehicles={"A": {"externalId": "A", "pricing": {"salesPrice": 10000.0}}},
        created=[],
        updated=[],
        closed=[],
        price_updates=[],
    )
    synchronizer = VehicleSynchronizer(client)  # type: ignore[arg-type]

    vehicles = [make_vehicle("A", 10000.0)]
    report = synchronizer.run(vehicles, close_missing=False, update_prices=False)

    assert report.updated == 0
    assert report.errors
    assert "update failed" in report.errors[0]
