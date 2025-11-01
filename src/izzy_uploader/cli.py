"""Command line entry point for the Izzy Uploader service."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from .config import ServiceConfig
from .csv_loader import assert_no_errors, load_vehicles_from_csv
from .client import IzzyleaseClient
from .pipelines.import_pipeline import PipelineReport, VehicleSynchronizer

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

    vehicles, errors = load_vehicles_from_csv(csv_path)
    assert_no_errors(errors)

    synchronizer = VehicleSynchronizer(client)
    report = synchronizer.run(vehicles, close_missing=close_missing, update_prices=update_prices)
    _emit_report(report, as_json=as_json)


def _emit_report(report: PipelineReport, *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        click.echo("Synchronisation finished:")
        for key, value in report.as_dict().items():
            click.echo(f"  - {key}: {value}")


if __name__ == "__main__":  # pragma: no cover - entry point
    cli()
