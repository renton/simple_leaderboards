"""Normalize and validate submitted player names.

Strategy:
- NFC normalize (so canonically-equivalent codepoints compare equal).
- Strip control characters (cat = Cc/Cf), bidi-override codepoints, and
  zero-width / format codepoints — these are useless for a display name
  and are common abuse vectors (RTL overrides, ZWJ-stuffed homoglyphs).
- Trim leading/trailing whitespace.
- Cap length by grapheme-cluster-ish count (we approximate with NFC code
  points; for v1 this is good enough — anyone bypassing it with a 1-char
  combining-mark stream still hits the byte/codepoint limit hard).

Returns the cleaned name, or raises InvalidPlayerNameError.
"""

from __future__ import annotations

import unicodedata

MIN_LEN = 1
MAX_LEN = 32

# Codepoints we strip even if they survive NFC normalization.
# - Bidi overrides: U+202A..U+202E, U+2066..U+2069
# - Zero-width: U+200B..U+200D, U+FEFF
# - Soft-hyphen: U+00AD
_STRIP_CHARS = (
    "‪‫‬‭‮"
    "⁦⁧⁨⁩"
    "​‌‍﻿"
    "­"
)


class InvalidPlayerNameError(ValueError):
    """Raised when a submitted player name cannot be made safe."""


def normalize_player_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise InvalidPlayerNameError("player_name must be a string")

    nfc = unicodedata.normalize("NFC", raw)
    # Remove specific abuse codepoints.
    nfc = nfc.translate({ord(c): None for c in _STRIP_CHARS})
    # Remove all control / format characters.
    cleaned = "".join(c for c in nfc if unicodedata.category(c) not in {"Cc", "Cf"})
    cleaned = cleaned.strip()

    if len(cleaned) < MIN_LEN:
        raise InvalidPlayerNameError("player_name is empty after sanitization")
    if len(cleaned) > MAX_LEN:
        raise InvalidPlayerNameError(f"player_name exceeds {MAX_LEN} characters")
    return cleaned
