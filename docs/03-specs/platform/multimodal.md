# Multimodal

Defines Leer's platform-level multimodal support model.

This document is the permanent product and technical spec for how Leer handles image, audio, video, document, spreadsheet, and generic file content across providers.

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
- WAV becomes `file` in v1 (dedicated `audio` type deferred)
- MP4 becomes `file` in v1 (dedicated `video` type deferred)
- XLSX becomes `file` with `kind_hint=spreadsheet` in v1

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

## v1 Implementation Constraints

These are known, accepted constraints in the current implementation. They do not block the v1 milestone but are documented here for clarity.

### Step 1 — Binary artifact transport

**Binary/media artifacts are blob-only.** Binary artifacts are always stored in blob storage. They never use `inline_data`. This is enforced by the SDK helper (`create_binary_artifact`) and the ingestion path. Small text/JSON artifacts may still be inline.

**Binary transport uses base64-over-JSON.** The SDK encodes binary artifact content as base64 in the ingest JSON payload (`binary_data_b64` field). The API decodes and stores directly to blob. This causes ~33% payload expansion and is acceptable for small-to-medium media. Future optimization: multipart upload or signed-upload-then-reference flow.

### Step 2 — Content-part normalization

**Output is canonical; input is still provider-shaped.** Output `content_blocks` use the canonical content-part model. Input `LLMInput.messages` still carry raw provider shapes. Summaries reveal multimodal presence (e.g. `[image] Explain this chart`), but message payloads are not yet normalized. This asymmetry is acceptable for v1. Canonical input content parts will be needed later for diffing, replay, and provider-agnostic message rendering.

**Inline base64 media has no artifact reference.** When providers return base64-encoded media (e.g. Anthropic image/document blocks), canonical parts get `source: {"kind": "inline"}` but no `artifact_id`. Step 3 must create derived artifacts for renderable media rather than rendering from raw provider payloads.

**Canonical type scope is image, document, and file only.** `_canonical_type_from_mime` only produces `image`, `document`, or `file`. Audio and video MIME types fall through to generic `file` to avoid overclassifying beyond current scope. Dedicated `audio`/`video` types are deferred.

### General

**Rich media rendering is not part of Step 1 or Step 2.** The binary artifact pipeline and content-part normalization are plumbing-only. Image, PDF, audio, and video renderers are Step 3. Until then, binary artifacts appear as typed artifact cards with metadata (kind, MIME type, filename, size).

---

## Delivery Order

Recommended implementation order:

1. ~~spec and audit~~ — done (Step 0)
2. ~~binary artifact transport (SDK helper, ingestion, serving, mime_type in refs)~~ — done (Step 1)
3. ~~canonical content-part model and provider normalization~~ — done (Step 2)
4. ~~media artifact linking, image + PDF/document rendering, typed generic artifact cards~~ — done (Step 3)
5. compare non-regression, polish, QA (Step 4)
6. later rich renderers for audio/video/spreadsheet

Binary transport comes before normalization because normalizers need a working artifact pipeline to write media into.

---

## Done Criteria for v1

Multimodal v1 is considered complete when:
- canonical content-part model exists
- media artifact taxonomy exists
- providers can map supported multimodal payloads into canonical parts
- large media is stored as blob-backed artifacts when needed
- run detail can inspect multimodal artifacts safely
- image and document rendering exist
- unsupported media types still appear as clear typed artifact cards
- compare does not regress on multimodal runs
