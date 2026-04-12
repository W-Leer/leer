# Multimodal — Implementation Plan

Temporary implementation plan.

This file tracks the practical rollout of multimodal support.
It may evolve or be deleted later.
Permanent rules belong in:
- `docs/03-specs/platform/multimodal.md`
- `docs/03-specs/platform/content-parts.md`
- `docs/03-specs/platform/media-artifacts.md`

---

## Goal

Support multimodal inputs and outputs in Leer using a provider-agnostic canonical content model and artifact-first storage strategy.

---

## Summary of Approach

- define canonical multimodal content parts
- map provider-native payloads into canonical parts
- store heavy media in artifacts, usually blob-backed
- render images and documents richly first
- render audio/video/spreadsheets/files generically at first
- keep provider-native raw payloads preserved separately when useful

---

## Proposed Phases

## Step 0 — Audit current state (done)

### Goal
Understand what OpenAI and Anthropic wrappers already capture, preserve, flatten, or lose.

### Deliverable
Written audit: `docs/04-execution/multimodal-step-0-audit.md`

### Status
Complete. The audit confirmed:
- raw provider payloads are preserved as artifacts (good foundation)
- normalizers drop all multimodal content blocks
- binary artifact pipeline is JSON-only end-to-end
- blob storage layer is ready but integration layer above it is not
- frontend renders all artifacts as JSON trees

---

## Step 1 — Binary artifact transport

### Goal
Make media artifacts technically possible end-to-end before building normalization on top.

Binary transport comes first because normalizers will need to create media artifacts and reference them from content parts. If the artifact pipeline cannot accept or serve binary payloads, normalization has nowhere to write media into.

### Tasks
- add SDK helper for media/binary artifact creation (`create_media_artifact` or `create_blob_artifact` in `artifacts.py`)
- update ingestion path (`_persist_artifact` in `ingestion.py`) to accept raw bytes / non-JSON media payloads
- add binary artifact serving endpoint (raw bytes response with correct `Content-Type`, or separate `/v1/artifacts/{id}/content` route)
- add `mime_type` to `StepArtifactRef` in timeline response schemas
- update blob key format to use MIME-appropriate extensions instead of hardcoded `.json`

### Status
Complete. Implemented via `create_binary_artifact()` SDK helper, base64-over-JSON transport, blob-backed ingestion, `/v1/artifacts/{id}/content` serving endpoint, and `mime_type` in timeline refs.

### Known limitations (acceptable for v1, revisit later)

1. **Base64 transport** — binary data travels as base64 inside the JSON ingest payload. This causes ~33% payload expansion and higher memory use during encode/decode. Acceptable for small-to-medium media (up to ~10–50 MB). Future optimization: multipart upload or signed-upload-then-reference flow.

2. **`/v1/artifacts/{id}/content` is dual-purpose** — returns raw bytes for binary artifacts and serialized JSON for JSON artifacts. The contract is slightly mixed but pragmatic: the metadata endpoint (`/v1/artifacts/{id}`) stays canonical for structured reads, and `/content` is the generic "give me the artifact body" endpoint. Acceptable for v1; revisit if the two paths diverge significantly.

3. ~~`filename` lives in `metadata`~~ — **Fixed.** `filename` is now a first-class field on `TraceArtifact`, `ArtifactPayload`, `StepArtifactRef`, `ArtifactContentResponse`, the ORM model, and the frontend types. Migration `0003_artifact_filename` adds the DB column.

### Output
An artifact pipeline that can store, retrieve, and serve binary media end-to-end.

---

## Step 2 — Canonical content parts and provider normalization

### Goal
Introduce the content-part model and map provider-native multimodal payloads into canonical parts.

### Tasks — content-part model
- add typed canonical part definitions aligned with `content-parts.md`
- define shared fields (type, mime_type, source, artifact_id, filename, size_bytes, preview_text, metadata)
- define source descriptor model (inline, artifact, provider_file, url, derived)
- extend `LLMOutput.content_blocks` to carry multimodal part types

### Tasks — provider input normalization
- OpenAI: map `image_url` blocks, file/document inputs into canonical parts
- Anthropic: map `image` blocks, `document` blocks into canonical parts
- preserve provider-native metadata where useful
- create media artifacts for inline base64 payloads
- use `file` as safe fallback for unknown content types

### Tasks — provider output normalization
- OpenAI: map generated image outputs (Responses API) into canonical parts
- Anthropic: map any media output blocks
- preserve original artifacts/references
- generic file fallback for unrecognized output types

### v1 target media types
- image (input and output)
- PDF/document (input)
- generic file fallback

### Stretch target
- audio, video, spreadsheet through generic file

### Output
A code-level content model and provider normalizers that produce multimodal content blocks with artifact references.

---

## Step 3 — UI rendering v1

### Goal
Ship the first multimodal UI surfaces.

### v1 rich renderers
- image renderer (`<img>` with lazy load from binary artifact endpoint)
- PDF/document renderer (embedded preview or styled download card)

### v1 generic artifact-card renderers
- audio (kind + MIME + size + download)
- video (kind + MIME + size + download)
- spreadsheet (kind + MIME + size + download)
- generic file (kind + MIME + size + download)

### Tasks
- add image renderer component
- add document/PDF renderer component
- improve generic artifact viewer for typed media (MIME-type icon/badge, download action)
- update `extractMessageContent` to render media badges in message views instead of raw JSON
- ensure lazy loading works for blob-backed media assets

### Output
A UI that renders image and document artifacts richly, and all other media types as clear typed artifact cards.

---

## Step 4 — Polish and compare non-regression

### Goal
Harden multimodal support for production use.

### Tasks
- verify compare page handles canonical parts and blob-backed artifacts without crashing
- add minimal compare rules for media presence/type changes
- handle long-content / large-media loading and error UX gracefully
- loading states, error recovery, and timeout handling for media artifacts

### QA and demo
- `examples/demo_multimodal_image.py`
- `examples/demo_multimodal_document.py`
- later `examples/demo_multimodal_audio.py`

### QA checklist
- capture
- artifact creation
- blob-backed storage
- lazy loading
- rendering
- compare non-regression

### Output
A stable, tested multimodal v1 ready for real use.

---

## Recommended v1 Product Cut

### Fully supported in v1
- image input/output tracing
- PDF/document input tracing
- generic multimodal artifact storage
- blob-backed media retrieval
- image rendering
- PDF/document rendering

### Captured but not richly rendered in v1
- audio
- video
- spreadsheets
- other files

This means users can still inspect these assets as typed artifacts with metadata and lazy loading, even before dedicated players/viewers exist.

---

## Risks

- provider-native multimodal shapes may differ more than expected
- generated media outputs may have different reference models than input files
- document rendering can expand scope quickly if page previews/OCR are mixed into v1
- trying to do rich UI for every media type in one pass will likely slow the project significantly

---

## Non-Goals

For the first implementation wave, do not do:
- full provider parity
- provider-specific UI branches unless unavoidable
- advanced multimodal replay
- full audio/video/spreadsheet rich rendering
- signed URL/browser-direct storage access

---

## Immediate Next Step

Step 0 audit is complete (`docs/04-execution/multimodal-step-0-audit.md`).
Step 1 binary artifact transport is complete.

Next: begin **Step 2 — Canonical content parts and provider normalization**.
