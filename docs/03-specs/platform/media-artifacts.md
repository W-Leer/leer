# Media Artifacts

Defines how multimodal media and related derivatives are stored as artifacts in Leer.

This document complements:
- `docs/03-specs/platform/content-parts.md`
- `docs/03-specs/platform/blob-storage.md`

---

## Goals

- define which multimodal payloads become artifacts
- define artifact kinds for original media and derived assets
- define storage expectations for large binary/media payloads
- define the relationship between content parts and artifacts

---

## Core Principle

Canonical content parts describe multimodal content semantically.
Artifacts store the actual payloads and derived assets physically.

Examples:
- original uploaded image
- generated image output
- PDF bytes
- transcript text
- OCR text
- waveform preview
- document page previews
- spreadsheet extraction results

---

## Storage Rules

### Rule 0 — media payloads are artifact-first, never inline in normalized payloads

Binary media must not live inside normalized LLM payloads, content-part objects, or step metadata.

Normalized content parts carry lightweight references (artifact_id, source descriptor, mime_type, size).
Artifacts carry the actual bytes.

This applies to every direction:
- provider request payloads containing user-uploaded images, documents, or files
- provider response payloads containing model-generated images, audio, or files
- heavy provider file objects (base64-encoded uploads, signed URLs, file IDs)

All of these become artifact refs in the canonical model, not inline blobs.

Small derived text (transcripts, OCR snippets, compact metadata JSON) may remain inline in artifacts when below the blob threshold, but never inside content parts or step metadata.

### Rule 1 — raw media is stored as an artifact

The original media/file payload should be represented as an artifact, not embedded in step metadata.

Applies to:
- images
- audio
- video
- PDFs/documents
- spreadsheets
- generic files

### Rule 2 — large assets should be blob-backed

Blob storage is the default expectation for most real multimodal binaries.

Inline storage should be reserved for:
- small JSON metadata
- short transcripts
- tiny previews
- small derived text where clearly below threshold

### Rule 3 — derived assets are first-class artifacts

Derived outputs from multimodal processing should also be artifacts when useful.

Examples:
- transcript
- OCR output
- page images
- thumbnail
- waveform summary
- extracted tables

### Rule 4 — artifacts must be referenceable from content parts

Where the UI or future replay needs a payload, the corresponding content part should reference an artifact via `artifact_id` or related metadata.

---

## Artifact Taxonomy

The following artifact kinds are recommended for multimodal support.

## Original input artifacts

- `input_image`
- `input_audio`
- `input_video`
- `input_document`
- `input_file`

## Original output artifacts

- `output_image`
- `output_audio`
- `output_video`
- `output_document`
- `output_file`

## Derived artifacts

- `media_thumbnail`
- `media_transcript`
- `media_ocr`
- `media_pages`
- `media_text_extract`
- `media_table_extract`
- `media_waveform`
- `media_poster`

## Provider/raw preservation artifacts

These preserve raw provider-native request/response structures when needed.

- `llm_request`
- `llm_response`
- `llm_stream`
- `provider_file_ref`

These are not strictly multimodal-specific, but they often contain multimodal references.

---

## Artifact Shape Expectations

All multimodal artifacts should continue using Leer's general artifact model.

Important fields include:

| Field | Purpose |
|------|---------|
| `artifact_type` | Logical artifact kind |
| `format` | Logical serialization format |
| `mime_type` | Media type when known |
| `storage_kind` | `inline` or `blob` |
| `preview_text` | Small UI preview |
| `size_bytes` | Payload size |
| `sha256` | Integrity / dedupe aid |
| `metadata` | Lightweight supplemental metadata |

---

## Recommended MIME / Format Conventions

### Images

- MIME examples: `image/png`, `image/jpeg`, `image/webp`
- `format`: keep provider-neutral, commonly `binary` or `image`

### Audio

- MIME examples: `audio/wav`, `audio/mpeg`, `audio/mp4`, `audio/ogg`
- `format`: `binary` or `audio`

### Video

- MIME examples: `video/mp4`, `video/webm`, `video/quicktime`
- `format`: `binary` or `video`

### Documents

- MIME examples: `application/pdf`, `text/markdown`, `application/msword`, Office MIME types
- `format`: `binary`, `pdf`, `document`, or more specific logical labels as needed

### Derived text assets

- MIME examples: `text/plain`, `application/json`
- `format`: `text` or `json`

---

## Original vs Derived Asset Linkage

Derived artifacts should be linked through metadata rather than by embedding content.

Examples:
- image part references `input_image` artifact
- image thumbnail references `media_thumbnail`
- audio part references `input_audio`
- transcript references `media_transcript`
- PDF part references `input_document`
- OCR text references `media_ocr`

Suggested metadata linkage fields:
- `source_artifact_id`
- `derived_from_artifact_id`
- `thumbnail_artifact_id`
- `transcript_artifact_id`
- `ocr_artifact_id`
- `pages_artifact_id`
- `poster_artifact_id`

---

## UI Rendering Strategy

Artifacts should support a renderer ladder:

1. **rich renderer by MIME/type**
   - image preview
   - audio player
   - video poster/player
   - PDF/document preview
2. **derived-text renderer**
   - transcript
   - OCR text
   - extracted tables
3. **generic artifact card**
   - filename
   - mime type
   - size
   - preview text
   - lazy load / download / raw view

Not every artifact type needs a rich UI in v1.

---

## v1 Recommendation

### Rich v1 renderers

- images
- PDFs/documents

### Generic v1 artifact-card support only

- audio
- video
- spreadsheets
- other files

That means v1 should still preserve these assets fully, but may show them in the UI as typed artifact cards rather than full embedded players/viewers.

---

## Blob Storage Expectations

Multimodal artifacts are expected to use blob storage frequently.

### Typically blob-backed

- original images
- original audio
- original video
- PDFs/documents
- spreadsheets
- generated media outputs
- large OCR/page extraction outputs

### Sometimes inline

- small transcripts
- tiny derived JSON metadata
- compact extracted summaries
- tiny thumbnails encoded as metadata only, if ever used

The exact threshold remains controlled by blob-storage policy, not multimodal logic.

---

## Provider Mapping Guidance

Adapters should map provider-managed file references into artifacts when possible.

Examples:
- provider file ID may be preserved as metadata or a `provider_file_ref` artifact
- if bytes are available to Leer, the original file should be stored as a proper media artifact
- if only an ID/reference is available, the content part can reference the provider source while preserving metadata

---

## Security Notes

Multimodal artifacts may contain sensitive user content.

Guidelines:
- do not inline large raw media into timeline payloads
- do not expose provider-signed URLs directly in UI state
- keep access mediated through Leer's API where possible
- preserve hashes and metadata for integrity/debugging
- never store credentials or secrets in artifact rows

---

## Non-Goals

This document does not define:
- exact provider adapter logic
- OCR/transcription extraction pipelines
- playback widgets for every file type
- replay semantics for externally hosted provider files

Those belong in implementation docs and future execution specs.
