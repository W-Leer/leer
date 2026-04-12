# Multimodal

Defines Leer's platform-level multimodal support model.

This document is the permanent product and technical spec for how Leer handles multimodal content across providers. The platform model covers image, audio, video, document, spreadsheet, and generic file content. See **v1 Support Strategy** and **v1 Status** for what is currently shipped.

---

## Goal

Support multimodal inputs and outputs in a provider-agnostic, artifact-first, blob-friendly way.

Leer should be able to:
- capture multimodal inputs sent to models
- capture multimodal outputs produced by models
- normalize them into stable internal shapes
- store heavy payloads safely
- render them meaningfully in the UI
- avoid binding product semantics to any single provider API

---

## Scope

Multimodal in Leer includes:

### Inputs

- image input
- audio input
- video input
- PDF/document input
- spreadsheet input
- generic file input

### Outputs

- model-generated image output
- model-generated audio output
- model-generated video output
- model-generated document/file output
- text responses that reference media/file outputs

### Related derived data

- transcripts
- OCR text
- page previews
- thumbnails
- poster frames
- extracted tables/text summaries

---

## Design Principles

### 1. Canonical before provider-native

Leer must define its own normalized multimodal model.
Provider-native request/response payloads may still be preserved as artifacts, but product logic should depend on canonical content parts.

### 2. Multimodal media payloads are artifact-first

Binary media must not live inside normalized LLM payloads or step metadata.

This means:
- normalized content parts reference artifacts — they never carry raw bytes or large base64 inline
- heavy provider file objects (uploaded images, generated media, document payloads) become artifact refs, not inline blobs
- the normalized LLM shape stays lightweight regardless of how much media was involved

Content parts carry type, source descriptor, artifact_id, and small metadata.
Artifacts carry the actual bytes, stored inline (if tiny) or in blob storage (if not).

This is the hard boundary between semantic content (content parts) and physical payload (artifacts).

### 3. Blob storage is foundational

Multimodal support assumes the blob-storage system exists and is used for large media payloads.
Blob storage is not optional for serious multimodal scale.

### 4. Rich rendering can be phased

Leer should be able to preserve all media types even before every media type has a polished rich renderer.

This means:
- broad capture support can arrive before broad UI support
- generic artifact cards are acceptable for some types in v1

### 5. Input and output symmetry

The same conceptual model should work for both sides:
- what the model consumed
- what the model produced

---

## Canonical Model

The multimodal platform model is built on two lower-level specs:

- `content-parts.md`
- `media-artifacts.md`

### Content parts

Content parts define semantic content units such as:
- text
- image
- audio
- video
- document
- file

### Artifacts

Artifacts define physical payload storage such as:
- original media bytes
- derived previews
- transcript text
- OCR output
- provider-native raw request/response structures

### Relationship

A content part may point to one or more artifacts.
The UI and future replay systems should rely on this relationship rather than large inline payloads.

---

## v1 Support Strategy

### v1 capture/storage support

In v1, Leer should aim to correctly capture and preserve all of the following at the data-model level:
- image
- PDF/document
- audio
- video
- spreadsheet
- generic file

That means:
- normalize the content part
- preserve source references
- create artifacts where appropriate
- use blob storage when large
- surface metadata in the UI

### v1 rich UI support

In v1, only a subset needs rich rendering:
- image
- PDF/document

### v1 generic-card support

The following may initially render as typed artifact cards only:
- audio
- video
- spreadsheet
- generic files

This is still valid multimodal support as long as capture, preservation, and lazy loading are correct.

---

## Rendering Strategy

### Rich renderers

Prefer dedicated renderers where practical:
- image preview/lightbox
- PDF/document preview
- future audio player
- future video player
- future spreadsheet renderer

### Fallback renderer

If no rich renderer exists, use a generic artifact viewer showing:
- media/file type
- filename
- size
- mime type
- preview text
- lazy load action
- raw/structured metadata if available

### Derived-renderer support

