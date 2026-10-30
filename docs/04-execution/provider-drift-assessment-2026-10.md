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
client internally, so its model calls bypass the wrapper. Tracked as D-H5
below.

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
  `mcp_approval_request`, `tool_search_call`, `*_call_output`
  items. Rare in output; revisit if they show up. (`compaction` got its own
  part later; ADR-003.)
- New fixtures: `anthropic__provider_run_search`,
  `anthropic__refusal_category`, `openai_responses__provider_run_search_mcp`
  (SDK-valid, current model IDs).

### Found while building the streaming suite (workstream E step 2)

Replaying fixture requests through the real SDK surfaced two upstream changes:

- **D-M6 — Anthropic request parameters changed.** `anthropic` 2.3
  `messages.create()` no longer accepts `temperature`, `top_p`, `top_k` or
  `output_format` (it raises `TypeError`); `output_format` moved into
  `output_config`. New parameters are not in `input.params`:
  `service_tier`, `speed`, `inference_geo`, `cache_control`, `container`,
  and on beta `context_management`, `compaction`, `fallbacks`,
  `mcp_servers`. The full request is still saved in the `llm_request`
  artifact, so nothing is lost; the canonical summary is incomplete. The same
  check shows long-standing omissions on OpenAI too (`reasoning_effort`,
  `tool_choice`, `parallel_tool_calls`, `previous_response_id`,
  `conversation`, `service_tier`, …). Widening the `input.params` allowlist
  is a design decision for both providers, deferred to its own item. Leer
  keeps recording `temperature` / `top_p` / `top_k` for older SDKs.
- **D-L3 (now confirmed):** `claude-sonnet-4-20250514` reached end-of-life on
  2026-06-15; the SDK warns on every call. The Anthropic fixtures now use
  `claude-sonnet-5-5`, and `anthropic__text` uses `stop_sequences` instead of
  `temperature`. `examples/` still use both and need the same update.

### D-M6 — done

Implemented as designed below; `tests/test_request_params.py` covers each
added and left-out parameter. Golden change: the `web_search` tool in
`anthropic__provider_run_search` now keeps `type` and `max_uses`. `examples/`
use `claude-sonnet-5-5`, and `demo_anthropic_wrapper.py` passes
`service_tier` instead of `temperature`. Older unit tests still use the
retired model ID as a plain string with fake clients; harmless.

### D-M6 — design

`input.params` records a request parameter when it changes what the model
sees, how it generates, which tools it may use, or which model / capacity
serves it. Identity, billing, storage, caching hints, diagnostics and
transport options stay out (they remain in the `llm_request` artifact).
Nothing is removed from the existing lists.

| Provider | Added | Left out |
|---|---|---|
| OpenAI chat | `reasoning_effort`, `verbosity`, `tool_choice`, `parallel_tool_calls`, `function_call`, `n`, `logit_bias`, `modalities`, `audio`, `prediction`, `web_search_options`, `service_tier`, `moderation` | `metadata`, `user`, `safety_identifier`, `store`, `stream_options`, `prompt_cache_*` |
| OpenAI Responses | `tool_choice`, `parallel_tool_calls`, `max_tool_calls`, `top_logprobs`, `previous_response_id`, `conversation`, `prompt`, `include`, `background`, `service_tier`, `context_management`, `moderation` | `metadata`, `user`, `safety_identifier`, `stream_options`, `prompt_cache_*`, `access_programs` |
| Anthropic | `tool_choice`, `service_tier`, `speed`, `container`, `context_management`, `compaction`, `thread`, `fallbacks`, `mcp_servers`, `betas` | `metadata`, `cache_control`, `diagnostics`, `inference_geo`, `fallback_credit_token`, `user_profile_id`, `workspace_id` |

`previous_response_id`, `conversation` and `thread` mean `input.messages` is
not the whole context. They are recorded as params now; a first-class
"continues from" field may be worth a separate decision later.

Also: Anthropic built-in tools (`web_search_*`, `code_execution_*`, …) keep
their `type` and settings in `input.tools`; only custom tools are reduced to
`name` / `description` / `input_schema`. Legacy OpenAI chat `functions` are
still not in `input.tools` (deprecated; left as is).

