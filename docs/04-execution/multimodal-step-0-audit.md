# Multimodal Step 0 — Codebase Audit

Audit of the current Leer codebase against the multimodal specs:
- `docs/03-specs/platform/multimodal.md`
- `docs/03-specs/platform/content-parts.md`
- `docs/03-specs/platform/media-artifacts.md`

Date: 2026-04-05

---

## 1. SDK / Provider Wrappers

### 1.1 Raw request/response preservation

**Both wrappers already preserve raw payloads as artifacts.**

- OpenAI wrapper (`apps/sdk-python/leer/integrations/openai.py`, `_enrich_step` at line 506) attaches `llm_request` and `llm_response` artifacts via `create_json_artifact`.
- Anthropic wrapper (`apps/sdk-python/leer/integrations/anthropic.py`, `_enrich_step` at line 479) does the same.
- The `request_dict` is captured from `**kwargs` and stored as-is. If a user passes multimodal content blocks (e.g. OpenAI's `{"type": "image_url", ...}` or Anthropic's `{"type": "image", ...}`), these survive into the `llm_request` artifact JSON.

**Verdict: raw provider payloads are already preserved well enough to recover multimodal references later.** The `llm_request` artifact holds the full `kwargs` dict, and the `llm_response` artifact holds the full response dict. This is the correct foundation.

### 1.2 Where content is flattened to text-only

**The normalization layer collapses multimodal content in several places:**

- `normalize.py`, `_normalize_openai_chat` (line 137): extracts only `message.content` as a string from the first choice. If the response contains content blocks (e.g. image output), only the `text` field is captured into `LLMOutput.text`. Content blocks are built from text + tool_calls only (lines 181-185).
- `normalize.py`, `_normalize_openai_responses` (line 222): only processes `output_text` blocks and `function_call` items. Any `image`, `file`, or other output types in the Responses API output are silently dropped.
- `normalize.py`, `normalize_anthropic` (line 329): iterates `response["content"]` and only handles `text`, `tool_use`, `thinking`, and `redacted_thinking` blocks. **Image blocks (`type: "image"`) and document blocks are silently dropped.**

**On the input side:**
- `_input_summary` in both `openai.py` (line 583) and `anthropic.py` (line 556): when `content` is a list, it filters for `type == "text"` or `type == "input_text"` only. Image/file/audio parts in the user message are not reflected in the summary.
- `extractMessageContent` in `llm-step-detail.tsx` (line 274): when content is an array of blocks, it extracts `b.text` and falls back to `JSON.stringify(b)`. Image blocks become opaque JSON strings rather than meaningful content.

### 1.3 Current text-only assumptions

| Location | Assumption |
|----------|-----------|
| `LLMOutput.text` field | Single string for all output text |
| `LLMOutput.content_blocks` | Only `text` and `tool_call` types are ever populated |
| `_input_summary` (both wrappers) | Only extracts text from user messages |
| `_output_summary` (both wrappers) | Only surfaces `text` and `tool_calls` |
| `_request_preview` / `_response_preview` | Text-only previews |
| `StreamCollector` | Only captures `text_delta` and `tool_call_delta` events |

### 1.4 Streaming path specifics

- `streaming.py` `StreamCollector` (line 87): has exactly two content event types: `text_delta` and `tool_call_delta`. There is no `image_delta`, `file_delta`, or generic binary content handling.
- `_process_openai_chunk` in `openai.py` (line 365): reads only `delta.content` (text) and `delta.tool_calls`. No handling of image/file/audio outputs from streaming.
- `_process_anthropic_event` in `anthropic.py` (line 351): handles `text_delta` and `input_json_delta` only. Anthropic's potential `image` or `document` content block deltas are not processed.
- `_assembled_to_chat_response` and `_assembled_to_anthropic_response`: reconstruct a response dict from text + tool_calls only.

**Verdict: streaming is fully text+tool-call-centric. Multimodal outputs from streaming would need new event types in `StreamCollector` and new chunk/event processing in both wrappers.**

---

## 2. Normalization Layer

### 2.1 Current canonical shape

The current normalized shape is `NormalizedLLMCall` in `normalize.py`:

