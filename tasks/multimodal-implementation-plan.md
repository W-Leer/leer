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

### Status
Complete. Implemented in `normalize.py` (shared helpers + canonical part builder), OpenAI and Anthropic wrapper summary updates. 85 new multimodal normalization tests + 322 full-suite SDK tests pass.

### What was implemented

**Canonical content-part helpers** (in `normalize.py`):
- `_media_part()` builder produces canonical parts with shared fields: `type`, `mime_type`, `source`, `provider`, `provider_part_type`, `filename`, `preview_text`, `metadata`
- `_make_source()` builder for `inline`, `url`, `provider_file` source descriptors
- `_canonical_type_from_mime()` maps MIME types to `image`, `document`, or `file` (audio/video deferred to a future step)
- `_summarize_content_for_user()` produces media-aware summaries like `[image] Explain this chart`

**OpenAI normalization**:
- Responses API: `output_image` blocks mapped to canonical `image` parts
- Responses API: `image_generation_call` items mapped to canonical `image` parts
- Responses API: `refusal` blocks preserved as text
- Unknown output items/blocks preserved as generic `file` fallback (never dropped)
- Chat completions: no multimodal output shapes yet (text + tool_call only)

**Anthropic normalization**:
- `image` response blocks mapped to canonical `image` parts (base64 and url sources)
- `document` response blocks mapped to canonical `document` parts (with filename from title)
- Unknown block types preserved as generic `file` fallback (never dropped)

**Summary improvements** (both providers):
- `_input_summary` now reveals `[image]`, `[document: report.pdf]`, `[file]` markers
- `_output_summary` includes `media` field listing output media parts
- `_request_preview` shows media markers in user messages
- `_response_preview` shows media labels when no text output

### v1 target media types
- image (input and output)
- PDF/document (input and output)
- generic file fallback

### Stretch target
- audio, video, spreadsheet through generic file

### Intentional v1 decisions

1. **Input messages stay provider-shaped.** Output `content_blocks` are canonical; input `LLMInput.messages` still carry the raw provider shapes. Summaries reveal multimodal presence, but the message payloads are not normalized. This asymmetry is acceptable for v1. Canonical input content parts will be needed later for clean diffing, replay, and provider-agnostic message rendering.

2. **Inline base64 media has no artifact reference yet.** Anthropic base64 image/document blocks get `source: {"kind": "inline"}` but no `artifact_id`. Step 3 must create derived artifacts for renderable media rather than rendering from raw provider payloads — this is the preferred long-term approach.

3. **`_canonical_type_from_mime` only produces `image`, `document`, `file`.** Audio/video MIME types fall through to generic `file`. Dedicated `audio`/`video` canonical types are deferred to avoid overclassifying beyond Step 2 scope.

4. **Chat completions API has no multimodal output shapes to normalize yet.**

### Output
A code-level content model and provider normalizers that produce multimodal content blocks with artifact references.

---

## Step 3 — Media artifact linking + v1 rendering

### Goal
Ship the first multimodal UI surfaces with artifact-backed rendering.

### Status
Complete. Implemented media artifact materialization in both provider wrappers, artifact-linked content parts, and frontend rendering components.

### What was implemented

**Backend — media artifact materialization** (in `normalize.py`):
- `materialize_media_artifacts()` inspects canonical content blocks after normalization
- For `image`/`document` parts with inline base64 data, decodes and creates binary artifacts via `create_binary_artifact`
- Enriches content parts with `artifact_id`, `source: {"kind": "artifact"}`, `size_bytes`, `mime_type`
- Called from both OpenAI and Anthropic `_enrich_step` flows, before metadata is serialized
- Uses clean artifact types: `output_image`, `output_document`
- Idempotent — skips parts that already have `artifact_id`

**Backend — provider support**:
- Anthropic: base64 image blocks → `output_image` artifacts
- Anthropic: base64 document/PDF blocks → `output_document` artifacts
- OpenAI: `image_generation_call` with base64 result → `output_image` artifacts
- OpenAI: `output_image` with base64 data → `output_image` artifacts
- URL-sourced and provider-file-referenced media are not materialized (no bytes available)

**Frontend — new components** (`media-artifact.tsx`):
- `ImageArtifactPreview` — inline `<img>` with lazy loading from artifact content endpoint
- `DocumentArtifactPreview` — download/open actions + embedded `<object>` PDF preview toggle
- `GenericMediaArtifactCard` — typed card with MIME label, filename, size, open action
- `MediaArtifactRenderer` — smart dispatcher that picks the right renderer
- `ContentBlockRow` — renders a canonical content block, matching to step artifacts by `artifact_id`
- `InputMediaMarker` — compact badge for multimodal input content

**Frontend — existing component updates**:
- `ArtifactViewer` dispatches media artifacts to `MediaArtifactRenderer` instead of JSON viewer
- `LlmStepDetail` `OutputSection` renders media content blocks via `ContentBlockRow`
- `LlmStepDetail` `MessageBlock` shows `InputMediaMarker` badges for multimodal inputs
- `extractMessageContent` produces `[image]`, `[document: file.pdf]`, `[file]` markers instead of raw JSON
- Compare page `OutputContent` renders media block badges without crashing

### Tests added
- 7 materialization tests covering Anthropic image, Anthropic document, OpenAI image generation, text-only no-ops, URL media not materialized, idempotent re-runs, text+tool_call preserved

### Intentional v1 decisions

1. **Materialization matching is heuristic.** `_find_response_block()` matches canonical content parts to provider response blocks by `provider_part_type`. This works for common single-image/document cases but could become ambiguous if a response contains multiple blocks of the same type (e.g. two Anthropic image blocks). A future improvement would use positional or identity-based matching.

2. **Materialization is a post-normalization mutation pass.** Normalization first creates content blocks without artifact linkage, then `materialize_media_artifacts` mutates them in a second pass. This is practical and keeps normalization pure, but means Step 2 + Step 3 should be treated as one pipeline. Tests around ordering and mutation behavior are important.

3. **Input-side media is display-only.** Output media gets first-class artifacts; input media gets markers/badges only. This is a deliberate v1 cut. Replay, full provenance, and richer input rendering may push toward materializing input-side media as artifacts too.

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
Step 2 canonical content parts and provider normalization is complete.
Step 3 media artifact linking + v1 rendering is complete.

Next: begin **Step 4 — Polish and compare non-regression**.
