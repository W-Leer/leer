# Content Parts

Defines Leer's canonical provider-agnostic content-part model.

This document is the source of truth for how multimodal inputs and outputs are represented inside Leer regardless of provider-specific request/response formats.

---

## Goals

- define one stable internal shape for multimodal content
- avoid coupling the product to OpenAI, Anthropic, or any single provider format
- make UI rendering, diffing, storage, and future replay possible
- separate semantic content from heavy artifact payloads

---

## Design Principles

### 1. Provider-agnostic first

Leer should not store provider-native multimodal payloads as its primary internal representation.
Provider-native payloads may still be preserved in request/response artifacts, but product logic should depend on canonical content parts.

### 2. Content is semantic, artifacts are physical

A content part describes what the model saw or produced.
An artifact stores the actual bytes, file, preview, transcript, or extracted derivative.

Example:
- content part: `image` with mime type and artifact reference
- artifact: the actual image bytes stored inline or in blob storage

### 3. Binary payloads are not message metadata

Large media must not be embedded in step metadata or timeline payloads.
Content parts should contain lightweight references only.

### 4. One model for input and output

The same part taxonomy should be used for:
- user input to the model
- tool-produced content passed into the model
- model output content
- future replay and diff features

---

## Canonical Part Types

Leer defines the following canonical part types:

- `text`
- `image`
- `audio`
- `video`
- `document`
- `file`
- `tool_call`
- `tool_result`
- `provider_tool`
- `compaction`

The first six are multimodal content parts.
`tool_call` and `tool_result` are included because real provider payloads often interleave tool activity with content.
`provider_tool` is a tool the provider ran itself (web search, code execution, MCP); see ADR-002.
`compaction` is a provider compaction of the conversation context; see ADR-003.

---

## Shared Fields

All content parts should include the following shared fields where applicable:

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `type` | string | yes | Canonical part type |
| `mime_type` | string \| null | no | MIME type if known |
| `source` | object | yes | Lightweight source descriptor |
| `provider` | string \| null | no | Origin provider when directly sourced from a provider object |
| `provider_part_type` | string \| null | no | Original provider-native part/block type |
| `artifact_id` | uuid \| null | no | Artifact containing the primary payload |
| `filename` | string \| null | no | Display filename |
| `size_bytes` | integer \| null | no | Size when known |
| `sha256` | string \| null | no | Content hash when known |
| `preview_text` | string \| null | no | Small preview text for UI |
| `metadata` | object | yes | Small provider-agnostic supplemental metadata |

Notes:
- `artifact_id` is optional because some parts may reference provider-hosted files or external URLs.
- `metadata` should stay lightweight and serializable.
- raw bytes never belong directly in a content part.

---

## Source Descriptor

Every part must include a `source` object describing where the canonical payload comes from.

### Allowed source kinds

- `inline`
- `artifact`
- `provider_file`
- `url`
- `derived`

### Source shape

```json
{
  "kind": "artifact",
  "value": "<artifact-id-or-provider-id-or-url>",
  "label": null
}
```

### Meaning

| Source kind | Meaning |
|------------|---------|
| `inline` | Small text/json content embedded directly in the normalized part |
| `artifact` | Content stored in a Leer artifact |
| `provider_file` | Provider-managed uploaded/generated file reference |
| `url` | External URL reference |
| `derived` | Content derived from another asset, such as OCR or transcript |

---

## Part Shapes

## TextPart

Used for plain text content.

```json
{
  "type": "text",
  "mime_type": "text/plain",
  "source": { "kind": "inline", "value": null, "label": null },
  "text": "Hello world",
  "metadata": {}
}
```

### Additional fields

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `text` | string | yes | Text content |

Text is the only part type that is normally allowed to carry its primary content inline by default.

---

## ImagePart

Used for images passed to or produced by the model.

```json
{
  "type": "image",
  "mime_type": "image/png",
  "source": { "kind": "artifact", "value": "<artifact-id>", "label": null },
  "artifact_id": "<artifact-id>",
  "filename": "diagram.png",
  "size_bytes": 183422,
  "preview_text": "uploaded image",
  "metadata": {
    "width": 1440,
    "height": 900,
    "detail": "high"
  }
}
```

### Suggested metadata

- width
- height
- provider detail level
- alt text if available
- thumbnail artifact reference if available

---

## AudioPart

Used for audio input/output.

```json
{
  "type": "audio",
  "mime_type": "audio/wav",
  "source": { "kind": "artifact", "value": "<artifact-id>", "label": null },
  "artifact_id": "<artifact-id>",
  "filename": "question.wav",
  "size_bytes": 922144,
  "preview_text": "user audio input",
  "metadata": {
    "duration_ms": 18250,
    "sample_rate_hz": 16000,
    "channels": 1,
    "transcript_artifact_id": "<artifact-id>"
  }
}
```

### Suggested metadata

- duration_ms
- sample_rate_hz
- channels
- transcript artifact reference
- language if known

---

## VideoPart

Used for video input/output.