```
NormalizedLLMCall
├── provider: str
├── model: str | None
├── input: LLMInput
│   ├── system: str | None
│   ├── messages: list[dict]     ← raw provider dicts, NOT normalized
│   ├── tools: list[dict]
│   └── params: dict
├── output: LLMOutput
│   ├── text: str | None         ← flattened text-only
│   ├── content_blocks: list[dict] ← text + tool_call only
│   └── tool_calls: list[dict]
├── usage: LLMUsage
└── meta: LLMMeta
```

### 2.2 Text-centricity analysis

- `LLMInput.messages` preserves raw provider message dicts. This means multimodal content blocks from the provider request survive at the input level, but **only because they are passed through un-normalized**. They are not transformed into canonical content parts.
- `LLMOutput` is fully text-centric. The `text` field is a single string. `content_blocks` only ever contains `{"type": "text", ...}` and `{"type": "tool_call", ...}` entries. There is no image, audio, document, or file block.
- The `LLMOutput.content_blocks` field is the closest to where canonical content-part arrays would fit. It already has a `type` field and ordered entries. **This is the natural extension point for multimodal content parts.**

### 2.3 What would need to evolve vs. be replaced

**Evolve (additive):**
- `LLMOutput.content_blocks` → extend to include `image`, `audio`, `video`, `document`, `file` part types with the shared fields from `content-parts.md`
- Add `artifact_id`, `mime_type`, `source`, `filename`, `size_bytes`, `sha256`, `preview_text`, `metadata` fields to content block dicts

**Replace:**
- `LLMOutput.text` is redundant once content blocks are canonical, but can remain as a convenience shorthand (derived from text content blocks). No need to remove it.

**Provider-agnostic vs. provider-shaped:**
- `LLMInput.messages` is still provider-shaped (raw dicts). This is fine for v1 — input normalization can be phased.
- `LLMOutput.content_blocks` is already provider-agnostic in structure but only covers two types.
- `LLMUsage` and `LLMMeta` are fully provider-agnostic.

### 2.4 Where content parts would naturally fit

The spec's canonical content-part model maps directly onto `LLMOutput.content_blocks`. Each entry would follow the shared-fields schema from `content-parts.md`:

```python
{
    "type": "image",          # canonical part type
    "mime_type": "image/png",
    "source": {"kind": "artifact", "value": "<artifact-id>"},
    "artifact_id": "<artifact-id>",
    "filename": "output.png",
    "size_bytes": 183422,
    "preview_text": "generated image",
    "metadata": {"width": 1440, "height": 900}
}
```

This fits cleanly into the existing `list[dict[str, Any]]` field. No structural change to `NormalizedLLMCall` is required — only richer entries in `content_blocks` and updated normalizer logic.

---

## 3. Artifact Layer

### 3.1 Current artifact model

`TraceArtifact` in `apps/sdk-python/leer/models.py` (line 44):

```
TraceArtifact
├── artifact_type: str       ← free-form, currently "llm_request" / "llm_response" / "llm_stream" / "tool_request" / "tool_response" / "tool_error"
├── storage_kind: str        ← "inline" or "blob"
├── role: str | None         ← "input" / "output"
├── format: str | None       ← "json" / "text"
├── mime_type: str | None    ← "application/json" / "text/plain"
├── inline_data: dict | None
├── blob_path: str | None
├── preview_text: str | None
├── metadata: dict
├── id, step_id, sequence_index
```

DB model `Artifact` in `apps/api/app/models.py` (line 140) adds:
- `size_bytes: BigInteger | None`
- `sha256: str | None`
- `project_id, run_id` (foreign keys)
- `created_at`

### 3.2 Can artifacts represent media/file generically?

**Yes, the schema is already flexible enough.** The `artifact_type` is a free-form string, so new kinds like `input_image`, `output_image`, `media_thumbnail`, etc. can be introduced without schema changes. The fields `mime_type`, `size_bytes`, `sha256`, `metadata` already exist. The `storage_kind` already supports `"inline"` and `"blob"`.

### 3.3 MIME types preserved end-to-end?

