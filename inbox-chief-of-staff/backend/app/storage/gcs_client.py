from __future__ import annotations

import os
import structlog
from pathlib import Path

from app.core.config import settings

logger = structlog.get_logger(__name__)

_LOCAL_FALLBACK_DIR = Path("/tmp/ics-artifacts")


class StorageClient:
    """Thin wrapper around GCS (or local filesystem for dev).

    If OBJECT_STORAGE_BUCKET is empty or APP_ENV=development, artifacts are
    written to /tmp/ics-artifacts/ instead of GCS so local dev never needs
    real credentials.
    """

    def __init__(self) -> None:
        self._bucket_name = settings.object_storage_bucket
        self._use_local = not self._bucket_name or settings.node_env == "development"

        if self._use_local:
            logger.warning(
                "storage_using_local_fallback",
                reason="OBJECT_STORAGE_BUCKET empty or node_env=development",
                path=str(_LOCAL_FALLBACK_DIR),
            )
            _LOCAL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
            self._gcs = None
        else:
            from google.cloud import storage as gcs
            self._gcs = gcs.Client()

    def _local_path(self, blob_name: str) -> Path:
        p = _LOCAL_FALLBACK_DIR / blob_name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    async def upload_artifact(
        self, blob_name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        if self._use_local:
            path = self._local_path(blob_name)
            path.write_bytes(data)
            uri = f"file://{path}"
            logger.info("artifact_uploaded_local", blob_name=blob_name, uri=uri)
            return uri

        bucket = self._gcs.bucket(self._bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data, content_type=content_type)
        uri = f"gs://{self._bucket_name}/{blob_name}"
        logger.info("artifact_uploaded_gcs", blob_name=blob_name, uri=uri)
        return uri

    async def download_artifact(self, blob_name: str) -> bytes:
        if self._use_local:
            path = self._local_path(blob_name)
            if not path.exists():
                raise FileNotFoundError(f"Local artifact not found: {path}")
            return path.read_bytes()

        bucket = self._gcs.bucket(self._bucket_name)
        blob = bucket.blob(blob_name)
        return blob.download_as_bytes()

    async def artifact_exists(self, blob_name: str) -> bool:
        if self._use_local:
            return self._local_path(blob_name).exists()

        bucket = self._gcs.bucket(self._bucket_name)
        return bucket.blob(blob_name).exists()


_storage_client: StorageClient | None = None


def get_storage_client() -> StorageClient:
    """Return the process-level singleton StorageClient."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client
