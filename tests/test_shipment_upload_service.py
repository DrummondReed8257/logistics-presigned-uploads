from uuid import UUID

from fastapi.testclient import TestClient

from src.shipment_upload_service import app, get_signer


class RecordingSigner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def ensure_bucket(self, name: str) -> None:
        return None

    def presign_put(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        self.calls.append({"bucket": bucket, "key": key, "max_bytes": max_bytes, "idempotency_key": idempotency_key})
        return {"url": "https://uploads.example/signed"}


def test_open_exception_event_receives_scoped_put_grant() -> None:
    signer = RecordingSigner()
    app.dependency_overrides[get_signer] = lambda: signer
    request_id = "ee67b5aa-b7df-45dd-a785-53bf330ba44c"
    event_id = "bc0af940-3d9c-4514-9f33-683f54fb5c62"

    response = TestClient(app).post(
        "/shipment-events/upload-intents",
        json={
            "shipment_id": "SHP-2048",
            "event_id": event_id,
            "event_state": "exception_open",
            "asset_kind": "exception_evidence",
            "filename": "damaged-carton.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 2_000_000,
            "request_id": request_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["method"] == "PUT"
    assert response.json()["object_key"].startswith(f"shipments/SHP-2048/events/{event_id}/")
    assert signer.calls[0]["idempotency_key"] == request_id  # type: ignore[attr-defined]
    assert signer.calls[0]["max_bytes"] == 15 * 1024 * 1024  # type: ignore[attr-defined]
    app.dependency_overrides.clear()


def test_resolved_exception_cannot_add_evidence() -> None:
    signer = RecordingSigner()
    app.dependency_overrides[get_signer] = lambda: signer
    response = TestClient(app).post(
        "/shipment-events/upload-intents",
        json={
            "shipment_id": "SHP-2048",
            "event_id": str(UUID(int=1)),
            "event_state": "exception_resolved",
            "asset_kind": "exception_evidence",
            "filename": "late-photo.png",
            "content_type": "image/png",
            "size_bytes": 4000,
            "request_id": str(UUID(int=2)),
        },
    )

    assert response.status_code == 409
    assert signer.calls == []
    app.dependency_overrides.clear()
