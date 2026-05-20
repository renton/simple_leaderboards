"""Install hardening response headers."""

from __future__ import annotations

from flask import Flask, Response


def install_security_headers(app: Flask) -> None:
    @app.after_request
    def _set_headers(response: Response) -> Response:
        csp = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self'; "
            "script-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        return response
