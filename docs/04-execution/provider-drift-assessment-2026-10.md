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

## 5. Progress

### D-H1 — done (plus D-H4, found while fixing it)

Reproduced against the real SDKs (installed in a throwaway venv, driven over an
in-memory HTTP transport) before fixing:

| Call | Before |
|---|---|
| OpenAI `.stream()`, iterating events | correct |
| OpenAI `.stream()` + `get_final_completion()` / `until_done()` | step "completed" with **empty output** |
| Anthropic `messages.stream()` (any consumption) | no step |
| Anthropic `messages.parse()` | no step |
| Anthropic `beta.messages.*` | no step |

**D-H4 (new, High):** the OpenAI `.stream()` wrapper from June only observed
events the caller iterated through our proxy. The SDK's `until_done()` /
`get_final_*()` read the stream internally, so the step finished with an empty
record. This was worse than a missing step because it looked successful.

Fix:
- Both stream-helper wrappers now route the SDK stream's internal `_iterator`
  through the existing `StreamCollector`, so every consumption style is
  observed, and return the genuine SDK stream object. If `_iterator` is ever
  missing they fall back to the previous proxy.
- Anthropic `_WrappedMessages` now intercepts `create`, `parse` and `stream`,
  for both `client.messages` and `client.beta.messages`.
- `normalize_anthropic` reads `parsed_output` from `parse()` text blocks into
  `output.parsed`, and records `output_format` / `output_config` in
  `input.params`.
- `MessageStream`'s synthesized convenience events (`text`, `thinking`, …) are
  skipped instead of being logged as unknown.
- `_to_dict` dumps SDK models with `warnings=False`; `ParsedResponse` otherwise
  printed Pydantic serializer warnings into the caller's logs.
- `openai` and `anthropic` are now dev dependencies, and
  `tests/test_real_sdk_contract.py` (18 tests) drives the real SDKs offline.

Still not recorded: Anthropic `beta.messages.tool_runner`. It calls the raw
client internally, so its model calls bypass the wrapper. Track separately.

### D-H2 (client-run tools), D-H3, D-M1 — done

- **D-H3:** Responses `message` items with `phase: "commentary"` are kept out
  of `output.text` and `output_is_json`, unless the response has no other
  text. Every text block keeps its `phase` in `output.content`, so the
  commentary is still in the record.
- **D-M1:** `function_call.namespace` is kept on the canonical tool call and in
  the step's tool-call summary. Run-detail and compare show `namespace.name`
  (for example `github.search`), and compare pairs calls by that label.
- **D-H2, client-run part:** Responses `custom_tool_call` items are now tool
  calls (`input` is parsed the same way as `arguments`), matching the
  chat-completions `custom` handling.
- **D-H2, provider-run part, moved to D-M2:** Anthropic `server_tool_use` and
  OpenAI `web_search_call` / `mcp_call` are executed by the provider, so no
  local tool step will ever link to them. Putting them in `output.tool_calls`
  would show them as "unmatched" in tool linkage. They need a design decision
  together with the other new item types.

**Streaming bug found while testing (fixed):** a streamed Responses call
rebuilt its output from deltas. That dropped `phase`, `namespace` and
`custom_tool_call` and reordered items, so streamed and non-streamed records
differed. The stream wrapper now normalizes the full `response` carried by the
terminal event (`response.completed` / `incomplete` / `failed`), and only
falls back to reassembling deltas when that event is missing. This also
resolves the old "Responses streaming interleave ordering" item whenever a
terminal event arrives.

New fixtures: `openai_responses__commentary_phase`,
`openai_responses__namespaced_tool_calls`, `openai_responses__custom_tool_call`.
They are SDK-valid; the 8 older OpenAI fixtures are still covered by D-M4. A
real-SDK test checks `.stream()` and `create(stream=True)` against
`create()` for the same response.

### D-M2, D-M3, D-M5 — done

Design: ADR-002 (`provider_tool` content part; OpenAI `reasoning` →
thinking; caller-run OpenAI tools → tool calls).

- **D-M2:** OpenAI `web_search_call`, `file_search_call`,
  `code_interpreter_call`, `mcp_call` and Anthropic `server_tool_use` /
  `mcp_tool_use` (plus their `*_tool_result` blocks, merged by `tool_use_id`)
  become `provider_tool` parts, never `tool_calls`. OpenAI `reasoning` becomes
  `thinking` / `redacted_thinking`. `computer_call`, `local_shell_call`,
  `shell_call` and `apply_patch_call` are tool calls. Anthropic
  `container_upload` is a `file` part with a `provider_file` source.
  Run-detail and compare show provider tools as "run by provider".
- **D-M3:** `meta.refusal_category` is added (all goldens gained
  `"refusal_category": null`). The run page's refusal badge shows it.
- **D-M5:** fixed as described below; real-SDK tests check streamed and
  non-streamed Anthropic records are equal for server tools and refusals.
- Still falling back to `file`: OpenAI `mcp_list_tools`,
  `mcp_approval_request`, `compaction`, `tool_search_call`, `*_call_output`
  items. Rare in output; revisit if they show up.
- New fixtures: `anthropic__provider_run_search`,
  `anthropic__refusal_category`, `openai_responses__provider_run_search_mcp`
  (SDK-valid, current model IDs).

**D-M5 (new, High), found while scoping D-M2:** Anthropic streaming rebuilds
the message from only thinking, joined text, and `tool_use`. Streamed
`server_tool_use` and result blocks are dropped, separate text blocks are
glued together without a separator, text/tool order is lost, and
`stop_details` is missing. Fix: rebuild each content block by its stream
index the way the SDK does, falling back to the old reassembly only if no
block events arrived.

**D-M3 design:** add `meta.refusal_category` (additive, provider-agnostic;
`None` for OpenAI, which has no categories). Anthropic
`stop_details.explanation` becomes the refusal text when the model returned
no text.
