# Blob Storage

This document defines the permanent blob storage design for Leer.

It describes **what the system should be**, not the temporary implementation sequence.

---

## Purpose

Leer currently stores request, response, summary, and stream data primarily inline in the database.

That is correct for small and medium payloads, but it does not scale well for:

- very large prompts or responses
- large tool inputs / outputs
- long streaming event histories
- future multimodal artifacts
- future replay inputs / outputs
- high-cardinality workloads where large inline payloads hurt query performance

Blob storage exists to keep the system fast, scalable, and predictable while preserving the developer experience.

---

## Goals

- keep small payloads simple and fast
- offload large payloads safely
- preserve the same product truth whether payloads are inline or blob-backed
- avoid making the UI or API care unnecessarily about storage location
- support future multimodal and replay use cases
- keep the storage layer provider-agnostic

---

## Non-Goals

Blob storage is **not** intended to:

- replace PostgreSQL as the source of truth for core run / step metadata
- store every payload by default
- introduce provider-specific branching in artifact logic
- define replay execution semantics
- define encryption / key management in full detail
- define lifecycle policies for all future enterprise deployments

---

## Design Principle

> Small things should stay simple. Large things should not break the system.

This means Leer should use a **hybrid storage model**:

- **small payloads** stay inline in PostgreSQL
- **large payloads** are written to blob storage, with PostgreSQL storing only a reference and lightweight preview metadata

---

## Canonical Model

### Core rule

Every artifact or large payload in Leer has exactly one canonical content location at read time:

- either **inline**
- or **blob-backed**

The UI and API should present a stable artifact model regardless of which storage mode was used.

### What stays in PostgreSQL

PostgreSQL remains the source of truth for:

- runs
- steps
- events
- summaries
- artifact identity and metadata
- lightweight previews
- blob references

### What may move to blob storage

Blob storage is used for large payload bodies, including:

- large `llm_request`
- large `llm_response`
- large `llm_stream`
- large `tool_request`
- large `tool_response`
- large `tool_error`
- future multimodal payloads
- future replay payloads

---

## Storage Modes

### 1. Inline

Used when the payload is below the inline threshold.

Characteristics:

- content stored directly in PostgreSQL JSONB / text fields
- fastest retrieval path
- ideal for summaries, small requests, small responses, small stream artifacts

### 2. Blob-backed

Used when the payload exceeds the inline threshold.

Characteristics:

- payload body stored in object storage
- database stores blob reference + metadata + preview text
- API may return a lightweight ref first, and fetch full body only when needed

---

## Threshold Policy

### Policy

Leer must use a configurable threshold to decide whether a payload is stored inline or in blob storage.

### Default behavior

The threshold should be:

- **byte-based**
- measured on the serialized payload body
- applied consistently across artifact creation paths

### Permanent product rule

The exact numeric threshold is an implementation detail, not part of the permanent product contract.

What the spec guarantees:

- there is a single default threshold
- it is configurable
- it is applied uniformly
- the system may force blob storage for some future artifact classes even below the default threshold if operationally justified

### Preview rule

Even when the full payload is blob-backed, Leer should still keep lightweight inline information for list and detail surfaces:

- artifact type
- preview text
- media / format hint if relevant
- size metadata
- blob-backed flag

---

## Blob Object Abstraction

Blob storage must be accessed through a provider-agnostic abstraction.

### Required capabilities

The abstraction must support:

- write blob
- read blob
- delete blob
- existence check
- generate stable blob metadata
- return a canonical blob reference object

### Required blob metadata

Each blob reference should include enough information to support reads, debugging, and migrations.

Minimum conceptual fields:

- storage provider
- bucket / container
- object key
- content type
- content length
- checksum / digest if available
- created timestamp
- version / schema marker if needed later

### Provider-agnostic requirement

The product design must not assume AWS S3 specifically.

Leer should support an abstraction compatible with:

- S3-style object storage
- GCS
- Azure Blob Storage
- local development file-backed storage

This keeps deployment flexible across cloud providers and self-hosted environments.

---

## Artifact Model

### Artifact record remains primary