```json
{
  "type": "video",
  "mime_type": "video/mp4",
  "source": { "kind": "artifact", "value": "<artifact-id>", "label": null },
  "artifact_id": "<artifact-id>",
  "filename": "demo.mp4",
  "size_bytes": 5829144,
  "preview_text": "uploaded video",
  "metadata": {
    "duration_ms": 44200,
    "width": 1280,
    "height": 720,
    "poster_artifact_id": "<artifact-id>"
  }
}
```

### Suggested metadata

- duration_ms
- width
- height
- frame rate if known
- poster image artifact reference
- extracted audio/transcript references

---

## DocumentPart

Used for PDFs and document-like assets where document semantics matter.

```json
{
  "type": "document",
  "mime_type": "application/pdf",
  "source": { "kind": "artifact", "value": "<artifact-id>", "label": null },
  "artifact_id": "<artifact-id>",
  "filename": "report.pdf",
  "size_bytes": 284192,
  "preview_text": "Quarterly report PDF",
  "metadata": {
    "page_count": 14,
    "ocr_artifact_id": "<artifact-id>",
    "pages_artifact_id": "<artifact-id>"
  }
}
```

### Suggested metadata

- page_count
- OCR artifact reference
- extracted text artifact reference
- page preview artifact reference

---

## FilePart

Used for generic files that do not yet have richer first-class rendering.
This includes spreadsheets, archives, unknown file types, and future extensibility.

```json
{
  "type": "file",
  "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "source": { "kind": "artifact", "value": "<artifact-id>", "label": null },
  "artifact_id": "<artifact-id>",
  "filename": "metrics.xlsx",
  "size_bytes": 118224,
  "preview_text": "uploaded spreadsheet",
  "metadata": {
    "kind_hint": "spreadsheet"
  }
}
```

### Suggested metadata

- kind_hint (`spreadsheet`, `archive`, `presentation`, etc.)
- extracted text/table artifact references
- sheet count if known

---

## ToolCallPart

Used when provider-native output interleaves tool calls alongside content.

```json
{
  "type": "tool_call",
  "mime_type": null,
  "source": { "kind": "inline", "value": null, "label": null },
  "metadata": {
    "tool_name": "lookup_weather",
    "tool_call_id": "call_123"
  }
}
```

This part type is not a media part, but is part of the same canonical sequence model.

---

## ProviderToolPart

A tool the provider executed (no local tool step exists). Not listed in
`output.tool_calls`. Call and result are one part on both providers.

```json
{
  "type": "provider_tool",
  "id": "srvtoolu_1",
  "name": "web_search",
  "input": { "query": "leer execution record" },
  "output": [ { "type": "web_search_result", "url": "https://…" } ],
  "provider": "anthropic",
  "provider_part_type": "server_tool_use",
  "preview_text": "web_search: leer execution record"
}
```

`status`, `output`, `error` and `server` are present only when known.

---

## CompactionPart

The provider compacted the conversation context (ADR-003). Never part of
`output.text`.

```json
{
  "type": "compaction",
  "summary": "User asked about …",
  "provider": "anthropic",
  "provider_part_type": "compaction",
  "preview_text": "User asked about …"
}
```

`summary` is `null` when the provider encrypts the result (OpenAI) or
compaction failed. `id` is present when the provider sends one;
`retained_messages` only on OpenAI `responses.compact()`.

---

## ToolResultPart

Used for normalized tool result content flowing back into the model.

```json
{
  "type": "tool_result",
  "mime_type": "application/json",
  "source": { "kind": "artifact", "value": "<artifact-id>", "label": null },
  "artifact_id": "<artifact-id>",
  "preview_text": "weather lookup result",
  "metadata": {
    "tool_name": "lookup_weather",
    "tool_call_id": "call_123"
  }
}
```

---

## Ordering Rules

Content parts are ordered.
The order must preserve the original semantic sequence of the provider payload as closely as possible.

Examples:
- text followed by image
- image followed by text
- text, tool call, tool result, text

Leer should not reorder parts for convenience.

---

## Normalization Rules

### Preserve semantics, not provider syntax

Adapters should map provider-native blocks into canonical parts while preserving:
- order
- type meaning
- media references
- important metadata

Adapters should not preserve provider-native syntax as the primary application model.

### Prefer richer canonical part types over generic file

Examples:
- PDF should become `document`, not generic `file`
- PNG should become `image`, not generic `file`
- WAV should become `audio`, not generic `file`
- XLSX may remain `file` in v1 with `kind_hint=spreadsheet`

### Use `file` as the safe fallback

If the type is unknown or unsupported, normalize as `file` rather than dropping it.

---

## UI Implications

The content-part model should allow the UI to decide:
- which renderer to use
- whether lazy loading is needed
- whether a preview can be shown
- whether a fallback generic artifact card is necessary

This model must therefore stay lightweight and reference-based.

---

## Non-Goals

This document does not define:
- provider-specific adapters in detail
- blob storage mechanics
- artifact taxonomy
- replay execution semantics

Those are covered elsewhere.
