# NOW

## Current Goal
Make Leer's execution records extremely strong and trustworthy for OpenAI and Anthropic before expanding into replay or execution.

## Tasks

### Immediate next feature — provider drift follow-up (Oct 2026)
Both SDKs had major releases since June. Gaps and fix order:
`docs/04-execution/provider-drift-assessment-2026-10.md`.
- [x] Docs refresh (roadmap, NOW, AGENTS, README links)
- [x] D-H1 — record Anthropic `messages.stream()`, `messages.parse()`, `beta.messages.*`
  (also fixed D-H4: OpenAI `.stream()` + `get_final_*()` recorded empty output)
- [x] D-H5 — Anthropic `beta.messages.tool_runner` and `thread()`: every turn is
  now an LLM step (model calls used to bypass the wrapper)
- [ ] Record tools that `tool_runner` executes itself as `tool` steps (needs a
  design; see D-H5 in the assessment)
- [x] OpenAI `responses.compact()` recorded; canonical `compaction` part for
  both providers (ADR-003)
- [ ] OpenAI `responses.connect()` (WebSocket) — designed and decided, build
  after E step 3 (`docs/03-specs/platform/compaction-and-responses-websocket.md`)
- [x] D-H2 / D-H3 / D-M1 — Responses `custom_tool_call`, `phase` (commentary
  kept out of `output.text`), `namespace`; Responses streaming now matches
  non-streaming
- [x] D-M2 / D-M3 — provider-run tools as `provider_tool` parts (ADR-002),
  OpenAI `reasoning` as thinking, `meta.refusal_category`; also fixed D-M5
  (Anthropic streaming dropped server-tool blocks and merged text blocks)
- [x] D-M4 — all drift fixtures validate against the real SDK types (enforced by a test)
- [x] Workstream E step 2 — streaming golden suite replayed through the real SDKs
- [x] D-M6 — wider `input.params` for both providers (context, generation,
  tools, serving); Anthropic built-in tools keep their settings; `examples/`
  on current model IDs
- [ ] Workstream E step 3 — opt-in live recorder

### Recently completed
- [x] Provider hardening pass (Steps 0–4) — `docs/04-execution/provider-hardening-qa.md`
- [x] Workstream A, structured outputs — `docs/04-execution/structured-outputs-step-0-audit.md`
- [x] Workstream E step 1, golden drift suite — `docs/04-execution/version-drift-step-0-audit.md`

### Provider hardening — done
- [x] Validate OpenAI wrapper edge cases
- [x] Validate Anthropic wrapper edge cases
- [x] Ensure normalized LLM shape consistency across both providers
- [x] Harden streaming edge cases (sync↔streaming parity)
- [x] Harden tool-calling edge cases
- [x] Harden error / finish-reason / usage normalization
- [~] Multimodal edge cases — inputs + image/document outputs covered; broader
  multimodal validation tracked in the roadmap, not blocking.

### Observability UX
- [x] Project picker: `GET /v1/projects` + sidebar selection (was hardcoded to
  `demo-project`)
- [ ] Improve compare clarity for complex runs
- [ ] Improve artifact inspection UX
- [ ] Improve step-header density and badge readability
- [ ] Refine retrieval / MCP artifact inspection experience
- [ ] Improve filtering and scanability in run detail

### Validation
- [ ] Run end-to-end validation on tool lifecycle demo
- [ ] Run end-to-end validation on multimodal demo
- [ ] Run end-to-end validation on MCP demo
- [ ] Run end-to-end validation on RAG demo
- [ ] Validate mixed runs combining tools, multimodal, MCP, and retrieval

### Docs
- [x] Open-source prep: MIT license, CONTRIBUTING, SECURITY, CI, README rewrite,
  positioning aligned with AGENTS.md
- [ ] Remove outdated roadmap references
- [x] Refresh top-level project status docs
- [ ] Add a provider-support status matrix
- [ ] Add a real-world instrumentation cookbook

### Later, not now
- [ ] Replay / simulation design pass
- [ ] Execution engine design pass