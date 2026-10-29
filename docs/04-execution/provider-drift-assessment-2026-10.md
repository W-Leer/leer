# Provider Drift Assessment — October 2026

Re-assessment of OpenAI / Anthropic capture after ~4 months without changes to
the integrations (last provider work: June 2026). Findings are documented here
before any code changes, per `AGENTS.md`.

Date: 2026-10-29

Related docs:
- `docs/04-execution/provider-hardening-qa.md` (June signoff this re-checks)
- `docs/04-execution/structured-outputs-step-0-audit.md` (workstream A)
- `docs/04-execution/version-drift-step-0-audit.md` (workstream E)

---

## 1. What changed upstream

| SDK | June 2026 | Now | Breaking releases in between |
|---|---|---|---|
| `openai` | 2.43.0 | 3.41.0 | 3.0.0 — HTTPX2 replaces `httpx` |
| `anthropic` | 0.111.0 | 2.3.0 | 1.0.0 — HTTPX2 + minor breaks; 2.0.0 — API version `2026-10-21` |

Leer's SDK does not depend on either package; the wrappers duck-type the
clients and every test uses fakes. So nothing in CI runs against the real SDKs.
For this assessment both latest SDKs were installed in a throwaway environment
and probed directly.

## 2. What still works

- Every OpenAI surface Leer wraps still exists in 3.41.0:
  `chat.completions.{create,parse,stream}`, `responses.{create,parse,stream}`,
  `beta.chat.completions.{parse,stream}`.
- All six Anthropic drift fixtures validate against the current `Message` type,
  and the real SDK's `model_dump()` normalizes to exactly the committed goldens.
- The full SDK suite is green (726 tests).

## 3. Gaps found

Raw provider payloads are still preserved in the `llm_response` artifact in
every case below, so data is not lost outright. The issue is that the canonical
record (`metadata.llm`), which run-detail and compare read, is wrong or
incomplete.

### High

- **D-H1 — Anthropic helper methods are not recorded.** `_WrappedMessages` only
  intercepts `create()`. `messages.stream()` (the idiomatic streaming helper),
  `messages.parse()` (new structured-output helper with `output_format`), and
  everything under `client.beta.messages` pass through `__getattr__` to the raw
  SDK with no step and no warning. This also invalidates the workstream A
  assumption that "Anthropic has no parsed-object helper."
- **D-H2 — Some tool calls are missing from `output.tool_calls`.**
  OpenAI Responses `custom_tool_call` items are not treated as tool calls (the
  chat-completions path handles `custom`; the Responses path does not).
  Anthropic `server_tool_use` blocks (provider-run tools such as web search) are
  also absent. Both break "which tools were called" and tool linkage.
- **D-H3 — Responses `phase` is ignored.** Output messages now carry
  `phase` (`commentary` vs `final_answer`). All `output_text` is concatenated,
  so a commentary preamble is merged into `output.text`. Reproduced: a JSON
  final answer preceded by commentary yields `output_is_json = false`.

### Medium

- **D-M1 — Responses `function_call.namespace` is dropped.** Two tools named
  `search` in namespaces `github` and `jira` become indistinguishable.
- **D-M2 — New item/block types are labeled as generic files.** Unknown types
  fall back to a `file` media part ("unknown output item: …"). This now covers
  common types: OpenAI `reasoning`, `web_search_call`, `mcp_call`,
  `shell_call`, `code_interpreter_call`, …; Anthropic `web_search_tool_result`,
  `code_execution_tool_result`, `web_fetch_tool_result`, ….
- **D-M3 — Anthropic `stop_details` is dropped.** Refusals now carry a
  category (`stop_details.category`); it is not captured anywhere canonical.
- **D-M4 — OpenAI drift fixtures are not SDK-valid.** All 8 OpenAI fixtures fail
  `ChatCompletion` / `Response` validation because they omit envelope fields
  (`created`, `created_at`, `tools`, `tool_choice`, usage detail objects). The
  normalizer does not read these, but the corpus is less realistic than
  intended.

### Low

- **D-L1 — New usage fields are not captured:** reasoning tokens, cache-write
  counts, `compute_units` (OpenAI); `cache_creation`, `speed`,
  `server_tool_use`, `output_tokens_details` (Anthropic). Additive metadata.
- **D-L2 — HTTP client mismatch.** Both SDKs moved to HTTPX2; Leer still pulls
  in `httpx` for submission. Works, but adds a second HTTP stack to user apps.
- **D-L3 — Outdated model IDs.** `claude-sonnet-4-20250514` (8 uses in
  `examples/`) is no longer listed in `anthropic` 2.3.0. Harmless with the fake
  clients, but the planned live recorder needs current IDs.

### Docs

- `docs/04-growth/next-steps-roadmap.md` says workstreams A–E are "none
  started" (A is complete, E step 1 is done).
- `tasks/NOW.md` mentions neither A nor E.
- `AGENTS.md` names Provider Hardening as the active workstream.
- `README.md` links `assets/demo.gif` and `docs/05-roadmap/future.md`; neither
  exists.
- The drift fixtures README documents `tools/record_provider_fixtures.py`,
  which does not exist yet.

## 4. Proposed order

1. Docs refresh (no code).
2. D-H1 — instrument Anthropic `messages.stream()`, `messages.parse()`, and
   `beta.messages.*`.
3. D-H2, D-H3, D-M1 — Responses/Anthropic normalization fixes, each with new
   drift fixtures.
4. D-M2, D-M3 — typed classification of new item/block types; `stop_details`.
5. D-M4 + workstream E — make fixtures SDK-valid, add an optional SDK-type
   validation test, then the live recorder using current model IDs.

D-L1 to D-L3 are deferred unless they come up while doing the above.
