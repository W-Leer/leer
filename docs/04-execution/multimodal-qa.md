# Multimodal v1 — QA Checklist

Visual QA checklist for the multimodal media artifact rendering pipeline.

---

## How to run the demo

```bash
# Prerequisites: API at http://127.0.0.1:8000, Postgres with migrations
cd apps/sdk-python && uv run python ../../examples/demo_multimodal.py
```

Open http://localhost:3000 → `demo-project` → `multimodal-demo`

---

## Run detail — image rendering

- [ ] IMG badge appears in artifact header
- [ ] Image loads via lazy-load from `/v1/artifacts/{id}/content`
- [ ] Loading state shows "Loading image…" placeholder
- [ ] Image preview does not exceed `max-h-[480px]`; layout is not broken
- [ ] Error state shows "Failed to load image" with Retry button
- [ ] Retry button re-attempts the image load
- [ ] Filename is displayed and truncated if long
- [ ] MIME type and size are shown in the header
- [ ] `blob` badge appears for blob-backed artifacts
- [ ] Multiple image artifacts in one step stack cleanly

## Run detail — PDF/document rendering

- [ ] PDF badge appears in artifact header
- [ ] "Open" button opens the raw PDF in a new tab
- [ ] "Preview" button toggles inline PDF embed
- [ ] Inline embed is 480px tall and fills width
- [ ] Browser fallback shows "PDF preview not supported" with direct link
- [ ] "Hide preview" toggles the embed closed
- [ ] Filename truncates cleanly if long
- [ ] Size is shown in the header

## Run detail — generic file card

- [ ] MIME label badge shows the file subtype (e.g. CSV, WAV)
- [ ] Filename is displayed and truncated if long
- [ ] MIME type and size are shown
- [ ] "Open" button opens raw content in a new tab
- [ ] Preview text is displayed and truncated if long
- [ ] `blob` badge appears for blob-backed artifacts

## LLM output — content block media rows

- [ ] `ContentBlockRow` renders for `image` and `document` type blocks
- [ ] `text`, `thinking`, and `tool_call` blocks are not duplicated (skipped by row)
- [ ] Linked artifact (`artifact_id` present) renders the full media preview
- [ ] Unlinked block (no `artifact_id`) renders a fallback card with type/filename/mime
- [ ] Multiple media blocks in one output render stacked without overlap

## LLM input — media markers

- [ ] `[image]` marker badge appears for image input blocks
- [ ] `[document: filename]` marker appears for document inputs
- [ ] `[file: filename]` marker appears for generic file inputs
- [ ] Markers truncate at `max-w-[200px]` for long filenames
- [ ] Markers wrap cleanly in flex layout

## Compare page — multimodal safety

- [ ] Page does not crash with content_blocks containing image/document/file parts
- [ ] Compact `CompareMediaBadge` renders with colored type badge
- [ ] Image blocks show violet badge, document blocks show orange badge
- [ ] File blocks show neutral badge
- [ ] Filename is truncated in badge if long
- [ ] MIME type is shown in badge
- [ ] One-sided media (only side A or B has media) renders cleanly
- [ ] Side without media shows "No output" placeholder
- [ ] Text + media mixed output shows both text and media badges
- [ ] Tool calls still render normally alongside media

## Blob loading / error states

- [ ] Blob-backed image shows loading state then resolves
- [ ] Blob-backed image with unreachable API shows error + retry
- [ ] Blob-backed PDF "Open" link works even before preview toggle
- [ ] Generic file "Open" link works for blob-backed artifacts

## Edge cases

- [ ] Very long filename (>60 chars) truncates with ellipsis, no layout break
- [ ] Repeated media blocks in single output are individually readable
- [ ] Content block with `artifact_id` not found in step artifacts falls back to card
- [ ] Unknown media type block renders with type badge (e.g. `AUDIO`, `VIDEO`)
- [ ] No console errors in browser dev tools during all above checks
- [ ] Content blocks with `null` or missing `type` are handled gracefully

## v1 Known Constraints

These are accepted limitations of the current implementation. See `docs/03-specs/platform/multimodal.md` for the full spec.

### Transport
- Binary artifacts use base64-over-JSON transport (~33% expansion)
- `/v1/artifacts/{id}/content` serves both binary and JSON artifacts

### Normalization
- Output content blocks are canonical; input messages are still provider-shaped
- Canonical types: `image`, `document`, `file` only — audio/video MIME types fall through to `file`
- Chat completions API has no multimodal output shapes yet

### Materialization
- Matching is heuristic (by `provider_part_type`, not positional) — may be ambiguous with multiple same-type blocks
- Post-normalization mutation pass (normalization + materialization are a two-step pipeline)
- Only base64-encoded media is materialized — URL references are preserved as-is

### Rendering
- Input media: display-only markers/badges, no artifact creation
- Compare: compact badges only, no rich image/PDF previews
- No audio/video playback widgets
- No spreadsheet rendering
- No signed URLs or browser-direct blob access
- No replay support for media