### D-M4 — done

- The 8 older OpenAI fixtures gained the envelope fields they lacked
  (`created`; `created_at`, `parallel_tool_calls`, `tool_choice`, `tools`,
  usage detail objects; message `status`; `output_text.annotations`).
- `test_fixture_is_valid_for_the_current_sdk` validates every fixture's
  response against `ChatCompletion`, `Response` or Anthropic `Message`, so an
  SDK upgrade that adds a required field fails loudly.
- One golden change per Responses fixture: `usage.cached_tokens` went from
  `null` to `0`. The real API always sends `input_tokens_details`, and `0`
  means "reported, no cache hit". The `null` ("not reported") case is still
  covered by the chat fixtures without `prompt_tokens_details` and by unit
  tests.

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

### D-H5 — Anthropic `tool_runner` and `thread()` record nothing (High) — done

Checked against `anthropic` 2.3.0, the latest release. Fixed as described
below. `tests/test_real_sdk_contract.py` drives the real `tool_runner` without
streaming, streamed, and streamed with `run_tools_eagerly`, plus
`thread().send()` / `.stream()`, and pass-through outside a trace. Each turn
is one LLM step under the caller's step, and streamed and non-streamed loops
produce the same canonical output.

**Finding.** `client.beta.messages` has two entry points the wrapper only
forwards through `__getattr__`: `tool_runner()` and `thread()`. Both build a
`BetaMessageThread` around the resource's own `_client`, which is the raw,
unwrapped client. Every turn then calls
`raw_client.beta.messages.create(...)`, so a whole tool loop produces no LLM
steps. Reproduced with the real SDK: a two-turn `tool_runner` run sent 2
requests and recorded 0 steps. `client.messages` (non-beta) has neither
method.

Thread turns send only the new messages, plus
`thread: {type: "create" | "continue", previous_message_id}`. Later turns
also omit `tools`. `thread` is already in `input.params` (D-M6), so each
recorded turn is accurate and shows which message it continues.

**Fix.** The wrapped `beta.messages` intercepts `tool_runner()` and
`thread()` and calls the real SDK method on a copy of the resource whose
`_client` is the wrapped client. The thread then sends every turn through
the instrumented `beta.messages.create()`, streaming or not. The SDK's
own runner, thread state, and return types are untouched. If the resource
has no `_client`, the call is forwarded unchanged, as before.

**Not in this fix: tools the runner executes.** The runner calls `@beta_tool`
functions itself (`_run_tool`, toolset members, eager execution while
streaming). Recording those as `tool` steps would mean patching private
runner methods or wrapping the user's tool objects, so it is a separate
design item. The model's requests are still visible as `output.tool_calls`,
and the results as `tool_result` blocks in the next turn's `input.messages`.

### Found while checking D-H5 against `openai` 3.41.0 (not triaged)

`openai` has no helper like `tool_runner`. Its Python SDK has no tool loop.
But `client.responses` has two methods the wrapper forwards unrecorded:

- **`responses.compact()`** compacts a conversation. It runs a model over the
  context and returns the compacted items. A run that uses it would silently
  lose a model call from its record.
- **`responses.connect()`** opens a persistent Responses API WebSocket. Turns
  sent over it bypass `responses.create()` entirely. It needs a separate
  capture path, like a stream with no HTTP response.

Both need a design decision before code.

**Status.** Design: `docs/03-specs/platform/compaction-and-responses-websocket.md`.

- **`compact()` — done.** Recorded as an `llm` step like `create()`.
  Compaction now has a canonical `compaction` content part on both providers
  (ADR-003): OpenAI `compaction` items (from `compact()` and from automatic
  compaction in `create()`), and Anthropic beta `compaction` blocks with their
  readable summary. The user messages `compact()` echoes count as
  `retained_messages`, not output. Also fixed: Anthropic streaming ignored
  `compaction_delta`, so a streamed compaction block lost its summary. Covered
  by real-SDK contract tests and the `openai_responses__auto_compaction`
  golden fixture.
- **`connect()` — designed, not built.** Decisions are in the spec: automatic
  successor responses are their own steps, steering is an event plus successor
  input, unfinished responses are `failed`; built after the live recorder.
