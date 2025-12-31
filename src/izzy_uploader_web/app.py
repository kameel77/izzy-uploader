"""Minimal Flask UI for the Izzy Uploader."""
from __future__ import annotations

import json
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

REPORTS: Dict[str, Dict[str, str]] = {}


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

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
            file.save(tmp_csv.name)
            tmp_csv_path = Path(tmp_csv.name)

        vehicles, csv_errors = load_vehicles_from_csv(tmp_csv_path)
        tmp_csv_path.unlink(missing_ok=True)

        try:
            config = _config_from_session()
        except Exception as exc:  # pragma: no cover - environment misconfiguration
            flash(str(exc), "error")
            return render_template("result.html", errors=[str(exc)])

        close_missing = request.form.get("close_missing") == "on"
        update_prices = request.form.get("update_prices") == "on"

        state_store = VehicleStateStore(config.state_file)
        image_state = ImageStateStore(config.image_state_file)
        synchronizer = VehicleSynchronizer(IzzyleaseClient(config), state_store)
        report = synchronizer.run(
            vehicles,
            close_missing=close_missing,
            update_prices=update_prices,
        )

        for csv_error in csv_errors:
            report.record_error(
                f"CSV line {csv_error.line_number}: {csv_error.message}",
                vin=csv_error.vin,
            )

        report_data = report.as_dict(include_details=True)
        report_json = json.dumps(report_data, ensure_ascii=False, indent=2)

        report_id = str(uuid.uuid4())
        report_path = Path(tempfile.gettempdir()) / f"izzy_report_{report_id}.json"
        report_path.write_text(report_json, encoding="utf-8")
        REPORTS[report_id] = {"path": str(report_path), "filename": f"report_{report_id}.json"}

        return render_template(
            "result.html",
            report=report_json,
            summary=report.as_dict(include_details=False),
            report_id=report_id,
            csv_errors=[err.format_for_display() for err in csv_errors],
        )

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
