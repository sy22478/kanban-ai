"""Password hashing and session tokens.

Two different problems that both look like "hash a thing", solved differently on
purpose:

- A **password** is low entropy and chosen by a human, so an attacker who steals
  the database can guess it. That needs a slow, memory-hard hash. Argon2id at
  64 MiB makes each guess expensive.
- A **session token** is 256 bits from the operating system's CSPRNG. There is
  nothing to guess, so there is nothing for a slow hash to slow down. sha256 is
  correct, and using Argon2 here would add real latency to every single request
  in exchange for no security at all.

Getting these the wrong way round is the classic error in both directions:
sha256 on passwords, or Argon2 on tokens.
"""

import hashlib
import secrets

from pwdlib import PasswordHash

# Argon2id at m=65536 KiB (64 MiB), t=3, p=4, which is above the OWASP floor of
# 19 MiB / t=2 / p=1. Not passlib, which last shipped in 2020 and imports the
# stdlib crypt module that Python 3.13 removed. Not bcrypt, which OWASP now
# restricts to legacy systems.
_hasher = PasswordHash.recommended()

# Hashed against when no such user exists, so that the work done on a login
# attempt does not depend on whether the account is real. Without this the
# no-such-user path returns in microseconds while a real one takes ~50ms, and
# that difference is a user-enumeration oracle no matter how carefully the
# response body is made identical.
#
# It is a genuine Argon2id hash of a random string that is discarded, rather than
# a sentinel like "" or "x". pwdlib raises UnknownHashError on anything it cannot
# parse, so a sentinel would make the no-such-user path a 500 while a wrong
# password stayed a 401 -- the same oracle, wearing a different hat.
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Hash a password for storage. The result carries its own parameters."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Check a password, and say whether the stored hash is now out of date.

    Returns (ok, new_hash_or_none). The second value is not None when the hash
    was made with older parameters than the current recommendation, which is how
    a future cost increase rolls out: each user's hash is upgraded the next time
    they log in, without anyone needing to know their password.

    UnknownHashError is deliberately not caught. password_hash is NOT NULL and is
    only ever written by hash_password, so an unparseable value means the row was
    corrupted or written by something outside this application. That is a bug I
    want to see, not one to swallow into a silent authentication failure.
    """
    return _hasher.verify_and_update(password, password_hash)


def new_session_token() -> str:
    """A fresh session token: 32 bytes from the OS CSPRNG, URL-safe base64.

    256 bits, so brute force is not a threat model. This is the value that goes
    in the cookie and it is never stored anywhere.
    """
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> bytes:
    """The 32 raw bytes stored in sessions.token_hash.

    Storing the digest rather than the token means a database leak does not hand
    over live sessions: the attacker has the hash and cannot reverse it into the
    cookie value. It is the same reason passwords are not stored in the clear,
    reached by a different route.
    """
    return hashlib.sha256(token.encode()).digest()