Artifacts still exist as first-class database records.

Blob storage does **not** replace the artifact record.

### Artifact content fields

Conceptually, an artifact may contain:

- inline content
- or blob reference
- but not both as the primary full body at the same time

Small preview metadata may remain inline in both modes.

### Blob-backed artifact invariants

If an artifact is blob-backed:

- the database record must clearly indicate that
- preview text must still be available when possible
- the UI must be able to discover that full content requires fetch / hydration
- deleting the artifact should eventually delete the blob

### Stream artifact rule

`llm_stream` artifacts may be blob-backed when stream event payloads become large.

This is especially important because stream histories can grow quickly and should not be allowed to bloat timeline responses.

---

## API Shape

### Design goal

The API should expose artifacts in a way that is stable across inline and blob-backed storage.

### List / timeline behavior

Timeline and compare responses should remain lightweight.

They should include:

- artifact id
- kind / type
- role
- preview text
- format hint
- small inline payload only when explicitly allowed
- signal that the artifact is blob-backed when applicable

### Full artifact retrieval

Full artifact bodies should be retrieved through a dedicated artifact read path.

That path should:

- return inline content directly when inline
- read from blob storage when blob-backed
- present a uniform response shape to the frontend

### UI contract

The frontend should not need to know whether content came from PostgreSQL or blob storage beyond optional hints like:

- loading state
- blob-backed badge
- file size / payload size

---

## UI Behavior

### General rule

Blob-backed artifacts should feel like normal artifacts, not like second-class citizens.

### Timeline / detail surfaces

In run detail or step detail:

- previews should render normally
- large content should be fetched only when needed
- raw / formatted toggles should still work once content is loaded
- loading full blob-backed content should be explicit and safe

### Compare surfaces

Compare should stay lightweight.

Blob-backed content should not be eagerly loaded into compare cards unless the surface truly needs it.

For large payloads:

- compare should prefer summaries and previews
- full raw bodies should be opt-in

### Failure behavior

If a blob cannot be loaded:

- the UI should show a truthful error state
- metadata and preview should still remain visible when available
- the artifact record itself should not disappear from the UI

---

## Performance Principles

### PostgreSQL protection

Blob storage exists primarily to protect PostgreSQL from becoming the dump site for arbitrarily large payloads.

The design should minimize:

- oversized JSONB rows
- heavy timeline payloads
- slow compare responses caused by giant inline artifacts
- runaway storage growth inside the relational database

### Retrieval efficiency

The system should optimize for:

- fast list views
- fast timeline loads
- lazy hydration of large bodies
- minimal repeated downloads when possible

### Streaming implication

Very large stream artifacts should be eligible for blob storage by default once payload size crosses threshold.

This ensures streaming scales without forcing a redesign later.

---

## Security and Privacy Principles

Blob storage must respect the same trust model as the rest of Leer.

### Required properties

- blob references are not public URLs by default
- reads must go through authorized server-side access or controlled signed access
- tenants / projects must remain isolated
- blob keys must not leak sensitive user data in their names
- deletion and retention behavior must remain controllable

### Out of scope here

This spec does not fully define:

- encryption key hierarchy
- enterprise BYOK
- region pinning policy
- retention / legal hold

Those can be layered later.

---

## Local Development

Blob storage must support a low-friction local mode.

Accepted local modes may include:

- local filesystem-backed blob store
- local object storage emulator
- developer cloud bucket

The product requirement is:

> local development must not require a full production cloud setup.

---

## Deployment Model

Blob storage should be deployment-agnostic.

### This means

Leer should not hardcode assumptions about:

- AWS only
- GCP only
- Azure only

### Recommended product posture

- define one provider-agnostic blob interface
- provide one local development backend
- provide one widely compatible object-store backend first
- allow deployment-specific configuration to choose the actual storage provider

This keeps Leer portable across SaaS, self-hosted, and future enterprise deployments.

---

## Migration Philosophy

Blob storage should be additive.

The system must support a gradual transition from fully inline storage to hybrid storage without requiring a redesign of the run / step / artifact model.

### Permanent migration rule

