# Tool Lifecycle — QA Checklist

QA signoff for the tool-calling lifecycle and linkage work (Steps 0–5).

---

## 1. Setup

- [ ] API running at `http://127.0.0.1:8000`
- [ ] Postgres running with migrations applied
- [ ] Run the demo:
  ```
  cd apps/sdk-python && uv run python ../../examples/demo_tool_lifecycle.py
  ```
- [ ] Confirm two runs created: `tool-lifecycle-demo-a` and `tool-lifecycle-demo-b`
- [ ] Open the UI at `http://localhost:3000`

---

## 2. Run detail — exact linkage

Open **Run A** (`tool-lifecycle-demo-a`).

- [ ] LLM step "planner" shows 3 tool calls
- [ ] `get_weather` (call_exact_1) shows **confidence = exact**
- [ ] `get_weather` shows **lifecycle = completed** (green badge)
- [ ] Click the jump arrow on `get_weather` tool call → navigates to the `get_weather` tool step
- [ ] On the `get_weather` tool step, back-link shows **exact** confidence badge
- [ ] Click the back-link → navigates back to the LLM "planner" step

Open **Run B** (`tool-lifecycle-demo-b`).

- [ ] `get_weather` (call_exact_2) shows **confidence = exact**
- [ ] `get_weather` shows **lifecycle = failed** (red badge)
- [ ] Tool step `get_weather` shows `status = failed`
- [ ] Error artifact visible on the failed tool step

---

## 3. Run detail — heuristic linkage

Open **Run A**.

- [ ] `lookup_city` (no id) shows **confidence = heuristic** (amber badge)
- [ ] `lookup_city` shows **lifecycle = completed**
- [ ] Jump arrow present — click navigates to the `lookup_city` tool step
- [ ] Tool step `lookup_city` shows heuristic back-link badge
- [ ] **Critical**: the linkage row does NOT disappear for this heuristic-only case
  (this was a known bug where `ToolLinkageDiff` returned null for steps with `tool_name` but no `tool_call_id`/`provider`/`model`)

Open **Run B**.

- [ ] `lookup_city` also shows **heuristic** confidence and **completed** lifecycle

---

## 4. Run detail — unmatched

Open **Run A**.

- [ ] `send_alert` (call_orphan_1) shows **lifecycle = unmatched** (neutral badge)
- [ ] `send_alert` shows **confidence = unlinked** (neutral badge)
- [ ] No jump arrow (nothing to jump to)
- [ ] No crash, no broken layout

---

## 5. Tool artifacts

Open **Run A**, expand the LLM "planner" step.

- [ ] LLM step contains `tool_call` artifacts (one per emitted call: 3 total)
- [ ] Each `tool_call` artifact has `tool_name`, `arguments`, `call_index` in its payload
- [ ] `tool_call` artifacts for `get_weather` and `send_alert` include `tool_call_id` in metadata
- [ ] `tool_call` artifact for `lookup_city` does not have `tool_call_id`

Open a tool step.

- [ ] `get_weather` tool step has `tool_request` and `tool_response` (or `tool_error` on Run B) artifacts
- [ ] Artifact metadata includes `tool_name` and (when applicable) `tool_call_id` and `parent_llm_step_id`
- [ ] Artifact JSON is inspectable without error

Blob safety (if applicable):

- [ ] If any tool output is large enough to be blob-backed, verify it loads correctly
- [ ] `ArtifactViewer` renders both inline and blob-backed artifacts without crash

---

## 6. Compare page

Open `/compare` and compare **Run A** vs **Run B**.

### Tool call alignment

- [ ] Tool calls section visible on the LLM "planner" step comparison
- [ ] Count badge shows `3 → 2`
- [ ] `get_weather` aligned side-by-side (by positional name — ids differ)
- [ ] `lookup_city` aligned side-by-side (by positional name)
- [ ] `send_alert` shows **"only in A"** label

### Diff highlighting

- [ ] `get_weather`: **args changed** badge visible (city: Paris vs London)
- [ ] `lookup_city`: **args changed** badge visible (nearest airport vs nearest train station)
- [ ] `changed` badge on the Tool calls section header

### Lifecycle in compare

- [ ] `get_weather` Run A: **completed** lifecycle badge
- [ ] `get_weather` Run B: **failed** lifecycle badge
- [ ] Lifecycle difference highlighted (ring or distinct color)
- [ ] `lookup_city` both sides: **completed** lifecycle badge (no highlight)

### Tool-step compare cards

- [ ] Tool step `get_weather` shows linkage section with **exact** confidence badge on both sides
- [ ] Tool step `lookup_city` shows linkage section with **heuristic** confidence badge
  - **Critical**: heuristic-only steps must NOT have their linkage section hidden
- [ ] Status diff visible: `get_weather` completed (A) vs failed (B)

### Insight

- [ ] Insight block appears with tool failure divergence or tool-count divergence message

---

## 7. Regression checks

- [ ] Non-tool LLM steps (from other demo runs) still render correctly
- [ ] Non-tool steps in compare still render correctly
- [ ] Compare page does not crash when comparing runs without tool calls
- [ ] No JavaScript console errors
- [ ] No broken layout in light mode
- [ ] No broken layout in dark mode (if supported)

---

## 8. Done criteria

- [ ] **Exact** linkage: visible in run detail with correct lifecycle and confidence
- [ ] **Heuristic** linkage: visible in run detail, linkage row does not disappear
- [ ] **Unmatched**: visible in run detail with unmatched/unlinked badges
- [ ] **Failed**: failed lifecycle visible in run detail and compare
- [ ] **Compare**: alignment, args diff, lifecycle diff, one-sided calls, confidence badges all work
- [ ] **Artifacts**: `tool_call`, `tool_request`, `tool_response`, `tool_error` inspectable
- [ ] **No regressions**: existing non-tool functionality unaffected

---

## Sign-off

| Area | Status | Notes |
|------|--------|-------|
| Run detail — exact | | |
| Run detail — heuristic | | |
| Run detail — unmatched | | |
| Run detail — failed | | |
| Tool artifacts | | |
| Compare — alignment | | |
| Compare — lifecycle | | |
| Compare — confidence | | |
| Compare — insight | | |
| Regressions | | |