Where derived text exists, the UI may also show:
- transcript
- OCR text
- extracted page text
- extracted tables

---

## Provider-Agnostic Handling

Leer must not assume a universal provider standard for multimodal payloads.

Providers may differ in:
- request shape
- content block taxonomy
- file upload model
- file reference model
- generated media output shape
- streaming behavior

Therefore:
- adapters map provider-native payloads to Leer's canonical content parts
- provider-native payloads may be preserved in artifacts for debugging
- the rest of the platform should not depend on provider syntax

---

## Storage Rules

### Keep small text-like data inline when reasonable

Examples:
- small transcript snippets
- compact extracted summaries
- small metadata JSON

### Offload heavy content to blob-backed artifacts

Examples:
- image bytes
- audio bytes
- video bytes
- PDFs and office files
- large OCR or transcript outputs
- generated media outputs

### Never rely on timeline inline payloads for large media

Timeline payloads should remain lightweight.
All large media must be lazily retrievable.

---

## Normalization Rules

Adapters should:
- preserve original content order
- preserve semantic type
- preserve references to source assets
- create canonical parts even when UI support is incomplete
- prefer `file` as a safe fallback rather than dropping unknown content

Examples:
- PDF becomes `document`
- PNG becomes `image`
- WAV currently normalizes to `file` in v1
- MP4 currently normalizes to `file` in v1
- XLSX becomes `file` with `kind_hint=spreadsheet` in v1

Dedicated `audio`/`video` canonical handling is deferred.

---

## Compare and Replay Implications

### Compare

Multimodal compare does not need full rich diffing in v1.
It should first support:
- stable content-part presence
- artifact references
- metadata-aware compare
- no crashes when large media is blob-backed

### Replay

Replay is out of scope for the initial multimodal implementation.
However, the multimodal model should avoid blocking replay later.
That means preserving:
- canonical content parts
- media/file references
- provider file IDs when relevant
- original artifacts when bytes are available

---

## Security and Privacy

Multimodal payloads may be much more sensitive than plain text.

Requirements:
- store raw media as artifacts, not in step metadata
- use blob storage for large media
- avoid exposing direct provider-signed URLs in normal UI state
- preserve hashes/size for integrity and debugging
- do not store credentials or secret endpoints in artifact rows

---

## Non-Goals for v1

The first multimodal milestone should explicitly avoid:
- perfect provider parity
- deeply provider-specific UI branches
- universal rich rendering for every media type
- browser-direct media loading from cloud storage
- replay execution of all multimodal workflows
- OCR/transcription pipelines for every provider path

---

## v1 Architecture Summary

### Binary artifact transport

- SDK helper: `create_binary_artifact()` creates blob-backed media artifacts with `mime_type`, `filename`, raw bytes
- Ingestion: API decodes base64 from the ingest payload, computes `sha256`/`size_bytes`, stores to blob
- Serving: `/v1/artifacts/{id}/content` returns raw bytes with correct `Content-Type`
- Timeline refs include `mime_type`, `filename`, `size_bytes`, `storage_kind`

### Content-part normalization

- Canonical part types: `text`, `image`, `document`, `file`, `tool_call`
- Each media part carries: `type`, `mime_type`, `source`, `artifact_id`, `filename`, `preview_text`
- Source descriptors: `inline`, `url`, `artifact`, `provider_file`
- OpenAI: `output_image`, `image_generation_call` → canonical `image`; unknown output items → `file` fallback
- Anthropic: `image` blocks → `image`; `document` blocks → `document`; unknown blocks → `file` fallback
- Summaries reveal media presence: `[image] Explain this chart`, `[document: report.pdf]`

### Media artifact materialization

- After normalization, `materialize_media_artifacts()` scans output content blocks
- For `image`/`document` parts with inline base64, decodes bytes and creates binary artifacts
- Enriches content parts with `artifact_id`, `source: {"kind": "artifact"}`, `size_bytes`
- Artifact types: `output_image`, `output_document`
- Idempotent — skips parts that already have `artifact_id`
- Called from both OpenAI and Anthropic wrapper `_enrich_step` flows

