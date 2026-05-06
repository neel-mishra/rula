"""Security helpers: token encryption/decryption and session JWT signing."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import structlog
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Fernet symmetric encryption (for storing Google refresh tokens)
# ---------------------------------------------------------------------------

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazy-load and cache the Fernet instance derived from ENCRYPTION_KEY_ID.

    The ENCRYPTION_KEY_ID must be a valid URL-safe base64-encoded 32-byte key,
    or a raw string that will be padded/hashed to 32 bytes for development.
    """
    global _fernet
    if _fernet is not None:
        return _fernet

    raw_key = settings.encryption_key_id
    if not raw_key:
        # Development fallback: generate a deterministic key from SESSION_SECRET.
        # Never do this in production.
        import hashlib

        digest = hashlib.sha256(settings.session_secret.encode()).digest()
        raw_key = base64.urlsafe_b64encode(digest).decode()
        logger.warning(
            "ENCRYPTION_KEY_ID not set — using derived key. "
            "Set a proper Fernet key in production."
        )

    # Ensure proper Fernet key format (URL-safe base64, 32 bytes decoded).
    try:
        _fernet = Fernet(raw_key.encode())
    except Exception as exc:
        raise ValueError(
            "ENCRYPTION_KEY_ID is not a valid Fernet key. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc

    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt *plaintext* and return a URL-safe base64 ciphertext string."""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt *ciphertext* and return the original plaintext string.

    Raises ``cryptography.fernet.InvalidToken`` if the token is invalid or
    has been tampered with.
    """
    fernet = _get_fernet()
    return fernet.decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Session JWT tokens
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"
_SESSION_TTL_HOURS = 24 * 7  # 7 days


def create_session_token(user_id: str) -> str:
    """Create a signed JWT session token for *user_id*.

    The token encodes ``sub`` (user_id) and ``exp`` (expiry timestamp).
    """
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=_ALGORITHM)


def verify_session_token(token: str) -> str | None:
    """Verify *token* and return the ``user_id`` (``sub`` claim), or ``None``.

    Returns ``None`` on any validation failure (expired, tampered, malformed).
    """
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[_ALGORITHM])
        user_id: str | None = payload.get("sub")
        return user_id
    except JWTError:
        return None
