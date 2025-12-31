"""Command line entry point for the Izzy Uploader service."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from .config import ServiceConfig
from .csv_loader import load_vehicles_from_csv
from .client import IzzyleaseClient
from .pipelines.import_pipeline import PipelineReport, VehicleSynchronizer
from .state import ImageStateStore, VehicleStateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """Entrypoint for the Izzy Uploader command line interface."""


@cli.command("sync")
@click.argument("csv_path", type=click.Path(exists=True, path_type=Path))
@click.option("--close-missing", is_flag=True, help="Close vehicles that are missing from the CSV file.")
@click.option("--update-prices", is_flag=True, help="Update prices for existing vehicles if they changed.")
@click.option("--json", "as_json", is_flag=True, help="Print the pipeline report as JSON.")
def sync_command(csv_path: Path, close_missing: bool, update_prices: bool, as_json: bool) -> None:
    """Synchronise vehicles defined in *CSV_PATH* with the Izzylease platform."""

    config = ServiceConfig.from_env()
    client = IzzyleaseClient(config)
    state_store = VehicleStateStore(config.state_file)

    # Initialize image state store with error handling
    image_state_store = None
    try:
        image_state_store = ImageStateStore(config.image_state_file)
        LOGGER.info(f"Using image state file: {config.image_state_file}")
        LOGGER.info(f"Image state store initialized successfully: {image_state_store is not None}")
    except Exception as e:
        LOGGER.error(f"Failed to initialize image state store at {config.image_state_file}: {e}")
        # Try fallback to /tmp directory
        try:
            import tempfile
            temp_file = Path(tempfile.gettempdir()) / "izzy_uploader_image_state.json"
            image_state_store = ImageStateStore(temp_file)
            LOGGER.info(f"Using fallback image state file: {temp_file}")
            LOGGER.info("Image state store initialized with fallback path")
        except Exception as e2:
            LOGGER.error(f"Failed to initialize image state store with fallback: {e2}")
            LOGGER.warning("Image uploads will be disabled")

    vehicles, csv_errors = load_vehicles_from_csv(csv_path)

    # Log image parsing results
    for i, vehicle in enumerate(vehicles):
        if vehicle.featured_photo or vehicle.other_photos:
            LOGGER.info(f"Vehicle {i+1} ({vehicle.vin}): featured_photo={vehicle.featured_photo is not None}, other_photos={len(vehicle.other_photos)}")

    synchronizer = VehicleSynchronizer(client, state_store, image_state_store)
    report = synchronizer.run(vehicles, close_missing=close_missing, update_prices=update_prices)

    for csv_error in csv_errors:
        report.record_error(
            f"CSV line {csv_error.line_number}: {csv_error.message}",
            vin=csv_error.vin,
            car_id=None,
        )
    _emit_report(report, as_json=as_json)


def _emit_report(report: PipelineReport, *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(report.as_dict(include_details=True), ensure_ascii=False, indent=2))
    else:
        click.echo("Synchronisation finished:")
        for key, value in report.as_dict().items():
            click.echo(f"  - {key}: {value}")


if __name__ == "__main__":  # pragma: no cover - entry point
    cli()
