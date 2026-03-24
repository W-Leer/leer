# Leer

> Debug AI workflows like Git.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Next.js](https://img.shields.io/badge/frontend-next.js-black)
![License](https://img.shields.io/badge/license-MIT-green)

Leer is an open-source devtool to **trace, compare, and debug AI runs**.

---

## ✨ Why Leer?

AI workflows are **non-deterministic**.

- outputs change
- failures are hard to reproduce
- debugging is painful

Leer makes it obvious:

- what changed
- what broke
- where it broke

---

## ⚡ What you get

### 🔍 Trace everything

Capture runs and steps with minimal instrumentation.

### 🔁 Compare runs like a diff

- output differences
- step-level changes
- failures vs success

### ❌ Debug failures instantly

- see failing step
- see error
- compare with working run

---

## 🎬 Demo

![Demo](./assets/demo.gif)

---

## 🚀 Quick demo (60 seconds)

```bash
# start backend
cd apps/api
uv run uvicorn app.main:app --reload

# run demo
cd apps/sdk-python
uv run python ../../examples/demo_compare.py

# start UI
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000

---

## 🧰 Full local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Postgres (or Docker)
- uv

---

### Start Postgres (Docker)

```bash
docker run -d \
  --name leer-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15
```

---

### Environment

Create:

```bash
apps/api/.env
```

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/leer
```

---

### Migrations

```bash
cd apps/api
uv run alembic upgrade head
```

---

### Start backend

```bash
uv run uvicorn app.main:app --reload
```

---

### Start frontend

```bash
cd apps/web
npm install
npm run dev
```

---

## 🐍 Using the Python SDK

```bash
cd apps/sdk-python
uv pip install -e .
```

### Example

```python
from leer import configure, trace, step

configure(
    api_base_url="http://localhost:8000",
    project_slug="demo-project",
)

@trace(workflow_name="my-agent")
def run():
    with step("draft_prompt", step_type="code"):
        prompt = "Summarize this"

    with step("llm_call", step_type="llm"):
        return {
            "summary": [
                "AI agents are non-deterministic",
                "Leer provides execution traces",
                "Replay enables debugging"
            ]
        }

run()
```

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
  api/
  web/
  sdk-python/

examples/
  demo_compare.py
```

---

## 🛣 Roadmap

See: docs/05-roadmap/future.md

---

## 💡 Philosophy

- simple > complex  
- clarity > abstraction  
- debugging > automation  

---

## 🤝 Contributing

Contributions welcome.

---

## 📄 License

MIT
