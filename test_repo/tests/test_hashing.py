"""Hidden FAIL_TO_PASS tests for security.hashing.needs_rehash.

The agent must make needs_rehash flag hashes that do not use the current
salted (salt:hash) format so legacy unsalted hashes get upgraded.
"""

from security.hashing import hash_password, needs_rehash


def test_fresh_hash_does_not_need_rehash() -> None:
    assert needs_rehash(hash_password("secret")) is False


def test_unsalted_hash_needs_rehash() -> None:
    assert needs_rehash("plain-sha256-without-separator") is True


def test_short_salt_hash_needs_rehash() -> None:
    # Current salts are secrets.token_hex(16) == 32 chars.
    assert needs_rehash("short:hash") is True


def test_empty_value_needs_rehash() -> None:
    assert needs_rehash("") is True
