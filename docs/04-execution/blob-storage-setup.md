# Blob Storage — Setup Guide

Practical configuration guide for Leer blob storage backends.

For the design rationale and permanent spec, see `docs/03-specs/platform/blob-storage.md`.

---

## Overview

Leer uses a hybrid storage model:

- **Small payloads** stay inline in PostgreSQL.
- **Large payloads** are offloaded to blob storage, with PostgreSQL storing only a reference, preview text, and metadata.

The backend is selected through a single environment variable. All artifact semantics — API shape and UI behavior — remain identical regardless of backend.

---

## Choosing a Backend

| Backend | When to use |
|---------|-------------|
| `local` | Local development, single-node testing, CI |
| `s3` | Production on AWS |
| `azure` | Production on Azure |

The `local` backend is the default. It requires no additional dependencies or cloud accounts.

---

## Inline Threshold

The threshold determines when payloads are offloaded to blob storage.

| Setting | Default | Behavior |
|---------|---------|----------|
| `BLOB_INLINE_THRESHOLD_BYTES` | `262144` (256 KB) | Payloads at or below this size stay inline. Payloads strictly above this size are written to blob storage. |

The threshold is applied to the serialized JSON payload size in bytes. It is enforced uniformly across all artifact types during ingestion.

---

## Local Dev Setup

No additional dependencies or configuration required. The defaults work out of the box.

```env
# .env (these are the defaults — you can omit them)
BLOB_BACKEND=local
BLOB_LOCAL_ROOT=.leer/blobs
BLOB_INLINE_THRESHOLD_BYTES=262144
```

Blob files are written to the `BLOB_LOCAL_ROOT` directory relative to the API working directory. The directory is created automatically on first use.

The local backend is not suitable for multi-instance production deployments — each instance would have its own local filesystem.

---

## S3 Setup

### 1. Install the SDK

```bash
pip install boto3
```

`boto3` is an optional dependency. It is only imported when `BLOB_BACKEND=s3`.

### 2. Create a bucket

The S3 bucket must already exist. Leer does not create buckets.

### 3. Configure

```env
BLOB_BACKEND=s3
BLOB_S3_BUCKET=leer-artifacts-prod
BLOB_S3_REGION=eu-west-1
BLOB_S3_PREFIX=artifacts/
BLOB_INLINE_THRESHOLD_BYTES=262144
```

| Setting | Required | Default | Notes |
|---------|----------|---------|-------|
| `BLOB_S3_BUCKET` | yes | — | Bucket name |
| `BLOB_S3_REGION` | no | — | Passed to the boto3 client; omit to use SDK default |
| `BLOB_S3_PREFIX` | no | `""` | Prepended to all object keys; useful for sharing a bucket |

### 4. Authentication

Leer uses the standard boto3 credential chain. It does not accept AWS access keys as Leer-specific settings.

| Environment | Recommended auth |
|-------------|-----------------|
| Local dev | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars, or `aws sso login` |
| EC2 / ECS | IAM instance role or ECS task role |
| EKS | IAM Roles for Service Accounts (IRSA) |

**Production recommendation:** Use IAM roles. Do not use long-lived access keys in production.

### Operational notes

- Object keys follow the pattern: `{prefix}projects/{project_id}/runs/{run_id}/artifacts/{artifact_id}.json`
- `blob_path` in the database stores the logical key (without prefix). The adapter prepends the prefix at read/write time.
- S3 provides strong read-after-write consistency.
- `delete` uses S3's idempotent semantics — deleting a nonexistent key does not error.

---

## Azure Setup

### 1. Install the SDKs

```bash
pip install azure-storage-blob azure-identity
```

Both packages are optional dependencies. They are only imported when `BLOB_BACKEND=azure`.

### 2. Create a container

The Azure Blob Storage container must already exist. Leer does not create containers.

### 3. Configure

**Using a connection string (simpler, good for dev):**

```env
BLOB_BACKEND=azure
BLOB_AZURE_CONTAINER=leer-artifacts
BLOB_AZURE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey=...
BLOB_AZURE_PREFIX=artifacts/
BLOB_INLINE_THRESHOLD_BYTES=262144
```

**Using account URL + DefaultAzureCredential (production):**

```env
BLOB_BACKEND=azure
BLOB_AZURE_CONTAINER=leer-artifacts
BLOB_AZURE_ACCOUNT_URL=https://myaccount.blob.core.windows.net
BLOB_AZURE_PREFIX=artifacts/
BLOB_INLINE_THRESHOLD_BYTES=262144
```