**Partially.** The `TraceArtifact` model has `mime_type`, and it flows through `_serialize_artifact` in `client.py` (line 61), through `ArtifactPayload` in `schemas.py` (line 54), into the DB `Artifact.mime_type` column. However:
- `create_json_artifact` in `artifacts.py` (line 23) hardcodes `mime_type="application/json"`.
- `create_text_artifact` in `artifacts.py` (line 53) hardcodes `mime_type="text/plain"`.
- There is **no `create_binary_artifact`** or `create_media_artifact` helper. Media artifacts would need a new helper or manual construction.

### 3.4 Binary / non-JSON artifact support

**This is the biggest artifact-layer gap.**

- `inline_data` in the DB is `JSONB`. Binary payloads (images, audio, video, PDFs) **cannot** be stored inline. They must go through blob storage.
- The ingestion path in `_persist_artifact` (`apps/api/app/services/ingestion.py`, line 30) serializes `inline_data` to JSON bytes for hashing/sizing and for blob offload. This path works fine for JSON content but **cannot handle raw binary blobs**.
- The blob key format is `projects/{id}/runs/{id}/artifacts/{id}.json` — note the `.json` extension. For binary media, the extension should reflect the actual content type (e.g. `.png`, `.wav`).
- The artifact fetch endpoint (`apps/api/app/routes/artifacts.py`, `_resolve_data` at line 45) assumes blob content is valid JSON (`json.loads(raw)`) and returns it as `dict | None`. **Binary media cannot be served through this endpoint as-is.**

### 3.5 Blob storage sufficiency

The blob storage abstraction in `apps/api/app/storage/base.py` is already media-ready:
- `BlobStore.put(key, data, content_type="application/json")` — the `content_type` parameter already exists and can be set to any MIME type.
- `BlobStore.get(key) -> bytes` — returns raw bytes, no JSON assumption.
- Local, S3, and Azure backends all implement this interface.
- `BlobRef` tracks `content_type`, `size_bytes`, `sha256`.

**The blob storage layer itself is sufficient.** The gap is in the integration layer above it:
1. `_persist_artifact` assumes JSON serialization before blob offload
2. The artifact fetch route assumes JSON decoding of blob content
3. The `ArtifactContentResponse.data` field is `dict | None` — cannot represent binary

### 3.6 Summary of artifact-layer gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| No `create_media_artifact` / `create_blob_artifact` SDK helper | Medium | Easy to add |
| `_persist_artifact` JSON-only pipeline | High | Must support raw bytes path |
| Artifact fetch assumes JSON blobs | High | Must support binary response for media |
| `ArtifactContentResponse.data` is `dict | None` | High | Need binary/base64/URL response mode |
| Blob key extension is `.json` | Low | Cosmetic, but should match MIME |

---

## 4. Backend API / Schemas

### 4.1 Artifact read API for multimodal

The current `/v1/artifacts/{artifact_id}` endpoint (`apps/api/app/routes/artifacts.py`) returns `ArtifactContentResponse`:

```python
class ArtifactContentResponse(BaseModel):
    id: UUID
    artifact_type: str
    role: str | None
    format: str | None
    storage_kind: str
    size_bytes: int | None
    sha256: str | None
    preview_text: str | None
    data: dict[str, Any] | None    # ← JSON-only
```

**For multimodal v1, this endpoint needs a second response mode** for binary/media artifacts — either:
- Streaming raw bytes with `Content-Type` headers (for direct rendering)
- Base64-encoded data in the JSON response
- A signed URL / redirect to blob storage

### 4.2 Timeline response schema

`TimelineStep` in `schemas.py` (line 198) includes:
- `llm: dict[str, Any] | None` — the normalized LLM call
- `artifacts: list[StepArtifactRef]` — lightweight artifact refs

`StepArtifactRef` (line 184) includes `kind`, `role`, `format`, `preview_text`, `storage_kind`, `size_bytes`, `sha256`. **This is already metadata-rich enough for multimodal artifact cards in the UI.** The UI can determine rendering strategy from `kind` (artifact type) and decide whether to lazy-load.

### 4.3 What stays unchanged

- Ingest schema (`IngestRunRequest`, `ArtifactPayload`) — already has all fields needed for multimodal artifacts
- `StepArtifactRef` in timeline — already has metadata for media cards
- Run/step/event schemas — no changes needed
- Compare response schema — already references `llm_a`/`llm_b` which will naturally contain multimodal content blocks

