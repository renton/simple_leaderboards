"""Seed derivation for daily-challenge leaderboards.

Daily seeds are produced by the game client (GDScript) as:

    seed = str(hash("YYYY-MM-DD"))   # date in US Eastern time

GDScript's built-in hash() on a String uses Godot's DJB2-XOR variant:
  h = 5381
  for each UTF-32 code point c:
      h = ((h << 5) + h) ^ c   (uint32 arithmetic)
  return h

For ASCII date strings every code point equals the ASCII byte value, so
this is straightforward to replicate.  The result is a uint32 stored as a
plain decimal string (e.g. "3421789012").
"""

from __future__ import annotations

import re

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def godot_string_hash(s: str) -> int:
    """DJB2-add matching GDScript's hash() for ASCII strings. Returns uint32."""
    h = 5381
    for c in s:
        h = (h * 33 + ord(c)) & 0xFFFFFFFF
    return h


def date_to_seed(date_str: str) -> str:
    """Return the decimal seed string for a YYYY-MM-DD date."""
    return str(godot_string_hash(date_str))


def looks_like_date(value: str) -> bool:
    return bool(_DATE_RE.match(value))
