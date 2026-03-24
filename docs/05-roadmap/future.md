# Leer — Future Roadmap

This document tracks ideas and features that are NOT part of the MVP but represent potential future directions for Leer.

---

## Core Principle

Leer should remain:
- simple
- developer-first
- focused on debugging AI workflows

Avoid feature bloat.

---

## 1. Replay Execution (Future)

### Idea
Re-run a previous execution with:
- same inputs
- modified prompt
- modified step

### Why
- debug regressions
- test prompt changes
- iterate faster

### Notes
- requires deterministic inputs
- requires artifact storage
- needs clean UX

Status: NOT MVP

---

## 2. Prompt & Artifact Visibility

### Idea
Expose:
- full prompt
- full response
- tool calls
- intermediate artifacts

### Why
- deeper debugging
- better understanding of failures

Status: Good candidate after launch

---

## 3. LLM Provider Integrations

### Idea
Adapters for:
- OpenAI
- Anthropic
- Bedrock

Auto-capture:
- prompts
- responses
- tokens

### Why
- reduce manual instrumentation
- improve developer experience

Status: Post-MVP

---

## 4. Security / Guardrails Layer (HIGH POTENTIAL)

### Idea
Intercept LLM calls:

Flow:
user → system → Leer (check prompt) → LLM → Leer (check response) → user

Features:
- detect sensitive data in prompts
- detect leaks in responses
- block unsafe calls
- optional local model for verification

### Why
- enterprise need
- strong monetization potential

### Notes
- must minimize false positives
- requires clear UX
- requires trust guarantees

Status: Future (Pro feature candidate)

---

## 5. Hosted Version (Monetization)

### Idea
Cloud product with:
- team dashboards
- shared runs
- history
- permissions

### Why
- monetize OSS
- easier onboarding

Status: Future

---

## 6. Advanced Diff

### Idea
- prompt diff
- token diff
- artifact diff

### Why
- deeper debugging

Status: After traction

---

## 7. Alerts / Monitoring

### Idea
- detect failures automatically
- notify developers

### Why
- production usage

Status: Later

---

## Summary

MVP focus:
- tracing
- UI
- diff

Everything else:
→ after user feedback
