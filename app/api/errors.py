"""Stable JSON error responses for the public API."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

# Stable error codes. Keep this list in docs/api.md in sync.
ERROR_CODES = {
    "invalid_request": 400,
    "invalid_session": 401,
    "rate_limited": 429,
    "game_not_found": 404,
    "score_out_of_bounds": 400,
    "invalid_player_name": 400,
    "invalid_seed": 400,
    "invalid_custom_data": 400,
    "invalid_played_at": 400,
    "method_not_allowed": 405,
    "payload_too_large": 413,
    "internal_error": 500,
}


class ApiError(Exception):
    def __init__(self, code: str, detail: str | None = None, status: int | None = None) -> None:
        self.code = code
        self.detail = detail
        self.status = status or ERROR_CODES.get(code, 400)
        super().__init__(detail or code)


def api_error_response(code: str, detail: str | None = None, status: int | None = None):
    status = status or ERROR_CODES.get(code, 400)
    payload: dict[str, Any] = {"error": code}
    if detail:
        payload["detail"] = detail
    return jsonify(payload), status


def register_api_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_err(e: ApiError):
        return api_error_response(e.code, e.detail, e.status)

    @app.errorhandler(413)
    def _too_large(_e):
        # Only return JSON for API paths; let Flask render HTML elsewhere.
        from flask import request

        if request.path.startswith("/api/"):
            return api_error_response("payload_too_large", status=413)
        return _e  # default handler

    @app.errorhandler(429)
    def _rate_limited(_e):
        from flask import request

        if request.path.startswith("/api/"):
            return api_error_response("rate_limited", status=429)
        return _e

    @app.errorhandler(HTTPException)
    def _http(e: HTTPException):
        from flask import request

        if request.path.startswith("/api/"):
            code_by_status = {
                400: "invalid_request",
                401: "invalid_session",
                404: "game_not_found" if "game" in (e.description or "").lower() else "invalid_request",
                405: "method_not_allowed",
                413: "payload_too_large",
                429: "rate_limited",
            }
            code = code_by_status.get(e.code, "invalid_request")
            return api_error_response(code, status=e.code)
        return e
