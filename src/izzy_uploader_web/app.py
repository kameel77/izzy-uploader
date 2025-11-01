"""Minimal Flask UI for the Izzy Uploader."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Optional

from flask import (
    Blueprint,
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from izzy_uploader.client import IzzyleaseClient
from izzy_uploader.config import ServiceConfig
from izzy_uploader.csv_loader import load_vehicles_from_csv
from izzy_uploader.pipelines.import_pipeline import VehicleSynchronizer
from izzy_uploader.state import VehicleStateStore

REPORTS: Dict[str, Dict[str, str]] = {}


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

    @bp.route("/upload", methods=["POST"])
    def upload() -> str:
        file = request.files.get("file")
        if file is None or file.filename == "":
            flash("Wybierz plik CSV.", "error")
            return redirect(url_for("web.index"))

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
            file.save(tmp_csv.name)
            tmp_csv_path = Path(tmp_csv.name)

        vehicles, errors = load_vehicles_from_csv(tmp_csv_path)
        tmp_csv_path.unlink(missing_ok=True)

        if errors:
            flash("Przetwarzanie CSV zakończone błędem.", "error")
            return render_template("result.html", errors=errors)

        try:
            config = ServiceConfig.from_env()
        except Exception as exc:  # pragma: no cover - environment misconfiguration
            flash(str(exc), "error")
            return render_template("result.html", errors=[str(exc)])

        close_missing = request.form.get("close_missing") == "on"
        update_prices = request.form.get("update_prices") == "on"

        state_store = VehicleStateStore(config.state_file)
        synchronizer = VehicleSynchronizer(IzzyleaseClient(config), state_store)
        report = synchronizer.run(
            vehicles,
            close_missing=close_missing,
            update_prices=update_prices,
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
        )

    @bp.route("/download/<report_id>", methods=["GET"])
    def download(report_id: str):
        entry: Optional[Dict[str, str]] = REPORTS.get(report_id)
        if not entry:
            flash("Raport wygasł lub nie istnieje.", "error")
            return redirect(url_for("web.index"))
        return send_file(entry["path"], as_attachment=True, download_name=entry["filename"])

    app.register_blueprint(bp)
    return app


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    create_app().run(debug=True)
