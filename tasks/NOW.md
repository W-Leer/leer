# NOW

## Current Goal
Make Leer feel extremely strong and trustworthy as an observability product for OpenAI and Anthropic before expanding into replay or execution.

## Tasks

### Immediate next feature
- [x] Provider hardening pass for OpenAI and Anthropic — **COMPLETE (Steps 0–4)**.
  Assessed production-ready for the v1 observability scope. See QA signoff:
  `docs/04-execution/provider-hardening-qa.md` (plan:
  `tasks/provider-hardening-implementation-plan.md`). Candidate next
  workstreams are in `docs/04-growth/next-steps-roadmap.md`.

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
- [ ] Remove outdated roadmap references
- [ ] Refresh top-level project status docs
- [ ] Add a provider-support status matrix
- [ ] Add a real-world instrumentation cookbook

### Later, not now
- [ ] Replay / simulation design pass
- [ ] Execution engine design pass