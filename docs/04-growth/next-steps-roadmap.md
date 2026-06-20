# Next Steps — Leer (Post Diff Feature)

You have completed:
- ingestion
- storage
- read API
- UI
- run comparison (diff)

This means Leer is now a **real product prototype**.

---

## ✅ Current status / candidate workstreams (provider hardening complete)

Provider Hardening (OpenAI + Anthropic, Steps 0–4) is **complete** and assessed
production-ready for the v1 observability scope — see
`docs/04-execution/provider-hardening-qa.md`. Core LLM execution-record capture
for the two primary providers is largely done.

Candidate next workstreams to take that support from "hardened" to "truly
complete" (none started; each should begin with a Step-0 audit and document
gaps before code, per `AGENTS.md`):

- **A. Structured-output validation** — JSON-schema outputs, OpenAI structured
  outputs, and Anthropic tool-use structured responses, under both streaming
  and non-streaming. (Existing spec: `docs/03-specs/llm-instrumentation/06-structured-outputs.md`.)
- **B. Multimodal inputs** — verify images, image URLs, and file attachments
  capture correctly across both providers.
- **C. Multimodal outputs** — validate current/future output modalities
  (e.g. image generation) end to end into artifacts.
- **D. Long-running agent workflows** — multiple tool loops, nested tool calls,
  and large execution trees render and compare cleanly.
- **E. Provider version-drift monitoring** — a recorded-fixture regression suite
  that protects normalization against OpenAI/Anthropic API changes.

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