### Frontend rendering

- `ImageArtifactPreview`: inline `<img>` loaded from artifact content endpoint, loading/error states
- `DocumentArtifactPreview`: open/preview actions, embedded `<object>` PDF viewer with fallback
- `GenericMediaArtifactCard`: typed card with MIME label, filename, size, open action
- `ContentBlockRow`: renders canonical content blocks, matches `artifact_id` to step artifacts
- `CompareMediaBadge`: compact color-coded badges for compare page (no rich previews)
- `ArtifactViewer` dispatches to media renderer for binary/media artifacts

### Provider coverage

| Provider | Input capture | Output normalization | Materialization |
|----------|---------------|----------------------|-----------------|
| OpenAI Responses API | summaries with media markers | `output_image`, `image_generation_call`, `refusal`, unknown → `file` | base64 images → `output_image` artifacts |
| OpenAI Chat Completions | summaries with media markers | text + tool_call only (no multimodal output shapes yet) | n/a |
| Anthropic | summaries with media markers | `image`, `document`, unknown → `file` | base64 image/document → `output_image`/`output_document` artifacts |

---

## v1 Known Constraints

These are accepted constraints in the current implementation. They do not block v1 but are documented for future reference.

### Transport

- **Base64-over-JSON transport.** Binary artifact content is base64-encoded in the ingest JSON payload. ~33% payload expansion, acceptable for small-to-medium media. Future: multipart upload or signed-upload-then-reference.
- **`/v1/artifacts/{id}/content` is dual-purpose.** Returns raw bytes for binary artifacts and serialized JSON for JSON artifacts. Pragmatic but slightly mixed contract.

### Normalization

- **Output is canonical; input is still provider-shaped.** Output `content_blocks` use canonical parts. Input `LLMInput.messages` still carry raw provider shapes. Summaries reveal media presence, but messages are not normalized. Later needed for diffing, replay, and provider-agnostic rendering.
- **Canonical type scope: `image`, `document`, `file` only.** Audio/video MIME types fall through to generic `file`. Dedicated `audio`/`video` canonical types are deferred.
- **Chat completions API has no multimodal output shapes to normalize yet.**

### Materialization

- **Matching is heuristic.** `_find_response_block()` matches content parts to provider response blocks by `provider_part_type`. Works for common single-image/document cases. Could become ambiguous with multiple blocks of the same type. Future: positional or identity-based matching.
- **Post-normalization mutation pass.** Normalization creates content blocks first, then `materialize_media_artifacts` mutates them in a second pass. Keeps normalization pure but means normalization + materialization should be treated as one pipeline.
- **URL-sourced media is not materialized.** Only base64-encoded media (where bytes are available) creates artifacts. URL references and provider-file references are preserved as-is.

### Rendering

- **Input-side media is display-only.** Output media gets first-class artifacts and rich rendering. Input media gets text markers and badges only — no materialization, no artifact creation. Later needed for replay and full provenance.
- **Compare shows badges, not rich previews.** The compare page renders compact media badges (type, filename, MIME) rather than inline images or PDF previews. Rich compare-level media diffing is deferred.

---

## v1 Status

Multimodal v1 is complete:

- Canonical content-part model exists
- Media artifact taxonomy exists
- OpenAI and Anthropic map multimodal payloads into canonical parts
- Large media is stored as blob-backed artifacts
- Run detail renders image and PDF/document artifacts richly
- Unsupported media types appear as typed generic artifact cards
- Compare page handles multimodal content without crashing
- 65+ backend tests cover normalization, materialization, and edge cases

### What's next (beyond v1)

- Rich renderers for audio/video/spreadsheet
- Canonical input content parts (input normalization)
- Input-side media artifact materialization
- Positional materialization matching
- Multipart binary upload transport
- Compare-level media diffing
