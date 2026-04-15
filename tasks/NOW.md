# NOW

## Current Goal
Make Leer feel extremely strong and trustworthy as an observability product for OpenAI and Anthropic before expanding into replay or execution.

## Tasks

### Immediate next feature
- [ ] Provider hardening pass for OpenAI and Anthropic

### Provider hardening
- [ ] Validate OpenAI wrapper edge cases
- [ ] Validate Anthropic wrapper edge cases
- [ ] Ensure normalized LLM shape consistency across both providers
- [ ] Harden streaming edge cases
- [ ] Harden tool-calling edge cases
- [ ] Harden multimodal edge cases
- [ ] Harden error / finish-reason / usage normalization

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