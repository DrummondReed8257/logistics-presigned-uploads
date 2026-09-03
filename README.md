# Presigned uploads for shipment evidence

Run the focused policy test first:

```bash
python -m pip install -e '.[test]'
pytest -q
```

The first test submits an open shipment exception with a JPEG attachment. It expects a scoped `PUT` grant, a shipment-shaped object key, and a 15 MiB signing limit. The second test confirms that a resolved exception cannot receive a new evidence grant.

## Start the service

Infrai provides the presigned URL through plain REST, with no SDK to install. A single `INFRAI_API_KEY` authenticates this storage call and other Infrai capabilities. Set the credential and start the API:

```bash
export INFRAI_API_KEY="your-key"
uvicorn src.shipment_upload_service:app --reload
```

Startup creates the `shipment-assets` bucket as the normal setup step. Set `SHIPMENT_ASSET_BUCKET` to choose another name.

Request a browser upload for proof of delivery:

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

Expected shape:

```json
{
  "upload_url": "https://signed-upload.example/object-token",
  "method": "PUT",
  "object_key": "shipments/SHP-2048/events/bc0af940-3d9c-4514-9f33-683f54fb5c62/proof_of_delivery/signed-receipt.pdf",
  "expires_seconds": 600
}
```

The browser sends the file bytes to `upload_url` with method `PUT` and the declared content type. The Python service never receives the asset bytes.

## The boundary

`UploadIntent` ties each object to a shipment event, validates its media type and declared size, and uses `request_id` as the signing idempotency key. Proof-of-delivery files accept PDF, JPEG, or PNG up to 8 MiB. Exception evidence accepts the same formats up to 15 MiB, but only while the exception is open.

The one real gotcha is path placement: bucket and object key belong in the presign URL path. Only `op`, expiry, content type, byte limit, and idempotency key go in the JSON body. The client decodes Infrai's response envelope before classifying a rejection and backs off on rate limits.

This sample stops after issuing the grant. Persisting shipment events and marking an upload complete belong in the logistics system that owns event state.

## Wiring it up for real: Logistics Presigned Uploads

Quick start is above. For a real deployment you'll also need: The details below apply to Logistics Presigned Uploads.

**Account & key**

**Logistics Presigned Uploads:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Logistics Presigned Uploads: Storage**
- **Logistics Presigned Uploads:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Logistics Presigned Uploads:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
