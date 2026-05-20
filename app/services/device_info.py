"""Parse User-Agent + merge with client-provided device info.

UA-derived fields (`os`, `browser`) win over the client-provided values
to make spoofing those fields harder. Client-provided fields that the UA
can't supply (`device_model`, `app_version`, `screen_resolution`, etc.)
are kept as-is, after a defensive size/depth cap.
"""

from __future__ import annotations

from typing import Any

from ua_parser import user_agent_parser

# Fields the client may supply. Anything else is dropped.
CLIENT_ALLOWED_FIELDS = frozenset(
    {
        "device_model",
        "app_version",
        "game_version",
        "screen_resolution",
        "locale",
        "platform",
    }
)

_MAX_VALUE_LEN = 128


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    if len(s) > _MAX_VALUE_LEN:
        s = s[:_MAX_VALUE_LEN]
    return s


def parse_user_agent(ua_string: str | None) -> dict[str, Any]:
    if not ua_string:
        return {}
    parsed = user_agent_parser.Parse(ua_string)
    info: dict[str, Any] = {}
    browser = (parsed.get("user_agent") or {}).get("family")
    if browser and browser != "Other":
        info["browser"] = _safe_str(browser)
    os_family = (parsed.get("os") or {}).get("family")
    if os_family and os_family != "Other":
        info["os"] = _safe_str(os_family)
    device_family = (parsed.get("device") or {}).get("family")
    if device_family and device_family != "Other":
        info["device"] = _safe_str(device_family)
    return info


def build_device_info(
    ua_string: str | None,
    client_info: dict[str, Any] | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}

    if isinstance(client_info, dict):
        for key, value in client_info.items():
            if key not in CLIENT_ALLOWED_FIELDS:
                continue
            cleaned = _safe_str(value)
            if cleaned:
                out[key] = cleaned

    # UA-derived fields win for os/browser/device — overlay last.
    out.update(parse_user_agent(ua_string))
    return out
