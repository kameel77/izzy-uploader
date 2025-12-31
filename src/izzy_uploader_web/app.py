"""Minimal Flask UI for the Izzy Uploader."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Optional

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    Blueprint,
    session,
    send_file,
    url_for,
)

from izzy_uploader.client import IzzyleaseClient
from izzy_uploader.config import ServiceConfig
from izzy_uploader.csv_loader import load_vehicles_from_csv
from izzy_uploader.normalizers import (
    get_location_map_path,
    load_location_map,
    save_location_map,
)
from izzy_uploader.pipelines.import_pipeline import VehicleSynchronizer
from izzy_uploader.state import ImageStateStore, VehicleStateStore
from izzy_uploader_web.api import api_bp

LOGGER = logging.getLogger(__name__)

REPORTS: Dict[str, Dict[str, str]] = {}

# Progress tracking for long-running uploads
PROGRESS_TRACKERS: Dict[str, Dict[str, any]] = {}


class ProgressTrackingSynchronizer(VehicleSynchronizer):
    """Extended VehicleSynchronizer that updates progress tracking."""

    def __init__(self, client, state_store, image_state_store, upload_id):
        super().__init__(client, state_store, image_state_store)
        self.upload_id = upload_id
        self.processed_count = 0

    def _upsert_vehicle(self, vehicle, report):
        """Override to update progress tracking."""
        # Update progress
        PROGRESS_TRACKERS[self.upload_id]["current_vehicle"] = vehicle.vin or vehicle.configuration_number or "Unknown"
        PROGRESS_TRACKERS[self.upload_id]["current_operation"] = f"Processing vehicle: {vehicle.vin or vehicle.configuration_number or 'Unknown'}"
        PROGRESS_TRACKERS[self.upload_id]["processed_vehicles"] = self.processed_count

        # Calculate progress percentage
        total = PROGRESS_TRACKERS[self.upload_id]["total_vehicles"]
        if total > 0:
            PROGRESS_TRACKERS[self.upload_id]["progress"] = int((self.processed_count / total) * 100)

        # Call parent method
        result = super()._upsert_vehicle(vehicle, report)

        self.processed_count += 1
        return result

    def run(self, vehicles, *, close_missing=False, update_prices=False):
        """Override to update final progress."""
        PROGRESS_TRACKERS[self.upload_id]["current_operation"] = f"Starting synchronization of {len(vehicles)} vehicles..."
        PROGRESS_TRACKERS[self.upload_id]["total_vehicles"] = len(vehicles)

        # Call parent method
        report = super().run(vehicles, close_missing=close_missing, update_prices=update_prices)

        # Update final progress
        PROGRESS_TRACKERS[self.upload_id]["progress"] = 100
        PROGRESS_TRACKERS[self.upload_id]["processed_vehicles"] = len(vehicles)
        PROGRESS_TRACKERS[self.upload_id]["current_operation"] = "Synchronization completed!"

        return report


def _process_upload_background(upload_id: str, vehicles: list, csv_errors: list, tmp_csv_path: Path) -> None:
    """Background processing function for CSV uploads."""
    try:
        # Get session config (this might not work in background thread, so we need to handle it)
        try:
            config = ServiceConfig.from_env()
        except Exception as exc:
            PROGRESS_TRACKERS[upload_id]["status"] = "error"
            PROGRESS_TRACKERS[upload_id]["errors"].append(f"Configuration error: {exc}")
            PROGRESS_TRACKERS[upload_id]["completed"] = True
            return

        PROGRESS_TRACKERS[upload_id]["status"] = "processing"
        PROGRESS_TRACKERS[upload_id]["current_operation"] = "Initializing state stores..."

        # Initialize stores
        state_store = VehicleStateStore(config.state_file)

        # Initialize image state store with error handling
        image_state = None
        try:
            image_state = ImageStateStore(config.image_state_file)
        except Exception as e:
            try:
                temp_file = Path(tempfile.gettempdir()) / "izzy_uploader_image_state.json"
                image_state = ImageStateStore(temp_file)
            except Exception as e2:
                PROGRESS_TRACKERS[upload_id]["errors"].append(f"Image state store error: {e2}")

        PROGRESS_TRACKERS[upload_id]["current_operation"] = "Starting synchronization..."

        # Create custom synchronizer with progress tracking
        synchronizer = ProgressTrackingSynchronizer(
            IzzyleaseClient(config),
            state_store,
            image_state,
            upload_id
        )

        # Get options from session if possible (this is tricky in background thread)
        close_missing = False  # Default to False for background processing
        update_prices = False

        report = synchronizer.run(vehicles, close_missing=close_missing, update_prices=update_prices)

        # Add CSV errors to report
        for csv_error in csv_errors:
            report.record_error(
                f"CSV line {csv_error.line_number}: {csv_error.message}",
                vin=csv_error.vin,
            )

        # Save report
        PROGRESS_TRACKERS[upload_id]["current_operation"] = "Generating report..."
        report_data = report.as_dict(include_details=True)
        report_json = json.dumps(report_data, ensure_ascii=False, indent=2)

        report_id = str(uuid.uuid4())
        report_path = Path(tempfile.gettempdir()) / f"izzy_report_{report_id}.json"
        report_path.write_text(report_json, encoding="utf-8")
        REPORTS[report_id] = {"path": str(report_path), "filename": f"report_{report_id}.json"}

        # Update progress tracker
        PROGRESS_TRACKERS[upload_id]["status"] = "completed"
        PROGRESS_TRACKERS[upload_id]["progress"] = 100
        PROGRESS_TRACKERS[upload_id]["completed"] = True
        PROGRESS_TRACKERS[upload_id]["report_id"] = report_id
        PROGRESS_TRACKERS[upload_id]["current_operation"] = "Upload completed successfully!"

    except Exception as exc:
        PROGRESS_TRACKERS[upload_id]["status"] = "error"
        PROGRESS_TRACKERS[upload_id]["errors"].append(f"Processing error: {exc}")
        PROGRESS_TRACKERS[upload_id]["completed"] = True
        LOGGER.exception(f"Background upload processing failed for {upload_id}")

    finally:
        # Clean up temp file
        try:
            tmp_csv_path.unlink(missing_ok=True)
        except:
            pass


def _config_from_session() -> ServiceConfig:
    overrides = session.get("izzylease_overrides") or None
    return ServiceConfig.from_env(overrides=overrides)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["SECRET_KEY"] = os.getenv("IZZY_UPLOADER_WEB_SECRET", "dev-secret")
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

    bp = Blueprint("web", __name__)

    @bp.route("/", methods=["GET"])
    def index() -> str:
        return render_template("index.html")

    @bp.route("/settings", methods=["GET", "POST"])
    def settings() -> str:
        if request.method == "POST":
            api_base_url = (request.form.get("api_base_url") or "").strip()
            client_id = (request.form.get("client_id") or "").strip()
            client_secret = (request.form.get("client_secret") or "").strip()
            token_url = (request.form.get("token_url") or "").strip()
            dealer_id = (request.form.get("dealer_id") or "").strip()

            if not api_base_url or not client_id or not client_secret:
                flash("Wprowadź API base URL, client_id oraz client_secret.", "error")
            else:
                session["izzylease_overrides"] = {
                    "API_BASE_URL": api_base_url,
                    "CLIENT_ID": client_id,
                    "CLIENT_SECRET": client_secret,
                    "TOKEN_URL": token_url,
                    "DEALER_ID": dealer_id,
                }
                flash("Zapisano połączenie z Izzylease dla tej sesji.", "success")
                return redirect(url_for("web.settings"))

        overrides = session.get("izzylease_overrides", {})
        return render_template(
            "settings.html",
            api_base_url=overrides.get("API_BASE_URL", ""),
            client_id=overrides.get("CLIENT_ID", ""),
            client_secret=overrides.get("CLIENT_SECRET", ""),
            token_url=overrides.get("TOKEN_URL", ""),
            dealer_id=overrides.get("DEALER_ID", ""),
        )

    @bp.route("/upload", methods=["POST"])
    def upload() -> str:
        file = request.files.get("file")
        if file is None or file.filename == "":
            flash("Wybierz plik CSV.", "error")
            return redirect(url_for("web.index"))

        # Generate unique upload ID for progress tracking
        upload_id = str(uuid.uuid4())

        # Initialize progress tracker
        PROGRESS_TRACKERS[upload_id] = {
            "status": "initializing",
            "progress": 0,
            "total_vehicles": 0,
            "processed_vehicles": 0,
            "current_vehicle": "",
            "current_operation": "Loading CSV file...",
            "errors": [],
            "completed": False,
            "report_id": None,
        }

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
            file.save(tmp_csv.name)
            tmp_csv_path = Path(tmp_csv.name)

        try:
            # Load and validate CSV
            PROGRESS_TRACKERS[upload_id]["current_operation"] = "Validating CSV data..."
            vehicles, csv_errors = load_vehicles_from_csv(tmp_csv_path)
            PROGRESS_TRACKERS[upload_id]["total_vehicles"] = len(vehicles)

            for csv_error in csv_errors:
                PROGRESS_TRACKERS[upload_id]["errors"].append(
                    f"CSV line {csv_error.line_number}: {csv_error.message}"
                )

            # Start background processing
            import threading
            thread = threading.Thread(target=_process_upload_background, args=(upload_id, vehicles, csv_errors, tmp_csv_path))
            thread.daemon = True
            thread.start()

            return redirect(url_for("web.upload_progress", upload_id=upload_id))

        except Exception as exc:
            PROGRESS_TRACKERS[upload_id]["status"] = "error"
            PROGRESS_TRACKERS[upload_id]["errors"].append(str(exc))
            PROGRESS_TRACKERS[upload_id]["completed"] = True
            return redirect(url_for("web.upload_progress", upload_id=upload_id))

    @bp.route("/upload/progress/<upload_id>", methods=["GET"])
    def upload_progress(upload_id: str) -> str:
        tracker = PROGRESS_TRACKERS.get(upload_id)
        if not tracker:
            flash("Upload session not found.", "error")
            return redirect(url_for("web.index"))

        if tracker.get("completed") and tracker.get("report_id"):
            # Redirect to results if completed
            return redirect(url_for("web.upload_result", upload_id=upload_id))

        return render_template("upload_progress.html", upload_id=upload_id, tracker=tracker)

    @bp.route("/upload/progress/<upload_id>/status", methods=["GET"])
    def upload_progress_status(upload_id: str) -> str:
        tracker = PROGRESS_TRACKERS.get(upload_id)
        if not tracker:
            return json.dumps({"error": "Upload session not found"}), 404

        return json.dumps({
            "status": tracker["status"],
            "progress": tracker["progress"],
            "total_vehicles": tracker["total_vehicles"],
            "processed_vehicles": tracker["processed_vehicles"],
            "current_vehicle": tracker["current_vehicle"],
            "current_operation": tracker["current_operation"],
            "errors": tracker["errors"],
            "completed": tracker["completed"],
        })

    @bp.route("/upload/result/<upload_id>", methods=["GET"])
    def upload_result(upload_id: str) -> str:
        tracker = PROGRESS_TRACKERS.get(upload_id)
        if not tracker or not tracker.get("completed"):
            flash("Upload not completed yet.", "error")
            return redirect(url_for("web.index"))

        report_id = tracker.get("report_id")
        if not report_id or report_id not in REPORTS:
            flash("Report not found.", "error")
            return redirect(url_for("web.index"))

        report_entry = REPORTS[report_id]
        report_path = Path(report_entry["path"])

        try:
            report_data = json.loads(report_path.read_text(encoding="utf-8"))
            summary = {
                "created": report_data.get("created", 0),
                "updated": report_data.get("updated", 0),
                "price_updates": report_data.get("price_updates", 0),
                "closed": report_data.get("closed", 0),
                "errors": len(report_data.get("errors", [])),
            }

            # Clean up progress tracker after some time
            import time
            def cleanup_tracker():
                time.sleep(300)  # Keep for 5 minutes
                PROGRESS_TRACKERS.pop(upload_id, None)

            cleanup_thread = threading.Thread(target=cleanup_tracker)
            cleanup_thread.daemon = True
            cleanup_thread.start()

            return render_template(
                "result.html",
                report=json.dumps(report_data, ensure_ascii=False, indent=2),
                summary=summary,
                report_id=report_id,
                csv_errors=[],  # Already included in tracker errors
            )
        except Exception as exc:
            flash(f"Error loading report: {exc}", "error")
            return redirect(url_for("web.index"))

    @bp.route("/download/<report_id>", methods=["GET"])
    def download(report_id: str):
        entry: Optional[Dict[str, str]] = REPORTS.get(report_id)
        if not entry:
            flash("Raport wygasł lub nie istnieje.", "error")
            return redirect(url_for("web.index"))
        return send_file(entry["path"], as_attachment=True, download_name=entry["filename"])

    @bp.route("/locations", methods=["GET", "POST"])
    def locations() -> str:
        mapping = load_location_map()

        if request.method == "POST":
            partner_id = (request.form.get("partner_id") or "").strip()
            location_uuid = (request.form.get("location_uuid") or "").strip()

            if not partner_id or not location_uuid:
                flash("Wprowadź numer partnera i UUID lokalizacji.", "error")
            else:
                mapping[partner_id] = location_uuid
                try:
                    save_location_map(mapping)
                    flash("Mapowanie zapisane.", "success")
                    return redirect(url_for("web.locations"))
                except Exception as exc:  # pragma: no cover - filesystem failure
                    flash(f"Nie udało się zapisać mapowania: {exc}", "error")

        mapping_items = sorted(load_location_map().items())
        return render_template(
            "locations.html",
            mapping=mapping_items,
            map_path=get_location_map_path(),
        )

    @bp.route("/photos", methods=["GET", "POST"])
    def photos() -> str:
        if request.method == "GET":
            return render_template("photos.html")

        car_id = (request.form.get("car_id") or "").strip()
        delete_all = request.form.get("delete_all_images") == "on"
        main_image = request.files.get("main_image")
        extra_images = request.files.getlist("extra_images")
        delete_image_ids_raw = (request.form.get("delete_image_ids") or "").strip()

        if not car_id:
            flash("Podaj ID pojazdu.", "error")
            return render_template("photos.html")

        all_files = [file for file in [main_image] + extra_images if file and file.filename]
        delete_ids = [item for item in delete_image_ids_raw.replace(",", " ").split() if item]

        if not all_files and not delete_ids and not delete_all:
            flash(
                "Dodaj co najmniej jedno zdjęcie, identyfikator do usunięcia lub zaznacz usunięcie wszystkich.",
                "error",
            )
            return render_template("photos.html", car_id=car_id)

        try:
            config = _config_from_session()
        except Exception as exc:  # pragma: no cover - environment misconfiguration
            flash(str(exc), "error")
            return render_template("photos.html", car_id=car_id)

        client = IzzyleaseClient(config)
        upload_results = []
        image_state = ImageStateStore(config.image_state_file)

        def _upload_image(file, label: str) -> None:
            content = file.read()
            if not content:
                upload_results.append(
                    {"label": label, "status": "error", "message": "Plik jest pusty."}
                )
                return

            content_type = file.mimetype or "application/octet-stream"
            try:
                image_id = client.upload_car_image(
                    car_id, content, content_type=content_type, filename=file.filename
                )
            except Exception as exc:  # pragma: no cover - network failure path
                upload_results.append(
                    {"label": label, "status": "error", "message": str(exc)}
                )
                return

            upload_results.append(
                {
                    "label": label,
                    "status": "success",
                    "message": f"Przesłano (imageId: {image_id}).",
                    "image_id": image_id,
                }
            )

        if main_image and main_image.filename:
            _upload_image(main_image, "Zdjęcie główne")

        for index, file in enumerate(extra_images, start=1):
            if file and file.filename:
                _upload_image(file, f"Zdjęcie dodatkowe #{index}")

        deletion_results = []
        changed_state = False
        if delete_all:
            try:
                known_images = image_state.get_images(car_id)
                if not known_images:
                    deletion_results.append(
                        {
                            "label": "Wszystkie zdjęcia",
                            "status": "error",
                            "message": "Brak zapamiętanych zdjęć dla tego pojazdu.",
                        }
                    )
                else:
                    for image_id in known_images:
                        try:
                            client.delete_car_image(car_id, image_id)
                            deletion_results.append(
                                {
                                    "label": image_id,
                                    "status": "success",
                                    "message": "Usunięto zdjęcie.",
                                }
                            )
                            image_state.remove_image(car_id, image_id)
                            changed_state = True
                        except Exception as exc:  # pragma: no cover - network failure path
                            deletion_results.append(
                                {
                                    "label": image_id,
                                    "status": "error",
                                    "message": str(exc),
                                }
                            )

                deletion_results.append(
                    {
                        "label": "Wszystkie zdjęcia",
                        "status": "success" if known_images else "error",
                        "message": "Usunięto wszystkie zapamiętane zdjęcia dla pojazdu."
                        if known_images
                        else "Brak zapamiętanych zdjęć do usunięcia.",
                    }
                )
            except Exception as exc:  # pragma: no cover - network failure path
                deletion_results.append(
                    {
                        "label": "Wszystkie zdjęcia",
                        "status": "error",
                        "message": str(exc),
                    }
                )

        for image_id in delete_ids:
            try:
                client.delete_car_image(car_id, image_id)
                deletion_results.append(
                    {
                        "label": image_id,
                        "status": "success",
                        "message": "Usunięto zdjęcie.",
                    }
                )
                image_state.remove_image(car_id, image_id)
                changed_state = True
            except Exception as exc:  # pragma: no cover - network failure path
                deletion_results.append(
                    {
                        "label": image_id,
                        "status": "error",
                        "message": str(exc),
                    }
                )

        # zapisz stan zdjęć gdy coś się zmieniło lub dodaliśmy nowe
        if upload_results:
            for result in upload_results:
                if result.get("status") == "success" and result.get("image_id"):
                    image_state.add_image(car_id, str(result["image_id"]))
                    changed_state = True

        if changed_state:
            image_state.save()

        return render_template(
            "photos.html",
            car_id=car_id,
            upload_results=upload_results,
            deletion_results=deletion_results,
        )

    app.register_blueprint(bp)
    app.register_blueprint(api_bp)
    return app


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    create_app().run(debug=True)
