"""Tests for session token issuance + consumption."""

from __future__ import annotations

import time

import fakeredis
import pytest
from freezegun import freeze_time

from app.services import session_tokens as st

SECRET = "test-secret-do-not-use" * 2
TTL = 60


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def test_issue_returns_token_and_stores_nonce(r):
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    assert issued.game_id == 42
    assert issued.token
    assert r.exists(st.NONCE_KEY_PREFIX + issued.nonce) == 1


def test_verify_and_consume_happy_path(r):
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    payload = st.verify_and_consume(
        secret_key=SECRET,
        token=issued.token,
        expected_game_id=42,
        redis_client=r,
        max_age_seconds=TTL,
    )
    assert payload["gid"] == 42
    # Nonce was consumed.
    assert r.exists(st.NONCE_KEY_PREFIX + issued.nonce) == 0


def test_replay_after_consume_rejected(r):
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    st.verify_and_consume(
        secret_key=SECRET,
        token=issued.token,
        expected_game_id=42,
        redis_client=r,
        max_age_seconds=TTL,
    )
    with pytest.raises(st.InvalidSessionTokenError):
        st.verify_and_consume(
            secret_key=SECRET,
            token=issued.token,
            expected_game_id=42,
            redis_client=r,
            max_age_seconds=TTL,
        )


def test_wrong_game_id_rejected(r):
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    with pytest.raises(st.InvalidSessionTokenError):
        st.verify_and_consume(
            secret_key=SECRET,
            token=issued.token,
            expected_game_id=7,
            redis_client=r,
            max_age_seconds=TTL,
        )
    # Nonce must NOT have been consumed on rejection.
    assert r.exists(st.NONCE_KEY_PREFIX + issued.nonce) == 1


def test_tampered_token_rejected(r):
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    tampered = issued.token[:-2] + ("AA" if not issued.token.endswith("AA") else "BB")
    with pytest.raises(st.InvalidSessionTokenError):
        st.verify_and_consume(
            secret_key=SECRET,
            token=tampered,
            expected_game_id=42,
            redis_client=r,
            max_age_seconds=TTL,
        )


def test_wrong_secret_key_rejected(r):
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    with pytest.raises(st.InvalidSessionTokenError):
        st.verify_and_consume(
            secret_key="some-other-secret-key",
            token=issued.token,
            expected_game_id=42,
            redis_client=r,
            max_age_seconds=TTL,
        )


def test_expired_token_rejected(r):
    with freeze_time("2026-05-20 12:00:00"):
        issued = st.issue_token(
            secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
        )
    # Two hours later, max_age=60s -> SignatureExpired.
    with freeze_time("2026-05-20 14:00:00"):
        with pytest.raises(st.InvalidSessionTokenError):
            st.verify_and_consume(
                secret_key=SECRET,
                token=issued.token,
                expected_game_id=42,
                redis_client=r,
                max_age_seconds=60,
            )


def test_expired_nonce_rejected(r):
    # Issue a token with TTL 1s, then drop the nonce manually to simulate TTL.
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    r.delete(st.NONCE_KEY_PREFIX + issued.nonce)
    with pytest.raises(st.InvalidSessionTokenError):
        st.verify_and_consume(
            secret_key=SECRET,
            token=issued.token,
            expected_game_id=42,
            redis_client=r,
            max_age_seconds=TTL,
        )


def test_token_fingerprint_is_stable_and_safe(r):
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    fp = st.token_fingerprint(issued.token)
    assert len(fp) == 12
    assert all(c in "0123456789abcdef" for c in fp)
    # Stable: same input -> same output.
    assert fp == st.token_fingerprint(issued.token)


def test_issued_at_from_token(r):
    before = int(time.time())
    issued = st.issue_token(
        secret_key=SECRET, game_id=42, redis_client=r, ttl_seconds=TTL
    )
    ts = st.issued_at_from_token(secret_key=SECRET, token=issued.token)
    after = int(time.time())
    assert ts is not None
    assert before - 1 <= ts <= after + 1


def test_issued_at_returns_none_on_bad_signature(r):
    assert st.issued_at_from_token(secret_key=SECRET, token="garbage.nope.nope") is None
