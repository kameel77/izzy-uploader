"""Public HTTP API for Izzy Uploader."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from izzy_uploader.client import IzzyleaseClient
from izzy_uploader.config import ServiceConfig
from izzy_uploader.csv_loader import load_vehicles_from_csv
from izzy_uploader.pipelines.import_pipeline import VehicleSynchronizer
from izzy_uploader.state import ImageStateStore, VehicleStateStore

api_bp = Blueprint("api", __name__, url_prefix="/api")


# -- helpers -----------------------------------------------------------------
def _extract_overrides_from_request() -> Optional[Dict[str, str]]:
    """Allow overriding Izzylease credentials via headers (for partner-specific calls)."""

    header_map = {
        "API_BASE_URL": "X-IZZY-API-BASE-URL",
        "CLIENT_ID": "X-IZZY-CLIENT-ID",
        "CLIENT_SECRET": "X-IZZY-CLIENT-SECRET",
        "TOKEN_URL": "X-IZZY-TOKEN-URL",
        "DEALER_ID": "X-IZZY-DEALER-ID",
    }
    overrides: Dict[str, str] = {}
    for key, header_name in header_map.items():
        value = request.headers.get(header_name)
        if value:
            overrides[key] = value
    return overrides or None


def _load_services() -> Tuple[ServiceConfig, IzzyleaseClient, VehicleStateStore, ImageStateStore]:
    overrides = _extract_overrides_from_request()
    config = ServiceConfig.from_env(overrides=overrides)
    client = IzzyleaseClient(config)
    vehicle_state = VehicleStateStore(config.state_file)
    image_state = ImageStateStore(config.image_state_file)
    return config, client, vehicle_state, image_state


def _bool_param(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _image_ids_from_state(image_state: ImageStateStore, car_id: str) -> List[str]:
    ids = image_state.get_images(car_id)
    return [img for img in ids if img]


def _delete_images(
    client: IzzyleaseClient,
    image_state: ImageStateStore,
    car_id: str,
    image_ids: List[str],
) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for image_id in image_ids:
        try:
            client.delete_car_image(car_id, image_id)
            image_state.remove_image(car_id, image_id)
            results.append(
                {
                    "image_id": image_id,
                    "status": "success",
                    "message": "Deleted image.",
                }
            )
        except Exception as exc:  # pragma: no cover - network failure path
            results.append(
                {
                    "image_id": image_id,
                    "status": "error",
                    "message": str(exc),
                }
            )
    return results


# -- endpoints ---------------------------------------------------------------
@api_bp.route("/health", methods=["GET"])
def health() -> tuple:
    return jsonify({"status": "ok"}), 200


@api_bp.route("/vehicles/sync", methods=["POST"])
def sync_csv() -> tuple:
    """Synchronise vehicles from uploaded CSV."""

    upload = request.files.get("file")
    if upload is None or upload.filename == "":
        return jsonify({"error": "Missing CSV file under field 'file'."}), 400

    close_missing = _bool_param(request.form.get("close_missing"))
    update_prices = _bool_param(request.form.get("update_prices"))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
        upload.save(tmp_csv.name)
        tmp_path = Path(tmp_csv.name)

    vehicles, csv_errors = load_vehicles_from_csv(tmp_path)
    tmp_path.unlink(missing_ok=True)

    try:
        config, client, vehicle_state, _image_state = _load_services()
        synchronizer = VehicleSynchronizer(client, vehicle_state)
        report = synchronizer.run(
            vehicles,
            close_missing=close_missing,
            update_prices=update_prices,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        return jsonify({"error": str(exc)}), 500

    return (
        jsonify(
            {
                "config_state_file": str(config.state_file),
                "report": report.as_dict(include_details=True),
                "csv_errors": [err.format_for_display() for err in csv_errors],
            }
        ),
        200,
    )


@api_bp.route("/vehicles/<car_id>/images", methods=["POST"])
def upload_images(car_id: str) -> tuple:
    """Upload main and extra images for a vehicle."""

    main_image = request.files.get("main_image")
    extra_images = request.files.getlist("extra_images")

    if not main_image and not extra_images:
        return jsonify({"error": "Provide at least one file: 'main_image' or 'extra_images'."}), 400

    try:
        _config, client, _vehicle_state, image_state = _load_services()
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": str(exc)}), 500

    results: List[Dict[str, str]] = []

    def _upload(file_storage, label: str) -> None:
        content = file_storage.read()
        if not content:
            results.append({"label": label, "status": "error", "message": "Empty file."})
            return
        content_type = file_storage.mimetype or "application/octet-stream"
        try:
            image_id = client.upload_car_image(
                car_id, content, content_type=content_type, filename=file_storage.filename
            )
            results.append(
                {"label": label, "status": "success", "message": "Uploaded", "image_id": image_id}
            )
            image_state.add_image(car_id, str(image_id))
        except Exception as exc:  # pragma: no cover - network failure path
            results.append({"label": label, "status": "error", "message": str(exc)})

    if main_image and main_image.filename:
        _upload(main_image, "main_image")

    for index, file_storage in enumerate(extra_images, start=1):
        if file_storage and file_storage.filename:
            _upload(file_storage, f"extra_image_{index}")

    image_state.save()
    return jsonify({"results": results}), 200


@api_bp.route("/vehicles/<car_id>/images/<image_id>", methods=["DELETE"])
def delete_image(car_id: str, image_id: str) -> tuple:
    try:
        _config, client, _vehicle_state, image_state = _load_services()
        client.delete_car_image(car_id, image_id)
        image_state.remove_image(car_id, image_id)
        image_state.save()
        return jsonify({"status": "success", "image_id": image_id}), 200
    except Exception as exc:  # pragma: no cover - network failure path
        return jsonify({"status": "error", "message": str(exc)}), 500


@api_bp.route("/vehicles/<car_id>/images", methods=["DELETE"])
def delete_images_bulk(car_id: str) -> tuple:
    """Delete selected or all known images."""

    payload = request.get_json(silent=True) or {}
    delete_all = bool(payload.get("delete_all"))
    image_ids = payload.get("image_ids") or []
    if not isinstance(image_ids, list):
        return jsonify({"error": "image_ids must be a list of strings"}), 400

    try:
        _config, client, _vehicle_state, image_state = _load_services()
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": str(exc)}), 500

    targets: List[str] = [str(img) for img in image_ids if img]
    if delete_all and not targets:
        targets = _image_ids_from_state(image_state, car_id)

    if not targets:
        return jsonify({"error": "No image_ids provided and no known images to delete."}), 400

    results = _delete_images(client, image_state, car_id, targets)
    image_state.save()
    return jsonify({"results": results}), 200


@api_bp.route("/vehicles/<car_id>/images/replace", methods=["POST"])
def replace_images(car_id: str) -> tuple:
    """Delete selected/known images and upload a new featured + extra set."""

    payload = request.form
    delete_all = _bool_param(payload.get("delete_all"))
    provided_ids_raw = payload.get("image_ids") or ""
    provided_ids = [item for item in provided_ids_raw.replace(",", " ").split() if item]

    main_image = request.files.get("main_image")
    extra_images = request.files.getlist("extra_images")

    try:
        _config, client, _vehicle_state, image_state = _load_services()
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": str(exc)}), 500

    targets: List[str] = [str(img) for img in provided_ids if img]
    if delete_all and not targets:
        targets = _image_ids_from_state(image_state, car_id)

    delete_results: List[Dict[str, str]] = []
    if targets:
        delete_results = _delete_images(client, image_state, car_id, targets)

    upload_results: List[Dict[str, str]] = []

    def _upload(file_storage, label: str) -> None:
        content = file_storage.read()
        if not content:
            upload_results.append({"label": label, "status": "error", "message": "Empty file."})
            return
        content_type = file_storage.mimetype or "application/octet-stream"
        try:
            image_id = client.upload_car_image(
                car_id, content, content_type=content_type, filename=file_storage.filename
            )
            upload_results.append(
                {"label": label, "status": "success", "message": "Uploaded", "image_id": image_id}
            )
            image_state.add_image(car_id, str(image_id))
        except Exception as exc:  # pragma: no cover - network failure path
            upload_results.append({"label": label, "status": "error", "message": str(exc)})

    if main_image and main_image.filename:
        _upload(main_image, "main_image")
    for index, file_storage in enumerate(extra_images, start=1):
        if file_storage and file_storage.filename:
            _upload(file_storage, f"extra_image_{index}")

    image_state.save()
    return (
        jsonify(
            {
                "deleted": delete_results,
                "uploaded": upload_results,
            }
        ),
        200,
    )
