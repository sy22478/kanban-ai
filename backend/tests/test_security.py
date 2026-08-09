"""The primitives underneath auth.

One test per property rather than one test asserting five things, per the lesson
logged on 2026-08-01: a check that names several behaviours and exercises one of
them reads like full coverage and is not.

No database here. These are pure functions.
"""

import base64
import statistics
import time

import pytest
from pwdlib.exceptions import UnknownHashError

from app.security import (
    DUMMY_HASH,
    hash_password,
    new_session_token,
    token_digest,
    verify_password,
)


def test_hash_is_argon2id_above_the_owasp_floor():
    _, algorithm, _version, params, _salt, _digest = hash_password("correct horse").split("$")
    values = dict(pair.split("=") for pair in params.split(","))

    assert algorithm == "argon2id"
    # OWASP: minimum 19 MiB, t=2, p=1.
    assert int(values["m"]) >= 19 * 1024
    assert int(values["t"]) >= 2
    assert int(values["p"]) >= 1


def test_the_password_is_not_recoverable_from_the_hash():
    password = "correct horse battery staple"

    stored = hash_password(password)

    assert password not in stored


def test_the_same_password_hashes_differently_each_time():
    """Distinct salts. Two users with the same password must not collide in a
    way that lets a stolen database be cracked once and used twice."""
    assert hash_password("same") != hash_password("same")


def test_the_right_password_verifies():
    ok, rehashed = verify_password("right", hash_password("right"))

    assert ok is True
    # Nothing to update: it was just hashed with the current parameters.
    assert rehashed is None


def test_the_wrong_password_does_not_verify():
    ok, _rehashed = verify_password("wrong", hash_password("right"))

    assert ok is False


def test_an_outdated_hash_is_reported_for_rehashing():
    """The mechanism that lets the cost parameters be raised later without
    knowing anyone's password."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    weak = PasswordHash((Argon2Hasher(memory_cost=19 * 1024, time_cost=2, parallelism=1),))
    old_hash = weak.hash("right")

    ok, rehashed = verify_password("right", old_hash)

    assert ok is True
    assert rehashed is not None
    assert rehashed != old_hash
    # The replacement is at the current, higher cost.
    assert "m=65536" in rehashed


def test_verifying_against_the_dummy_hash_returns_false_rather_than_raising():
    """The property the no-such-user path depends on. If this raised, login
    would answer 500 for an unknown address and 401 for a wrong password, which
    is the enumeration leak the dummy hash exists to close."""
    ok, _rehashed = verify_password("anything at all", DUMMY_HASH)

    assert ok is False


def test_a_sentinel_would_have_raised():
    """Why DUMMY_HASH is a real Argon2 hash and not "" or "x". This is the
    failure the test above is guarding against, shown rather than asserted."""
    with pytest.raises(UnknownHashError):
        verify_password("anything at all", "")


def test_no_such_user_costs_the_same_as_a_wrong_password():
    """The dummy hash exists to flatten timing, so timing is what gets measured.

    Medians of several runs, because a single sample on a container is noise.
    The bound is deliberately loose: the claim is same order of magnitude, which
    is what defeats a remote attacker, not identical nanoseconds.
    """
    real_hash = hash_password("the real password")

    def median_ms(password_hash):
        samples = []
        for _ in range(7):
            start = time.perf_counter()
            verify_password("guess", password_hash)
            samples.append((time.perf_counter() - start) * 1000)
        return statistics.median(samples)

    real = median_ms(real_hash)
    absent = median_ms(DUMMY_HASH)

    assert 0.5 < absent / real < 2.0, f"real {real:.1f}ms vs no-such-user {absent:.1f}ms"


def test_session_tokens_are_unique():
    assert len({new_session_token() for _ in range(100)}) == 100


def test_a_session_token_carries_256_bits():
    token = new_session_token()

    # token_urlsafe strips base64 padding, so it goes back on to decode.
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))

    assert len(raw) == 32


def test_the_digest_is_32_bytes_and_stable():
    token = new_session_token()

    assert len(token_digest(token)) == 32
    assert token_digest(token) == token_digest(token)


def test_the_digest_does_not_contain_the_token():
    """What makes a leaked sessions table useless for logging in."""
    token = new_session_token()

    assert token.encode() not in token_digest(token)


def test_different_tokens_digest_differently():
    assert token_digest(new_session_token()) != token_digest(new_session_token())
