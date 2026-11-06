from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

password_hasher = PasswordHash([Argon2Hasher()])


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except (UnknownHashError, ValueError, TypeError):
        return False


def verify_password_and_update(
    password: str, password_hash: str
) -> tuple[bool, str | None]:
    try:
        return password_hasher.verify_and_update(password, password_hash)
    except (UnknownHashError, ValueError, TypeError):
        return False, None
