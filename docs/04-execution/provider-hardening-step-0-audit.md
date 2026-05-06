# Provider Hardening — Step 0 Audit

Factual audit of Leer's current provider support for OpenAI and Anthropic, focused on hardening the observability layer before adding broader provider depth.

This is the execution audit for the provider-hardening workstream.

Related source docs:
- `docs/03-specs/platform/provider-hardening.md`
- `tasks/provider-hardening-implementation-plan.md`

---

## Goal of this audit

Establish the exact current state of provider support so the next implementation steps target real gaps instead of assumed ones.

This audit should answer:

1. What already works reliably for OpenAI and Anthropic?
2. Where are the wrappers inconsistent with each other?
3. Which provider paths are covered only partially?
4. Which behaviors are fragile under malformed, partial, or evolving payloads?
5. What can be improved without schema changes?
6. What should be treated as hardening vs new feature work?

---

## Scope

This audit is about **provider hardening**, not replay, not new providers, and not major product expansion.

In scope:
- OpenAI wrapper behavior
- Anthropic wrapper behavior
- request/response normalization consistency
- streaming collector behavior
- artifact creation consistency
- metadata/output_summary consistency
- malformed/partial payload handling
- compare/run-detail assumptions that depend on provider shape
- test coverage quality and missing edge cases

Out of scope:
- replay execution
- adding Gemini / Bedrock / Groq / etc.
- new DB schema design unless truly required
- enterprise auth / permissions / tenancy topics

---

## What to inspect

### 1. Wrapper entrypoints

Audit the current provider integrations and document:
- wrapper surface area
- sync vs async support
- chat vs responses/messages APIs
- streaming vs non-streaming paths
- where `_enrich_step` is called
- where request/response artifacts are created
- where normalization happens

Expected code areas to inspect:
- `apps/sdk-python/leer/integrations/openai.py`
- `apps/sdk-python/leer/integrations/anthropic.py`
- `apps/sdk-python/leer/integrations/streaming.py`
- `apps/sdk-python/leer/integrations/normalize.py`

Questions:
- Are the OpenAI and Anthropic wrappers conceptually parallel?
- Are there any paths that bypass normalization or artifact creation?
- Are there any provider-specific branches that now behave differently enough to cause drift?

### 2. Canonical normalized shape

Audit whether both providers consistently populate the canonical normalized model:
- `provider`
- `model`
- `input.system`
- `input.messages`
- `input.tools`
- `input.params`
- `output.text`
- `output.tool_calls`
- `output.content_blocks`
- `usage`
- `meta`

Questions:
- Do OpenAI and Anthropic produce comparable shapes for equivalent scenarios?
- Are missing fields normalized to consistent null/empty defaults?
- Are `tool_calls`, `content_blocks`, and summaries aligned enough for compare and run detail?
- Are there still places where raw provider structure leaks into product logic?

### 3. Output summaries and metadata

Audit consistency of:
- `input_summary`
- `output_summary`
- `metadata["llm"]`
- top-level metadata such as provider/model/stream info

Questions:
- Are summaries compact, stable, and compare-friendly?
- Do both providers include equivalent summary detail for:
  - text
  - tool calls
  - media presence
  - token usage
- Are there provider-specific omissions that make compare weaker on one side?
- Does any important debugging information exist only inside raw provider payloads but not in normalized metadata?

### 4. Streaming behavior

Audit streaming support by provider and endpoint.

Questions:
- Which APIs support streaming today?
- Does the stream collector preserve:
  - final text
  - tool calls
  - finish reason
  - usage if available
  - multimodal pieces when applicable
- Are partial/failure cases handled safely?
- Is final aggregated output equivalent to non-streaming output for the same logical response?
- Are stream artifacts/summaries/metadata consistent across providers?

### 5. Tool-calling parity

Audit provider parity around tool calls:
- normalized `id`
- normalized `name`
- normalized `arguments`
- summary enrichment (`id`, `arguments_hash`)
- run-detail visibility
- compare visibility

Questions:
- Are OpenAI chat completions, OpenAI responses, and Anthropic tool-use all equally hardened now?
- Are there provider paths that still drop ids, names, or malformed args?
- Are invalid JSON args handled consistently?
- Are tool call artifacts created consistently regardless of provider path?

### 6. Multimodal parity

Audit current multimodal coverage for OpenAI and Anthropic.

Questions:
- Which output media shapes are supported per provider?
- Which are normalized only vs normalized + materialized?
- Are URL/provider-file/base64 cases handled clearly and safely?
- Are there provider-specific multimodal paths likely to regress if payload shape shifts?
- Are summaries and `content_blocks` robust enough for compare and run detail?