### 4.4 What needs to change

| Change | Scope |
|--------|-------|
| Add binary artifact serve endpoint or response mode | New route or endpoint variant |
| Add `mime_type` to `StepArtifactRef` | 1 field addition (already in DB, not in the ref schema) |
| Add `mime_type` to `ArtifactContentResponse` | 1 field addition |
| Handle raw binary blob ingestion (SDK → API) | Ingestion pipeline enhancement |

---

## 5. Frontend Rendering

### 5.1 Current `ArtifactViewer` behavior

`apps/web/src/components/artifact-viewer.tsx`:

- Shows a collapsible card with `kind`, `role`, blob badge, size
- Lazy-loads blob content via `fetchArtifactContent`
- Renders loaded data through `StructuredValue` (JSON tree viewer) or raw JSON toggle
- **All rendering assumes `resolvedData` is a `Record<string, unknown>` (parsed JSON)**

### 5.2 What already works for generic media cards

The `ArtifactViewer` header (lines 58-88) already shows:
- `artifact.kind` — could display `input_image`, `output_audio`, etc.
- `artifact.role` — input/output badge
- blob indicator
- `formatBytes(artifact.size_bytes)` — file size

**This is already a reasonable generic artifact card.** For typed media files that don't have rich renderers, this card plus `preview_text` is sufficient.

### 5.3 What assumes JSON-structured values only

- `ArtifactViewer` line 52: `rawText = JSON.stringify(resolvedData, null, 2)` — assumes JSON
- `ArtifactViewer` line 138: renders through `<StructuredValue value={resolvedData} />` — JSON tree
- `fetchArtifactContent` returns `ArtifactContentResponse` with `data: Record<string, unknown> | null` — JSON-only

### 5.4 Rendering gap analysis for each media type

| Media type | Current state | What's needed for v1 |
|-----------|--------------|---------------------|
| **Image** | No renderer. Would stringify the JSON blob. | `<img>` element with URL to artifact serve endpoint. Lightbox optional. |
| **PDF/document** | No renderer. | Embedded `<iframe>` or `<object>` for PDF preview. Fallback to generic card + download. |
| **Audio** | No renderer. | Generic artifact card is sufficient for v1. `<audio>` player is a future enhancement. |
| **Video** | No renderer. | Generic artifact card is sufficient for v1. `<video>` player is a future enhancement. |
| **Spreadsheet** | No renderer. | Generic artifact card is sufficient for v1. |

### 5.5 `LlmStepDetail` message rendering

`extractMessageContent` in `llm-step-detail.tsx` (line 274):
- Handles string content → renders as text
- Handles array content → extracts `b.text` from each block, falls back to `JSON.stringify(b)`
- **Image blocks in user messages become `JSON.stringify({"type": "image_url", "image_url": {...}})` — opaque and unhelpful**

For v1, this function should detect image/media content blocks and render them differently (e.g. thumbnail, media icon, or "attached image" badge).

### 5.6 What can be postponed

- Audio/video embedded players
- Spreadsheet table viewer
- Image lightbox / zoom
- Side-by-side media diff in compare view
- Thumbnail generation

---

## 6. Data-Model Fit Against Specs

### 6.1 Canonical content-part model (`content-parts.md`)

| Requirement | Status | Notes |
|-------------|--------|-------|
| `text` part type | **Already matches** | `content_blocks` has `{"type": "text", "text": "..."}` |
| `image` part type | **Missing** | Not emitted by any normalizer |
| `audio` part type | **Missing** | Not emitted by any normalizer |
| `video` part type | **Missing** | Not emitted by any normalizer |
| `document` part type | **Missing** | Not emitted by any normalizer |
| `file` part type | **Missing** | Not emitted by any normalizer |
| `tool_call` part type | **Already matches** | `content_blocks` has `{"type": "tool_call", ...}` |
| `tool_result` part type | **Missing** | Tool results are separate artifacts, not in content blocks |
| Shared fields (mime_type, source, artifact_id, etc.) | **Missing** | Current content blocks have only `type` + type-specific fields |
| Source descriptor model | **Missing** | No source kind/value/label structure exists |
| Ordering preservation | **Already matches** | Content blocks maintain provider order |

