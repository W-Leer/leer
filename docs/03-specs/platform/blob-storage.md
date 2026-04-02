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

# Appendix — Blob Storage Backend Configuration

This appendix defines how blob storage should be configured across environments.

The guiding principle is:

> Leer should stay provider-agnostic at the product layer and backend-specific only at the storage adapter layer.

---

## Configuration Goals

Blob backend configuration should:

- keep local development simple
- support cloud object storage in production
- avoid product-level coupling to any one cloud
- make migration between backends possible without changing artifact semantics

---

## Shared Concepts

Regardless of backend, Leer should treat blob storage through the same logical contract:

- `blob_backend` — which adapter to use
- `blob_inline_threshold_bytes` — maximum inline payload size before offloading
- provider-specific credentials/config only inside the selected adapter

Artifact semantics should remain unchanged:

- inline artifacts use `storage_kind=inline`
- offloaded artifacts use `storage_kind=blob`
- `blob_path` stores the backend key/path, not a public URL
- full artifact payload retrieval always goes through the Leer API

---

## Local Backend

Use for:

- local development
- single-machine testing
- CI smoke tests

Suggested config:

```env
BLOB_BACKEND=local
BLOB_LOCAL_ROOT=.leer/blobs
BLOB_INLINE_THRESHOLD_BYTES=262144
```

Behavior:

- blob files are stored on the local filesystem
- best for development only
- not suitable for multi-instance production deployments

Recommended notes in the main spec:

- local backend is the default
- local backend is not a production HA storage strategy

---

## Amazon S3 Backend

Use for:

- production deployments on AWS
- general-purpose object storage
- environments where S3-compatible tooling already exists

Suggested config shape:

```env
BLOB_BACKEND=s3
BLOB_S3_BUCKET=leer-artifacts-prod
BLOB_S3_REGION=eu-west-1
BLOB_S3_PREFIX=artifacts/
BLOB_INLINE_THRESHOLD_BYTES=262144
```

Credential strategy:

- prefer IAM role / workload identity in production
- allow explicit access key / secret only for local testing or exceptional cases

Suggested optional fields:

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...
```

Design notes:

- `blob_path` should store the object key, not a signed URL
- signed/public URLs should not be persisted in artifact rows
- all reads should still be mediated by the Leer API
- S3 adapter should support bucket + prefix separation

Recommended future adapter responsibilities:

- put bytes
- get bytes
- delete object
- existence check
- consistent content-type support
- optional metadata tagging if useful later

---

## Azure Blob Storage Backend

Use for:

- production deployments on Azure
- teams standardized on Azure infra

Suggested config shape:

```env
BLOB_BACKEND=azure
BLOB_AZURE_ACCOUNT_URL=https://myaccount.blob.core.windows.net
BLOB_AZURE_CONTAINER=leer-artifacts
BLOB_AZURE_PREFIX=artifacts/
BLOB_INLINE_THRESHOLD_BYTES=262144
```

Credential strategy:

- prefer managed identity / workload identity in production
- allow connection string only for local development or transitional setups

Suggested optional fields:

```env
AZURE_STORAGE_CONNECTION_STRING=...
```

Design notes:

- `blob_path` should store the blob key/path within the container
- keep container/account config in backend settings, not in artifact rows
- full payload retrieval should still go through the Leer API

---

## Recommended Settings Structure

As the backend matrix grows, config should stay grouped by backend.

Suggested long-term shape:

```text
blob_backend
blob_inline_threshold_bytes

blob_local_root

blob_s3_bucket
blob_s3_region
blob_s3_prefix

blob_azure_account_url
blob_azure_container
blob_azure_prefix
```

This keeps the interface explicit while avoiding cross-provider confusion.

---

## What Should Not Be in Artifact Rows

Do not store these in the artifact DB row:

- raw cloud credentials
- signed URLs
- public URLs
- provider SDK objects
- backend-specific auth state

Artifact rows should only store portable blob reference data such as:

- storage kind
- blob key/path
- size
- checksum

---

## Recommended Production Guidance

For production docs, recommend:

- local backend only for dev/testing
- S3 or Azure Blob for production
- private buckets/containers by default
- no direct browser access required
- API-mediated artifact retrieval as the default security model

---

## Future Extensions

This appendix can later expand to cover:

- GCS backend
- S3-compatible backends (Cloudflare R2, MinIO, Backblaze B2, Wasabi)
- encryption-at-rest expectations
- object lifecycle / retention rules
- blob garbage collection
- cross-region replication

---

## Suggested Short Note for the Main Spec

You can append a short note like this inside `docs/03-specs/blob-storage.md`:

> Leer blob storage is backend-agnostic by design. Local filesystem storage is the default for development. Production deployments should use a managed object store such as Amazon S3 or Azure Blob Storage via a storage adapter, while preserving the same artifact semantics and API-mediated retrieval model.