### 7. Artifact consistency

Audit artifact creation across wrappers.

Questions:
- Do both providers always create `llm_request` and `llm_response` artifacts?
- Do streaming paths consistently create `llm_stream` artifacts?
- Do tool call paths consistently create `tool_call` artifacts?
- Do multimodal paths consistently create media artifacts when bytes are available?
- Is artifact ordering relied upon anywhere fragilely in tests or UI?
- Are artifact metadata fields consistent enough across providers for future filtering and debugging?

### 8. Failure handling and malformed payload resilience

Audit what happens when payloads are incomplete, malformed, or surprising.

Questions:
- What if a provider omits model, usage, finish reason, or content?
- What if tool arguments are invalid JSON?
- What if content blocks are empty or unknown?
- What if streaming terminates early?
- What if request/response serialization is only partially possible?
- Do wrappers fail closed (capture as much as possible without crashing observability)?

This section should explicitly identify:
- known brittle assumptions
- known provider-shape assumptions
- test gaps around malformed payloads

### 9. Frontend assumptions on provider data

Audit the UI for hidden assumptions that depend on current provider behavior.

Expected code areas to inspect:
- `apps/web/src/components/llm-step-detail.tsx`
- `apps/web/src/app/compare/page.tsx`
- `apps/web/src/components/artifact-viewer.tsx`
- related helpers in `apps/web/src/lib/*`

Questions:
- Does run detail assume fields only one provider currently sets?
- Does compare depend on summary shape that is only hardened for some paths?
- Are null/empty states safe when provider metadata is sparse?
- Are there any places where provider-specific values are rendered without normalization guards?

### 10. Test coverage and gaps

Audit the current tests for OpenAI and Anthropic.

Expected areas:
- `apps/sdk-python/tests/test_openai_wrapper.py`
- `apps/sdk-python/tests/test_anthropic_wrapper.py`
- `apps/sdk-python/tests/test_normalize.py`
- `apps/sdk-python/tests/test_multimodal_normalize.py`
- any stream/tool/async-related test files

Questions:
- What is strongly covered today?
- What is under-tested?
- Which tests are implementation-detail fragile rather than behavior-focused?
- Are there parity tests that directly compare equivalent OpenAI vs Anthropic normalized outputs?
- Are there edge-case tests missing for malformed or partial provider payloads?

---

## Output format for the audit

Write the audit as a factual document with these sections:

### 1. What already works well

Summarize the stable, already-shipped provider support that does not need redesign.

### 2. Provider inconsistencies

List meaningful OpenAI vs Anthropic inconsistencies, especially ones visible in:
- normalization
- summaries
- artifacts
- streaming
- multimodal
- compare behavior

### 3. Fragile assumptions / hardening gaps

Document exact weak spots, including:
- payload shape assumptions
- malformed input/output edge cases
- summary drift
- artifact drift
- UI assumptions

### 4. Schema/API impact

Directly answer:
- Can Step 1 start without schema changes?
- Do any hardening tasks require backend migrations?
- Are all likely improvements SDK/frontend-only?

### 5. Recommended Step 1

Give the next concrete step for provider hardening.

This should likely be one focused slice such as:
- normalization parity and safe defaults
- malformed payload hardening
- summary consistency
- streaming parity fixes

The recommendation must be narrow enough to implement cleanly.

---

## Strong preferences for this workstream

- Prefer **hardening existing OpenAI + Anthropic coverage** over adding new provider breadth.
- Prefer **canonical consistency** over provider-specific patchwork.
- Prefer **safe fallback behavior** over brittle “perfect” parsing.
- Prefer **behavioral tests** over tests that depend on artifact ordering or incidental structure.
- Prefer **no schema changes** unless the audit proves one is unavoidable.

---

## Explicit questions this audit should answer

1. Is there any provider path today that does not reliably produce a normalized LLM shape?
2. Is there any provider path today that does not reliably produce request/response artifacts?
3. Are summaries equally compare-friendly across OpenAI and Anthropic?
4. Is streaming materially less reliable on one provider path than the other?
5. Are multimodal output paths hardened enough for production use, or only for happy-path demos?
6. What are the top 3 hardening gaps with the best debugging-value-per-effort ratio?
7. Can Step 1 begin with zero schema changes?

---

## Done condition for Step 0

Step 0 is complete when this file contains:
- a factual current-state audit
- concrete hardening gaps
- a clear statement on schema-change necessity
- a recommended narrow Step 1