| Setting | Required | Default | Notes |
|---------|----------|---------|-------|
| `BLOB_AZURE_CONTAINER` | yes | — | Container name |
| `BLOB_AZURE_CONNECTION_STRING` | one of these | — | Takes precedence if set |
| `BLOB_AZURE_ACCOUNT_URL` | one of these | — | Used with `DefaultAzureCredential` when no connection string is set |
| `BLOB_AZURE_PREFIX` | no | `""` | Prepended to all blob names |

### 4. Authentication

If `BLOB_AZURE_CONNECTION_STRING` is set, it takes precedence. Otherwise `BLOB_AZURE_ACCOUNT_URL` is required and the adapter uses `DefaultAzureCredential`, which supports managed identity, workload identity, Azure CLI, and environment variables.

| Environment | Recommended auth |
|-------------|-----------------|
| Local dev | Connection string, or `az login` with account URL |
| Azure App Service / Functions | Managed identity with account URL |
| AKS | Workload identity with account URL |

**Production recommendation:** Use managed identity–based auth for Azure-hosted deployments. `DefaultAzureCredential` is a good general-purpose default, but teams deploying to a known Azure environment may prefer a more specific credential such as `ManagedIdentityCredential` for tighter control and faster auth resolution.

### Operational notes

- Blob names follow the same key pattern as S3.
- `upload_blob` is called with `overwrite=True` — re-ingesting is safe.
- `delete` returns `False` when the blob does not exist (matches local backend semantics).
- Azure Blob Storage provides strong consistency.

---

## Optional Dependency Installation

Cloud SDKs are not required unless you use the corresponding backend. Local-backend users need no additional packages.

| Backend | Packages |
|---------|----------|
| `local` | none |
| `s3` | `boto3` |
| `azure` | `azure-storage-blob`, `azure-identity` |

If a cloud backend is selected but its SDK is not installed, the application raises a clear `ImportError` on startup with install instructions.

---

## UI Behavior

Blob storage is mostly transparent to the frontend. Key behaviors:

- **Run detail page:** Blob-backed artifacts show a preview and a "Load artifact" button. Full content is fetched on demand via `GET /v1/artifacts/{id}`. Inline artifacts display their content immediately.
- **Stream playback:** Blob-backed `llm_stream` artifacts show a "Load stream events" action. Once loaded, stream playback, grouping, and raw view work normally.
- **Compare page:** Stream event loading supports blob-backed `llm_stream` on either side. Compare remains summary-first — it does not eagerly load blob bodies. Loading and error states are tracked per side.
- **Error handling:** If a blob cannot be loaded, the UI shows an error message with a retry button. Metadata and preview text remain visible.

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| `BLOB_BACKEND=s3` but `boto3` not installed | `ImportError` on first request | `pip install boto3` |
| `BLOB_BACKEND=azure` but SDKs not installed | `ImportError` on first request | `pip install azure-storage-blob azure-identity` |
| `BLOB_BACKEND=s3` without `BLOB_S3_BUCKET` | `ValueError` on first request | Set `BLOB_S3_BUCKET` |
| `BLOB_BACKEND=azure` without `BLOB_AZURE_CONTAINER` | `ValueError` on first request | Set `BLOB_AZURE_CONTAINER` |
| `BLOB_BACKEND=azure` without connection string or account URL | `ValueError` on first request | Set one of `BLOB_AZURE_CONNECTION_STRING` or `BLOB_AZURE_ACCOUNT_URL` |
| S3 bucket or Azure container does not exist | SDK error on first blob write | Create the bucket/container before starting Leer |
| Wrong AWS region | Slow or failing S3 calls | Set `BLOB_S3_REGION` to match your bucket's region |
| Using local backend in multi-instance production | Each instance has its own blobs; reads fail cross-instance | Switch to `s3` or `azure` |

---

## Security Notes

- Blob references are not public URLs. All reads go through the Leer API.
- Buckets and containers should be private (no public access).
- Do not store credentials, signed URLs, or provider endpoints in artifact database rows.
- In production, prefer IAM roles (AWS) or managed identity (Azure) over long-lived secrets.
- Connection strings contain account keys — treat them as secrets and do not commit them to version control.

---

## Not Supported Yet

The following are not currently implemented:

- GCS backend
- S3-compatible backends (MinIO, R2, Backblaze B2)
- Signed / presigned URLs
- Streaming direct-to-cloud upload
- Encryption-at-rest / KMS / BYOK abstraction
- Object lifecycle / retention policies
- Browser-direct blob access
- Automatic bucket / container creation
