from app.security.passwords import (
    hash_password,
    verify_password,
    verify_password_and_update,
)


def test_password_hashing_uses_argon2id_and_verifies() -> None:
    encoded = hash_password("a sufficiently long password")

    assert encoded.startswith("$argon2id$")
    assert verify_password("a sufficiently long password", encoded)
    assert not verify_password("a different password", encoded)


def test_malformed_hash_is_rejected_without_leaking_an_exception() -> None:
    assert not verify_password("password", "not-an-encoded-hash")
    assert verify_password_and_update("password", "not-an-encoded-hash") == (
        False,
        None,
    )
