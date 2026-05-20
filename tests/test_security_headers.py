"""Tests for hardening response headers and payload-size limits."""

from __future__ import annotations


def test_csp_header_is_set(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy")
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_no_sniff_header(client):
    resp = client.get("/healthz")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_clickjacking_protection(client):
    resp = client.get("/healthz")
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_referrer_policy(client):
    resp = client.get("/healthz")
    assert resp.headers.get("Referrer-Policy") == "no-referrer"


def test_oversized_payload_rejected(client, make_game):
    g = make_game()
    # Build a payload comfortably over MAX_CONTENT_LENGTH (4096 bytes).
    big_name = "x" * 8000
    resp = client.post(
        "/api/v1/sessions",
        json={"game": g.slug, "client_info": {"junk": big_name}},
    )
    assert resp.status_code == 413
    assert resp.get_json()["error"] == "payload_too_large"
