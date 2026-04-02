# Blob Storage — QA Checklist

## Goal

Verify that Leer correctly:

- keeps small artifacts inline
- offloads large artifacts to blob storage
- preserves preview text and metadata
- lazily loads blob-backed artifacts in the UI
- does not break run detail or compare behavior

---

## Setup

### API
Make sure the API is running locally.

### Web
Make sure the web app is running locally.

### Blob backend
For local verification, use the default local backend.

Expected defaults:
- `blob_backend=local`
- `blob_local_root=.leer/blobs`
- `blob_inline_threshold_bytes=262144`

### Demo data
Run the blob demo:

```bash
cd apps/sdk-python && uv run python ../../examples/demo_blob_storage.py
```

Expected result:
- at least one run named `blob-storage-demo`
- the run contains both small and large artifacts
- some artifacts stay inline
- some artifacts are stored as blob-backed

---

## Run Detail — General

- [ ] Open the `blob-storage-demo` run in the UI
- [ ] The run loads without error
- [ ] Steps render normally
- [ ] No regression in regular step expansion/collapse behavior

---

## Non-LLM Step Artifacts

- [ ] Open a non-LLM step that has artifacts
- [ ] The **Artifacts** section is visible
- [ ] Artifact count is correct
- [ ] Each artifact row shows:
  - [ ] artifact kind
  - [ ] role when present
  - [ ] sequence index when present
  - [ ] size when available
  - [ ] blob badge for blob-backed artifacts only

### Inline artifact behavior
- [ ] Expand a small inline artifact
- [ ] Data is visible immediately without clicking “Load artifact”
- [ ] Structured view renders correctly
- [ ] Raw toggle works
- [ ] Copy works
- [ ] No unnecessary loading state appears

### Blob-backed artifact behavior
- [ ] Expand a blob-backed artifact
- [ ] Preview text is visible before loading
- [ ] A **Load artifact** button is shown
- [ ] Clicking it loads the full payload successfully
- [ ] Structured view renders correctly after load
- [ ] Raw toggle works after load
- [ ] Copy works after load
- [ ] SHA256 is shown only in expanded view
- [ ] Re-expanding does not trigger a second fetch

### Blob error behavior
- [ ] If artifact fetch fails, an error message is shown
- [ ] Retry button is shown
- [ ] Retry works after the issue is fixed

---

## LLM Step Artifacts

- [ ] Open an LLM step in the same run
- [ ] The normal LLM detail sections still render:
  - [ ] Input
  - [ ] Output
  - [ ] Stream / latency sections if present
  - [ ] Tokens
- [ ] The **Artifacts** section is also visible for the LLM step
- [ ] `llm_request` and `llm_response` are inspectable there
- [ ] `llm_stream` is NOT duplicated in the generic artifact list if intentionally excluded
- [ ] Stream playback UX still works independently

---

## Blob-backed Stream Events

### Inline stream artifact path
- [ ] For inline `llm_stream`, stream playback still works without lazy loading
- [ ] Grouping, playback, raw view, and truncation still work

### Blob-backed stream artifact path
- [ ] For blob-backed `llm_stream`, the Stream section shows a load action
- [ ] Clicking **Load stream events** fetches the event payload
- [ ] After load, playback works
- [ ] Grouping works
- [ ] Raw view works
- [ ] Retry works on failure

### Stream metadata
- [ ] Stream stats still render before blob event payload is loaded
- [ ] Latency row still renders correctly from inline metadata
- [ ] Expanded latency breakdown still renders correctly

---

## Timeline / API Consistency

- [ ] Timeline response includes artifact refs with:
  - [ ] `storage_kind`
  - [ ] `size_bytes`
  - [ ] `sha256`
- [ ] Non-stream artifacts do not inline large payloads in the timeline response
- [ ] Blob-backed artifact bodies are only retrieved via `GET /v1/artifacts/{id}`

---

## Compare Page

- [ ] Compare page still opens successfully for runs containing blob-backed artifacts
- [ ] Existing compare output does not crash
- [ ] Stream latency compare still renders when applicable
- [ ] No assumption of inline artifact payloads causes a UI error

Note:
Artifact-body inspection inside compare is not required for this phase.

---

## Threshold Behavior

Using the blob demo or targeted test data, verify:

- [ ] small artifact stays `storage_kind=inline`
- [ ] large artifact becomes `storage_kind=blob`
- [ ] preview text is preserved in both cases
- [ ] `size_bytes` is populated in both cases
- [ ] `sha256` is populated in both cases

---

## Regression Checks

- [ ] Non-blob runs still behave normally
- [ ] Streaming run detail still behaves normally
- [ ] Compare page still behaves normally
- [ ] No new console errors in the browser
- [ ] No broken styling in light mode
- [ ] No broken styling in dark mode if supported

---

## Edge Cases

- [ ] Empty artifact payload does not crash rendering
- [ ] Blob-backed artifact with missing blob shows a clean error
- [ ] Large JSON payload renders without freezing the page
- [ ] Repeated expand/collapse does not reset loaded content unexpectedly

---

## Done Criteria

Blob storage is considered validated when:

- [ ] large artifacts are offloaded
- [ ] small artifacts remain inline
- [ ] run detail supports lazy artifact loading
- [ ] LLM and non-LLM artifacts are both inspectable
- [ ] blob-backed stream playback works
- [ ] compare does not regress
