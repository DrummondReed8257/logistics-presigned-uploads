from __future__ import annotations

import os
from contextlib import asynccontextmanager
from enum import Enum
from typing import Iterator
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .infrai_storage import InfraiError, InfraiStorage


class EventState(str, Enum):
    delivered = "delivered"
    exception_open = "exception_open"
    exception_resolved = "exception_resolved"


class AssetKind(str, Enum):
    proof_of_delivery = "proof_of_delivery"
    exception_evidence = "exception_evidence"


class UploadIntent(BaseModel):
    shipment_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    event_id: UUID
    event_state: EventState
    asset_kind: AssetKind
    filename: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    content_type: str
    size_bytes: int = Field(gt=0)
    request_id: UUID


class UploadGrant(BaseModel):
    upload_url: str
    method: str
    object_key: str
    expires_seconds: int


BUCKET = os.environ.get("SHIPMENT_ASSET_BUCKET", "shipment-assets")
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_BYTES = {
    AssetKind.proof_of_delivery: 8 * 1024 * 1024,
    AssetKind.exception_evidence: 15 * 1024 * 1024,
}


def validate_upload(intent: UploadIntent) -> int:
    if intent.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail="asset type must be PDF, JPEG, or PNG")
    if intent.asset_kind == AssetKind.exception_evidence and intent.event_state != EventState.exception_open:
        raise HTTPException(status_code=409, detail="exception evidence requires an open exception event")
    limit = MAX_BYTES[intent.asset_kind]
    if intent.size_bytes > limit:
        raise HTTPException(status_code=413, detail=f"asset exceeds {limit} bytes")
    return limit


def get_signer() -> Iterator[InfraiStorage]:
    signer = InfraiStorage()
    try:
        yield signer
    finally:
        signer.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    signer = InfraiStorage()
    try:
        signer.ensure_bucket(BUCKET)
    finally:
        signer.close()
    yield


app = FastAPI(title="Shipment asset upload grants", lifespan=lifespan)


@app.post("/shipment-events/upload-intents", response_model=UploadGrant)
def create_upload_intent(intent: UploadIntent, signer: InfraiStorage = Depends(get_signer)) -> UploadGrant:
    max_bytes = validate_upload(intent)
    object_key = f"shipments/{intent.shipment_id}/events/{intent.event_id}/{intent.asset_kind.value}/{intent.filename}"
    try:
        result = signer.presign_put(
            BUCKET,
            object_key,
            content_type=intent.content_type,
            max_bytes=max_bytes,
            idempotency_key=str(intent.request_id),
        )
    except InfraiError as exc:
        caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=caller_status, detail={"code": exc.code, "message": str(exc)}) from exc
    return UploadGrant(
        upload_url=str(result["url"]),
        method="PUT",
        object_key=object_key,
        expires_seconds=600,
    )
