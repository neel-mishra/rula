"""
Token encryption — envelope encryption for OAuth refresh tokens.
Production: AWS KMS CMK via boto3.
Dev/test: local Fernet symmetric key from TOKEN_ENCRYPTION_KEY env var.
"""

from __future__ import annotations

import base64
import os
from typing import Protocol

import structlog
from cryptography.fernet import Fernet

from core.config import settings

log = structlog.get_logger(__name__)


class TokenEncryptor(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...


class FernetEncryptor:
    """Local symmetric encryption for dev/test. Never use in prod."""

    def __init__(self, key: str) -> None:
        raw = base64.b64decode(key) if not key.startswith("CHANGE") else None
        if raw is None:
            # Generate a dev-only key if placeholder not replaced
            raw = Fernet.generate_key()
            log.warning("Using auto-generated dev encryption key — not suitable for production")
        self._fernet = Fernet(raw if len(raw) == 44 else base64.urlsafe_b64encode(raw[:32]))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()


class KMSEncryptor:
    """AWS KMS envelope encryption. Used in staging/prod."""

    def __init__(self, key_arn: str, region: str) -> None:
        import boto3
        self._client = boto3.client("kms", region_name=region)
        self._key_arn = key_arn

    def encrypt(self, plaintext: str) -> str:
        response = self._client.encrypt(
            KeyId=self._key_arn,
            Plaintext=plaintext.encode(),
        )
        return base64.b64encode(response["CiphertextBlob"]).decode()

    def decrypt(self, ciphertext: str) -> str:
        blob = base64.b64decode(ciphertext)
        response = self._client.decrypt(CiphertextBlob=blob)
        return response["Plaintext"].decode()


def get_encryptor() -> TokenEncryptor:
    """Factory: returns KMS encryptor in prod/staging, Fernet otherwise."""
    if settings.is_production and settings.kms_key_arn and not settings.kms_key_arn.startswith(
        "arn:aws:kms:us-east-1:123456789012"
    ):
        return KMSEncryptor(key_arn=settings.kms_key_arn, region=settings.aws_region)
    return FernetEncryptor(key=settings.token_encryption_key)


# Module-level singleton
_encryptor: TokenEncryptor | None = None


def encrypt_token(token: str) -> str:
    global _encryptor
    if _encryptor is None:
        _encryptor = get_encryptor()
    return _encryptor.encrypt(token)


def decrypt_token(ciphertext: str) -> str:
    global _encryptor
    if _encryptor is None:
        _encryptor = get_encryptor()
    return _encryptor.decrypt(ciphertext)
