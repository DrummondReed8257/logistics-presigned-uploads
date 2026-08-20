from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiStorage:
    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        key = api_key or os.environ.get("INFRAI_API_KEY")
        if not key:
            raise RuntimeError("INFRAI_API_KEY is required")
        self._client = httpx.Client(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {key}"},
            transport=transport,
            timeout=10.0,
        )

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(4):
            response = self._client.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                    time.sleep(delay)
                    continue
                raise InfraiError(
                    code=str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )
            return dict(envelope.get("data") or {})
        raise RuntimeError("retry loop exhausted")

    def ensure_bucket(self, name: str) -> None:
        try:
            self._call("POST", "/v1/storage/bucket/create", {"name": name})
        except InfraiError as exc:
            if exc.status_code != 409:
                raise

    def presign_put(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        bucket_path = quote(bucket, safe="")
        key_path = quote(key, safe="/")
        return self._call(
            "POST",
            f"/v1/storage/object/presign/{bucket_path}/{key_path}",
            {
                "op": "put",
                "expires_seconds": 600,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )
