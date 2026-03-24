# Leer

> Debug AI workflows like Git.

Leer is an open-source devtool to **trace, compare, and debug AI runs**.

---

## ✨ Why Leer?

AI workflows are **non-deterministic**.

- outputs change
- failures are hard to reproduce
- debugging is painful

Leer makes it simple to:

- trace execution step-by-step
- compare runs like a diff
- understand what changed instantly

---

## ⚡ What you can do

### 🔍 Trace your workflows

Instrument your code with minimal effort:

```python
from leer import trace, step

@trace()
def my_agent():
    draft_prompt()
    call_llm()
```

---

### 🔁 Compare runs

See exactly what changed between two executions:

- output differences
- step-level changes
- failures vs success

Like a **Git diff for AI runs**.

---

### ❌ Debug failures instantly

Identify:
- which step failed
- what error occurred
- how it differs from a working run

---

## 🚀 Quick start

### 1. Start the API

```bash
cd apps/api
uv run uvicorn app.main:app --reload
```

---

### 2. Run the demo

```bash
cd apps/sdk-python
uv run python ../../examples/demo_compare.py
```

This creates:
- a successful run
- a changed successful run
- a failed run

---

### 3. Open the UI

```bash
cd apps/web
npm run dev
```

Then open your browser and explore the runs.

---

## 🎬 Demo

(Insert GIF or video here)

Suggested flow:
1. open a run
2. compare two successful runs → see output diff
3. compare failed vs successful → see error and step diff

---

## 🧠 How it works

Leer captures:

- runs
- steps
- outputs
- errors

Then lets you:

- visualize execution
- compare runs
- debug faster

---

## 📦 Project structure

```
apps/
  api/           # FastAPI backend
  web/           # frontend UI
  sdk-python/    # Python SDK

examples/
  demo_compare.py
```

---

## 🛣 Roadmap

Planned:

- replay execution
- prompt + artifact visibility
- LLM provider integrations
- security / guardrails layer
- hosted version

See: docs/05-roadmap/future.md

---

## 💡 Philosophy

Leer is built for developers.

- simple > complex
- clarity > abstraction
- debugging > automation

---

## 🤝 Contributing

Contributions welcome.

---

## 📄 License

MIT
