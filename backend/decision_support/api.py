"""Local evaluation API; no release downloads, credentials, or training on import."""

import argparse
import os
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
import joblib

from .model import compare_options, SCHEMA_VERSION
from .train import DEFAULT_OUTPUT
from .dashboard import register_dashboard
from .train import DEFAULT_DATA
from ..request_logging import install_request_logging


def create_app(model_path=None, *, bundle=None, db_path=None, data_dir=None):
    app = Flask(__name__)
    origins = os.environ.get("DIGITALOC_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    CORS(app, origins=origins, expose_headers=["X-Request-ID"])
    if bundle is None:
        path = Path(model_path) if model_path else DEFAULT_OUTPUT / "baseline.joblib"
        if path.exists():
            bundle = joblib.load(path)
    if bundle is not None and bundle.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported model schema")
    install_request_logging(app, {"outcome_model": bundle.get("model_id", "local") if bundle else "unavailable"})
    register_dashboard(app, bundle,
                       db_path or os.environ.get("DIGITALOC_DB_PATH") or Path(__file__).resolve().parents[1] / "instance" / "digitaloc.sqlite",
                       data_dir or DEFAULT_DATA)

    @app.get("/health")
    def health():
        return jsonify({"model_ready": bundle is not None, "status": "experimental"}), 200 if bundle else 503

    @app.post("/evaluateOptions")
    def evaluate_options():
        if bundle is None:
            return jsonify({"error": "Train the local baseline before requesting comparisons"}), 503
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Expected a JSON object"}), 400
        if set(data) - {"current_situation", "allowed_actions"}:
            return jsonify({"error": "Supported fields are current_situation and allowed_actions"}), 400
        try:
            result = compare_options(bundle, data.get("current_situation"), data.get("allowed_actions"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(result)

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_OUTPUT / "baseline.joblib")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    create_app(args.model).run(host="127.0.0.1", port=args.port, debug=False)