**Score: Partially matches (2/8 part types, ordering OK, shared fields missing)**

### 6.2 Multimodal source model

| Requirement | Status | Notes |
|-------------|--------|-------|
| `inline` source kind | **Missing** | No source descriptor exists |
| `artifact` source kind | **Missing** | No artifact_id reference in content blocks |
| `provider_file` source kind | **Missing** | Provider file IDs not captured |
| `url` source kind | **Missing** | URLs not preserved as source references |
| `derived` source kind | **Missing** | No derived content concept |

**Score: Missing**

### 6.3 Media artifact taxonomy (`media-artifacts.md`)

| Requirement | Status | Notes |
|-------------|--------|-------|
| `input_image` / `output_image` kinds | **Missing** | Current kinds: `llm_request`, `llm_response`, `llm_stream`, `tool_*` |
| `input_audio` / `output_audio` kinds | **Missing** | — |
| `input_video` / `output_video` kinds | **Missing** | — |
| `input_document` / `output_document` kinds | **Missing** | — |
| `input_file` / `output_file` kinds | **Missing** | — |
| `media_thumbnail` / `media_transcript` etc. | **Missing** | — |
| `llm_request` / `llm_response` / `llm_stream` kinds | **Already matches** | Already in use |
| Artifact shape fields (artifact_type, format, mime_type, storage_kind, preview_text, size_bytes, sha256, metadata) | **Already matches** | All exist in DB model |
| Derived artifact linkage (source_artifact_id, etc.) | **Missing** | No inter-artifact references |

**Score: Partially matches (artifact shape is ready, taxonomy and linkage missing)**

### 6.4 Binary/blob storage fit

| Requirement | Status | Notes |
|-------------|--------|-------|
| Blob store abstraction | **Already matches** | `BlobStore` protocol with local/S3/Azure backends |
| Content-type aware storage | **Already matches** | `put()` accepts `content_type` parameter |
| Raw bytes retrieval | **Already matches** | `get()` returns `bytes` |
| SHA256 integrity | **Already matches** | `compute_sha256` + `sha256` columns |
| JSON-only ingestion pipeline | **Blocks multimodal** | `_persist_artifact` serializes to JSON before blob offload |
| JSON-only fetch endpoint | **Blocks multimodal** | `_resolve_data` calls `json.loads()` on blob content |

**Score: Partially matches (storage layer ready, integration layer is JSON-only)**

### 6.5 Rendering strategy

| Requirement | Status | Notes |
|-------------|--------|-------|
| Rich renderer by MIME/type | **Missing** | No media-specific renderers |
| Derived-text renderer | **Missing** | No transcript/OCR rendering |
| Generic artifact card | **Partially matches** | `ArtifactViewer` header is a good base, but body is JSON-only |
| Lazy loading | **Already matches** | Blob artifacts lazy-load on click |

**Score: Partially matches (generic card base exists, lazy loading works)**

### 6.6 Provider mapping readiness

| Requirement | Status | Notes |
|-------------|--------|-------|
| OpenAI image input mapping | **Missing** | `image_url` blocks dropped by normalizer |
| OpenAI image output mapping | **Missing** | Responses API `image` output items dropped |
| OpenAI file/document input mapping | **Missing** | — |
| Anthropic image input mapping | **Missing** | `image` content blocks dropped by normalizer |
| Anthropic document input mapping | **Missing** | `document` content blocks dropped |
| Raw provider preservation | **Already matches** | `llm_request` / `llm_response` artifacts capture full payloads |

**Score: Partially matches (raw preservation exists, normalization mapping missing)**

---

## 7. Recommended Real v1 Scope

### 7.1 Should v1 support all media types at storage level?

**Yes.** The artifact model is generic enough that all media types can be stored with correct `artifact_type`, `mime_type`, `size_bytes`, and `sha256` today. The normalization layer should emit canonical content parts for all recognized media types even if the UI only richly renders a subset. Unknown types should fall back to `file` with a `kind_hint` in metadata.

