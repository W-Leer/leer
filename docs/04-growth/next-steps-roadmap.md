# Next Steps — Leer (Post Diff Feature)

You have completed:
- ingestion
- storage
- read API
- UI
- run comparison (diff)

This means Leer is now a **real product prototype**.

---

## ✅ Current status / candidate workstreams

Provider Hardening (OpenAI + Anthropic, Steps 0–4) is **complete** — see
`docs/04-execution/provider-hardening-qa.md`.

**Current focus (Oct 2026): provider drift follow-up.** Both SDKs had major
releases since June (`openai` 2.43 → 3.41, `anthropic` 0.111 → 2.3). The
re-assessment in `docs/04-execution/provider-drift-assessment-2026-10.md` found
capture gaps (unrecorded Anthropic `stream()`/`parse()`/`beta` calls, missing
tool calls, Responses `phase` mixing) and lists the fix order. Work that list
before starting B–D.

Workstreams to take support from "hardened" to "truly complete" (each starts
with a Step-0 audit and documents gaps before code, per `AGENTS.md`):

- **A. Structured-output validation** — ✅ **complete** (June 2026). `.parse()`
  and `.stream()` capture, canonical `output.parsed` / `meta.output_is_json`,
  UI surfacing, JSON-safe submission. See
  `docs/04-execution/structured-outputs-step-0-audit.md`. Anthropic's newer
  `messages.parse()` helper is tracked as D-H1 in the drift assessment.
- **B. Multimodal inputs** — verify images, image URLs, and file attachments
  capture correctly across both providers. Not started.
- **C. Multimodal outputs** — validate current/future output modalities
  (e.g. image generation) end to end into artifacts. Not started.
- **D. Long-running agent workflows** — multiple tool loops, nested tool calls,
  and large execution trees render and compare cleanly. Not started.
- **E. Provider version-drift monitoring** — 🟡 **step 1 of 3 done**: golden
  snapshot suite over 14 hand-authored fixtures
  (`apps/sdk-python/tests/test_provider_drift.py`). Remaining: streaming
  snapshots, and an opt-in recorder for real API payloads. See
  `docs/04-execution/version-drift-step-0-audit.md`.

Deferred provider-hardening items (documented, non-blocking) live in the QA
report §4 and the implementation plan: Responses streaming interleave ordering,
Anthropic `cache_creation_input_tokens`, OpenAI Responses `reasoning` →
generic block, async wrappers, and a web render-test harness.

> Note: the GitHub-launch / demo sections below predate the hardening work and
> are kept for distribution planning; treat the section above as the current
> engineering roadmap.

---

## 🎯 Immediate Goal

Turn Leer into something that:
- developers understand instantly
- is demoable in < 60 seconds
- can get GitHub traction

---

## 🚀 Step 6 — Make it Demo-Ready

### 1. Improve demo data

Create better examples:
- successful run
- failed run
- changed output run

Goal:
→ make comparison visually obvious

---

### 2. Improve output summaries

Right now summaries are raw JSON.

Improve:
- truncate long text
- format nicely
- extract meaningful preview

Example:
- instead of full JSON → short readable sentence

---

### 3. Clean UI details

Focus:
- spacing
- typography
- consistent labels

Do NOT redesign.
Just polish.

---

## 🚀 Step 7 — GitHub Launch Prep

### README.md

Add:
- what Leer is (1 sentence)
- GIF/demo
- quick start (3 steps)
- example code

---

### Example folder

Ensure:
- examples/demo_agent.py is clean
- easy to run
- produces multiple runs for comparison

---

### First demo script

You should be able to say:

1. start API
2. run demo script twice
3. open UI
4. compare runs

---

## 🚀 Step 8 — First Distribution

### Open source release

- make repo public
- post on:
  - Hacker News
  - Reddit (r/MachineLearning, r/LocalLLaMA)
  - Twitter/X

---

## 🧠 What NOT to build next

Avoid:
- auth
- multi-user
- replay execution
- complex UI
- infra scaling

---

## 🧭 What comes after

Once you get feedback:

### Option A (most likely)
- improve diff
- add prompt visibility
- add artifact viewer

### Option B (bigger step)
- replay execution

---

## 🏁 Summary

You are now at:

Logs → Observability → Diff ✅

Next:

👉 Distribution + Feedback
