"""Tests for name normalization and device info helpers."""

from __future__ import annotations

import pytest

from app.services.device_info import build_device_info, parse_user_agent
from app.services.name_normalize import InvalidPlayerNameError, normalize_player_name


class TestNormalizePlayerName:
    def test_basic_passes_through(self):
        assert normalize_player_name("RenLawrence") == "RenLawrence"

    def test_trims_whitespace(self):
        assert normalize_player_name("  Ren  ") == "Ren"

    def test_strips_zero_width(self):
        assert normalize_player_name("Re​n") == "Ren"

    def test_strips_bidi_override(self):
        # An RTL override followed by name — the override is removed.
        assert normalize_player_name("‮Ren") == "Ren"

    def test_strips_control_chars(self):
        assert normalize_player_name("Ren\x07Lawrence") == "RenLawrence"

    def test_nfc_normalization(self):
        # Decomposed "é" should normalize to a single codepoint.
        decomposed = "Rén"  # 'R','e', combining-acute, 'n' -> "Rén"
        assert normalize_player_name(decomposed) == "Rén"

    def test_empty_after_sanitization_rejected(self):
        with pytest.raises(InvalidPlayerNameError):
            normalize_player_name("​‌")

    def test_empty_input_rejected(self):
        with pytest.raises(InvalidPlayerNameError):
            normalize_player_name("")

    def test_overlong_rejected(self):
        with pytest.raises(InvalidPlayerNameError):
            normalize_player_name("a" * 33)

    def test_non_string_rejected(self):
        with pytest.raises(InvalidPlayerNameError):
            normalize_player_name(None)  # type: ignore[arg-type]


class TestDeviceInfo:
    UA_DESKTOP_CHROME = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )

    def test_parse_user_agent_extracts_browser_and_os(self):
        info = parse_user_agent(self.UA_DESKTOP_CHROME)
        assert info["browser"] == "Chrome"
        assert info["os"] == "Windows"

    def test_parse_user_agent_empty(self):
        assert parse_user_agent("") == {}
        assert parse_user_agent(None) == {}

    def test_client_fields_kept_when_allowed(self):
        info = build_device_info(
            self.UA_DESKTOP_CHROME,
            {"device_model": "Pixel 8", "app_version": "1.2.3"},
        )
        assert info["device_model"] == "Pixel 8"
        assert info["app_version"] == "1.2.3"
        assert info["browser"] == "Chrome"
        assert info["os"] == "Windows"

    def test_client_unknown_fields_dropped(self):
        info = build_device_info(
            self.UA_DESKTOP_CHROME,
            {"is_admin": True, "device_model": "Pixel 8"},
        )
        assert "is_admin" not in info
        assert info["device_model"] == "Pixel 8"

    def test_ua_os_browser_win_over_client_provided(self):
        info = build_device_info(
            self.UA_DESKTOP_CHROME,
            {"os": "Mars", "browser": "FakeBrowser", "device_model": "Pixel 8"},
        )
        # Disallowed client fields (os/browser) dropped, UA wins anyway.
        assert info["os"] == "Windows"
        assert info["browser"] == "Chrome"
        assert info["device_model"] == "Pixel 8"

    def test_value_length_clamped(self):
        long_val = "x" * 500
        info = build_device_info(None, {"device_model": long_val})
        assert len(info["device_model"]) == 128