### 7.2 Should v1 rich-render only image + document/PDF?

**Yes.** Image rendering is the highest-value, lowest-effort win. PDF/document preview is the second. Audio/video/spreadsheet are lower priority and acceptable as generic cards.

### 7.3 Should audio/video/spreadsheet initially be generic artifact cards?

**Yes.** The existing `ArtifactViewer` card header already provides kind, size, and preview_text. With `mime_type` added to `StepArtifactRef`, it becomes a proper typed artifact card. Rich players are future work.

### 7.4 Is there enough current foundation to do this cleanly?

**Yes, with targeted gaps to fill.** The critical gaps are:
1. Binary artifact ingestion path (currently JSON-only)
2. Binary artifact serving endpoint (currently JSON-only)
3. Normalizer extensions for multimodal content blocks
4. Media-aware rendering in the frontend

None of these require architectural changes. They are additive extensions to the existing design.

### 7.5 Exact step order after this audit

Binary transport comes before normalization because normalizers need a working artifact pipeline to write media into.

**Step 1 — Binary artifact transport**

1. Add SDK helper for media/binary artifact creation (`create_media_artifact` in `artifacts.py`)
2. Fix binary artifact ingestion (`_persist_artifact` in `ingestion.py` — raw bytes, not JSON-only)
3. Add binary artifact serving endpoint (raw bytes with correct `Content-Type`)
4. Add `mime_type` to `StepArtifactRef` in timeline response schemas

**Step 2 — Canonical content parts and provider normalization**

5. Add canonical content-part types to `LLMOutput.content_blocks` with shared fields (mime_type, source, artifact_id, filename, size_bytes, preview_text, metadata)
6. Update OpenAI normalizer — map `image_url` inputs, image outputs (Responses API), file/document inputs
7. Update Anthropic normalizer — map `image` blocks, `document` blocks, media outputs
8. Use `file` as safe fallback for unrecognized content types

**Step 3 — UI rendering v1**

9. Add image renderer component (`<img>` with lazy load from binary serve endpoint)
10. Add document/PDF renderer component (embedded preview or styled download card)
11. Improve generic artifact card (MIME-type icon/badge, download action)
12. Update `extractMessageContent` for media badges in user messages

**Step 4 — Polish and compare non-regression**

13. Verify compare handles multimodal content blocks and blob-backed artifacts
14. Loading/error UX for media artifacts
15. QA/demo signoff

---

## v1 Decision Block

### Supported in v1

- Canonical content-part model with `text`, `image`, `audio`, `video`, `document`, `file`, `tool_call` types
- Media artifact taxonomy (`input_image`, `output_image`, `input_document`, `output_document`, etc.)
- Binary/blob-backed media storage through existing blob infrastructure
- Provider normalization for OpenAI + Anthropic image and document inputs
- Provider normalization for OpenAI image outputs (Responses API)
- Image artifact rendering (inline preview with lazy load)
- PDF/document artifact rendering (embedded preview or styled card)
- Correct `mime_type`, `size_bytes`, `sha256` tracking end-to-end
- Binary artifact serving endpoint
- Generic typed artifact cards for all media types
- Compare non-regression for multimodal runs

### Captured but generic in v1

- Audio artifacts — stored with correct metadata and MIME type, rendered as generic artifact card
- Video artifacts — stored with correct metadata and MIME type, rendered as generic artifact card
- Spreadsheet artifacts — stored as `file` with `kind_hint=spreadsheet`, rendered as generic artifact card
- Derived artifacts (transcript, OCR, etc.) — not generated in v1 but the artifact model supports them
- Provider file IDs — preserved in artifact metadata but not actively used for retrieval
- Model-generated audio/video outputs — captured if provider returns them, rendered generically
- Input message media badges — image/file content in user messages shown as badges, not inline previews

### Deferred beyond v1

- Audio player widget
- Video player widget
- Spreadsheet table renderer
- Thumbnail generation pipeline
- OCR/transcription extraction
- Signed URL / browser-direct media access
- Side-by-side media diffing in compare view
- Multimodal replay execution
- Provider-specific UI branches
- Perfect provider parity for all multimodal features
- Page preview extraction for documents
- Waveform visualization for audio