Existing inline artifacts remain valid.
New large artifacts may become blob-backed.
The product should not require backfilling all old artifacts immediately.

---

## Observability of Storage Mode

Blob usage should itself be observable internally.

Useful internal signals include:

- inline vs blob artifact counts
- average payload size
- blob read latency
- blob write failures
- blob hydration failures in UI/API paths

This is not a user-facing feature requirement, but it is important for operating the platform.

---

## Future Extension Points

This design intentionally prepares for:

- multimodal artifacts
- long stream histories
- replay input / output storage
- downloadable files
- export bundles
- archival / lifecycle policies
- optional provider-specific optimizations behind the same abstraction

---

## Invariants

These must remain true:

1. PostgreSQL remains the source of truth for run / step / artifact identity and metadata.
2. Blob storage is only for payload bodies, not for replacing the relational model.
3. The UI should not materially care whether content is inline or blob-backed.
4. Small payloads should remain inline by default.
5. Large payloads must not be allowed to degrade core timeline and compare performance.
6. Blob storage must be provider-agnostic.
7. Local development must remain easy.
8. Blob-backed artifacts must still preserve previews and debuggability.

---

## Summary

Blob storage in Leer is a **hybrid storage layer** for large artifact bodies.

It exists to let Leer scale safely while keeping the developer experience clean:

- small payloads stay inline
- large payloads are offloaded
- artifacts stay first-class
- API shape stays stable
- UI stays mostly storage-agnostic
- the design remains cloud-provider agnostic

---

## Backend Configuration

Leer blob storage is backend-agnostic by design. The backend is selected through a single setting and all artifact semantics remain identical regardless of which backend is active.

For practical setup instructions and example `.env` files, see `docs/04-execution/blob-storage-setup.md`.

### Shared settings

| Setting | Default | Description |
|---------|---------|-------------|
| `BLOB_BACKEND` | `local` | Backend selector: `local`, `s3`, or `azure` |
| `BLOB_INLINE_THRESHOLD_BYTES` | `262144` (256 KB) | Payloads at or below this size stay inline; payloads above are offloaded to blob storage |

### Local filesystem

Use for local development and single-node testing.

| Setting | Default | Description |
|---------|---------|-------------|
| `BLOB_LOCAL_ROOT` | `.leer/blobs` | Directory where blob files are written |

Not suitable for multi-instance production deployments.

### AWS S3

Use for production deployments on AWS or S3-compatible infrastructure.

| Setting | Default | Required | Description |
|---------|---------|----------|-------------|
| `BLOB_S3_BUCKET` | — | yes | S3 bucket name |
| `BLOB_S3_REGION` | — | no | AWS region passed to the boto3 client |
| `BLOB_S3_PREFIX` | `""` | no | Key prefix prepended to all blob keys |

Authentication uses the standard boto3 credential chain (environment variables, shared config, IAM role, IRSA, ECS task role). Leer does not accept AWS credentials as its own settings.

Requires `boto3` to be installed.

### Azure Blob Storage

Use for production deployments on Azure.

| Setting | Default | Required | Description |
|---------|---------|----------|-------------|
| `BLOB_AZURE_CONTAINER` | — | yes | Azure container name |
| `BLOB_AZURE_CONNECTION_STRING` | — | one of these | Full connection string (takes precedence) |
| `BLOB_AZURE_ACCOUNT_URL` | — | one of these | Account URL; used with `DefaultAzureCredential` |
| `BLOB_AZURE_PREFIX` | `""` | no | Key prefix prepended to all blob keys |

If `BLOB_AZURE_CONNECTION_STRING` is set, it takes precedence. Otherwise `BLOB_AZURE_ACCOUNT_URL` is required and auth uses `DefaultAzureCredential`.

Requires `azure-storage-blob` and `azure-identity` to be installed.

### What is not stored in artifact rows

Artifact database rows contain only portable blob reference data:

- `storage_kind` (`inline` or `blob`)
- `blob_path` (the object key)
- `size_bytes`
- `sha256`

Bucket names, container names, credentials, signed URLs, and provider endpoints are never stored in artifact rows.

