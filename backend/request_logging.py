"""One JSON completion record per HTTP request, correlated with Chrome headers."""

import json
import logging
import time
import uuid

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException


def install_request_logging(app, model_versions):
    logger = logging.getLogger("digitaloc.requests")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = False

    @app.before_request
    def start_request():
        g.request_id = uuid.uuid4().hex
        g.request_started = time.perf_counter()

    @app.errorhandler(Exception)
    def request_error(error):
        status = error.code if isinstance(error, HTTPException) else 500
        g.request_error_type = type(error).__name__
        if status == 500:
            logger.exception(json.dumps({"event": "request_error", "request_id": g.request_id,
                                         "error_type": type(error).__name__}))
        message = error.description if isinstance(error, HTTPException) else "Unable to generate suggestions"
        return jsonify({"error": message, "request_id": g.request_id}), status

    @app.after_request
    def finish_request(response):
        response.headers["X-Request-ID"] = g.request_id
        payload = response.get_json(silent=True) if response.is_json else None
        logger.info(json.dumps({
            "event": "request_completed", "request_id": g.request_id,
            "method": request.method, "path": request.path, "status": response.status_code,
            "duration_ms": round((time.perf_counter() - g.request_started) * 1000, 2),
            "model_versions": model_versions,
            "session_id": getattr(g, "session_id", None),
            "session_revision": getattr(g, "session_revision", None),
            "processed_situation": getattr(g, "processed_situation", None),
            "history_length": getattr(g, "history_length", None),
            "model_inputs": getattr(g, "model_inputs", []),
            "error_type": getattr(g, "request_error_type", None),
            "play_type": payload.get("play_type") if isinstance(payload, dict) else None,
            "play_count": len(payload.get("plays", [])) if isinstance(payload, dict) else None,
        }, allow_nan=False))
        return response
