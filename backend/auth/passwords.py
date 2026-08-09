from __future__ import annotations

import hashlib
import hmac
import os

# scrypt parameters tuned for a 2026-era development box: ~100ms per hash.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32


def hash_password(password: str) -> str:
    """Hash a plaintext password with a random salt (scrypt, standard library).

    Format: ``scrypt$<salt_hex>$<derived_key_hex>``.
    """
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LEN,
    )
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification of a password against an encoded hash."""
    try:
        algorithm, salt_hex, hash_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=len(expected),
    )
    return hmac.compare_digest(derived, expected)


__all__ = ["hash_password", "verify_password"]
