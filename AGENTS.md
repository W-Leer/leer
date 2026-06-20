# AGENTS.md

Guide for AI coding agents (Cursor, Codex, etc.) working on Leer. This file is
always in context — read it first; it replaces per-session re-explanation.

---

## What Leer is

Leer is an **execution-record system** for AI agents. It is **not** observability,
not logging, not tracing, not prompt management. The execution record is the
**source of truth** and must answer:

- what happened, and why
- which tools and LLMs were called
- what inputs produced what outputs
- what intermediate reasoning artifacts existed
- what execution path was taken, and the final result

The record must stay useful even when providers change APIs, models are
deprecated, prompts change, or tool schemas change.

---

## Read first (where the real context lives)

Don't ask the user to re-explain the project — read these:

- **Product**: `docs/00-product/vision.md`, `docs/00-product/overview.md`, `docs/00-product/positioning.md`
- **Architecture**: `docs/01-architecture/data-model.md`, `docs/01-architecture/ingestion-architecture.md`
- **Scope / decisions**: `docs/02-decisions/provider-scope-and-priorities.md` + ADRs in `docs/02-decisions/`
- **Current goal & status**: `tasks/NOW.md`
- **Active/most-recent workstream — Provider Hardening**: spec `docs/03-specs/platform/provider-hardening.md`, plan `tasks/provider-hardening-implementation-plan.md`, QA signoff `docs/04-execution/provider-hardening-qa.md`
- **Editing provider code?** The load-bearing canonical contracts are enforced by `.cursor/rules/provider-integrations.mdc` (auto-loads for `apps/sdk-python/leer/integrations/**`).

Specs live in `docs/03-specs/`, execution audits/QA in `docs/04-execution/`.
Treat docs as living state and rules as durable truth — read docs for "where
things are now," follow rules for invariants.

---

## Canonical model (do not invent new concepts)

Four concepts: **Run → Step → Event → Artifact**. Provider responses normalize
into one canonical `NormalizedLLMCall` shape
(`apps/sdk-python/leer/integrations/normalize.py`). Product surfaces (run-detail,
compare, exports) read the canonical shape; raw provider payloads are
supplemental and live in artifacts/metadata.

---

## Hard constraints

- **Provider-agnostic + canonical-first.** OpenAI and Anthropic normalize to the
  same shape. Provider specifics may live in metadata but must never be required
  to understand a run.
- **Capture over replay.** Priority order: accurate capture → consistent
  normalization → stable records. Design so replay/diffing stay *possible* later,
  but never compromise capture quality for replay, and do not build replay now.
- **Streaming ↔ non-streaming parity.** A streamed and a non-streamed response
  must produce equivalent canonical output unless the provider fundamentally
  exposes different information.
- **Additive only.** No schema breaks, no step-type changes, no changing
  historical behavior except to fix a bug. Prefer additive metadata.
- **OpenAI + Anthropic only.** Optimize these two first; don't broaden providers
  in the current pass.
- **No architecture redesign, no unrelated features, no provider-specific UI**
  unless genuinely unavoidable.
- **Document gaps before implementing.** Write the finding down (audit / QA /
  plan) before changing code.

---

## Workflow

1. Before major code, check for a spec in `docs/03-specs/`; if none exists,
   create one. When you change structure, update docs and add an ADR in
   `docs/02-decisions/`.
2. Keep changes small and focused. Clarity over cleverness, typed Python, small
   functions, minimal dependencies, local-first, no magic behavior.
3. Add tests for stateful logic and for any weak spot you touch; keep the suite
   green.

### Commands

- SDK tests: `cd apps/sdk-python && uv run pytest -q`
- Web helper tests: `cd apps/web && bun test`
- Web build/typecheck: `cd apps/web && npm run build`
