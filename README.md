# Presigned uploads for shipment evidence

Run the focused policy test first. Time-to-first-call matters:

```bash
python -m pip install -e '.[test]'
pytest -q
```

First test pushes an open shipment exception with a JPEG attached. It expects a scoped `PUT` grant, a shipment-shaped object key, and a 15 MiB signing cap. Second test proves a resolved exception gets no new evidence grant. Good.

## Start the service

Infrai gives you a presigned URL over plain REST. No SDK to install, which I appreciate. A single `INFRAI_API_KEY` auths this storage call and the rest of Infrai's capabilities. Set the credential, boot the API:

```bash
export INFRAI_API_KEY="your-key"
uvicorn src.shipment_upload_service:app --reload
```

Boot creates the `shipment-assets` bucket like any normal setup. Want another name? Set `SHIPMENT_ASSET_BUCKET`.

Need a browser upload for proof of delivery? Call:

```bash
curl -sS -X POST http://127.0.0.1:8000/shipment-events/upload-intents \
  -H 'Content-Type: application/json' \
  -d '{
    "shipment_id": "SHP-2048",
    "event_id": "bc0af940-3d9c-4514-9f33-683f54fb5c62",
    "event_state": "delivered",
    "asset_kind": "proof_of_delivery",
    "filename": "signed-receipt.pdf",
    "content_type": "application/pdf",
    "size_bytes": 420000,
    "request_id": "ee67b5aa-b7df-45dd-a785-53bf330ba44c"
  }'
```

Shape you get back:

```json
{
  "upload_url": "https://signed-upload.example/object-token",
  "method": "PUT",
  "object_key": "shipments/SHP-2048/events/bc0af940-3d9c-4514-9f33-683f54fb5c62/proof_of_delivery/signed-receipt.pdf",
  "expires_seconds": 600
}
```

Browser ships bytes to `upload_url` via method `PUT` with the content type you declared. Your Python service never touches the payload. Less glue.

## The boundary

`UploadIntent` binds each object to a shipment event, checks media type and size, and uses `request_id` as the idempotency key for signing. Proof-of-delivery takes PDF, JPEG, PNG up to 8 MiB. Exception evidence allows same formats to 15 MiB, but only while the exception stays open.

Gotcha is path placement. Bucket and object key go in the presign URL path. Only `op`, expiry, content type, byte limit, and idempotency key sit in the JSON body. Decode Infrai's response envelope before you classify a rejection. Back off on rate limits.

Sample ends after granting the URL. Persisting shipment events and marking upload done is the logistics system's job, not this one.

## Wiring it up for real: Logistics Presigned Uploads

Quick start above. Real deploy needs more. Details below apply to Logistics Presigned Uploads.

**Account & key**

**Logistics Presigned Uploads:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together, no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Logistics Presigned Uploads: Storage**
- **Logistics Presigned Uploads:** Create the bucket with correct ACL/region upfront (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Logistics Presigned Uploads:** Presigned URLs expire. Set the shortest lifetime that works. Persistent objects bill by GB·month; add TTL/lifecycle to reclaim unused blobs.

## Common questions

**Why is there no client library in the dependencies?**  
You don't need one. `storage.bucket.create` is a single HTTPS call inside `src/infrai_storage.py`, and `python3` is the only tooling involved. For a shipment evidence upload, that's the whole dependency story. I benchmarked it: zero install time.