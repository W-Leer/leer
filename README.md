# Leer

> The execution record for AI agents.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Next.js](https://img.shields.io/badge/frontend-next.js-black)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/W-Leer/leer/actions/workflows/ci.yml/badge.svg)](https://github.com/W-Leer/leer/actions/workflows/ci.yml)

Leer records what an AI agent actually did, as a durable, provider-agnostic
record you can inspect and compare. Each run answers:

- what happened, and why
- which tools and LLMs were called
- which inputs produced which outputs
- which intermediate artifacts existed (reasoning, retrieved context, tool results)
- which execution path was taken, and what the final result was

The record is the source of truth. It stays readable when providers change
their APIs, models are deprecated, or prompts and tool schemas change.

---

## How it works

```
your agent ── Leer SDK ──▶ API (FastAPI) ──▶ Postgres (+ blob storage)
                                   │
                                   └──▶ Web UI (Next.js): runs, run detail, compare
```

Every run is stored as four concepts:

| Concept      | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| **Run**      | One execution of a workflow, with its status and final output |
| **Step**     | A unit of work inside the run: an LLM call, a tool call, code |
| **Event**    | A lifecycle transition of a run or step (started, failed, …)  |
| **Artifact** | A captured payload: prompts, responses, streams, files, images |

OpenAI and Anthropic responses are normalized into one canonical LLM call
shape (`provider`, `model`, `input`, `output`, `usage`, `meta`), so the
run detail and compare views read the same way for both. Raw provider
payloads are kept as supplemental artifacts.

---

## What gets captured

- **LLM calls, automatically.** Wrap your client once. OpenAI Chat
  Completions and Responses (`create`, `stream`, `parse`) and Anthropic
  Messages (`create`, `stream`, `parse`, `beta.messages`) are then recorded
  as LLM steps.
- **Streaming.** Chunks are captured with timing (time to first chunk,
  stream duration), and assembled into the same canonical output a
  non-streamed call produces. The UI can play a recorded stream back at
  adjustable speed.
- **Tool calls.** Tool steps are linked to the LLM call that requested
  them, including unmatched and failed calls. Tools the provider ran
  itself (web search, code execution, MCP) are recorded and marked "run by
  provider".
- **Structured outputs, refusals, and reasoning.** You get parsed outputs,
  refusals with their category, thinking and reasoning blocks, and token
  usage, including cached tokens.
- **Multimodal artifacts.** Images, PDFs, and other files are captured.
  Large artifacts go to blob storage (local disk, S3, or Azure).
- **MCP, skills, and RAG.** Helpers record protocol metadata, capability
  identity, and retrieval phases (request, candidates, rerank, selected
  context).
- **Run compare.** You can diff two runs step by step: status, inputs,
  outputs, errors, and tool calls.

Current scope: Python SDK, OpenAI and Anthropic, synchronous clients.
Replay is not built. The record is designed so replay and diffing remain
possible later.

---

## Quick start

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 20.9+,
and Docker (or a local Postgres).

**1. Start Postgres**

```bash
docker run -d --name leer-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=leer \
  -p 5432:5432 \
  postgres:17
```

**2. Start the API** (terminal 1)

```bash
cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`; interactive docs are at `/docs`.

**3. Record some runs** (terminal 2)

```bash
cd apps/sdk-python
uv sync
uv run python ../../examples/demo_openai_wrapper.py
uv run python ../../examples/demo_compare.py
```

The examples use fake provider clients, so no API keys or network are needed.

**4. Start the UI** (terminal 3)

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000. Runs appear under `demo-project`. Pick two
runs to compare them.

The API has no authentication yet, so run it locally or on a trusted
network only. See [`SECURITY.md`](SECURITY.md).

---

## Using the SDK

```python
from openai import OpenAI

from leer import configure, step, trace
from leer.integrations.openai import wrap_openai_client

# The UI's runs list currently shows only "demo-project".
configure(api_base_url="http://127.0.0.1:8000", project_slug="demo-project")
client = wrap_openai_client(OpenAI())


@trace(workflow_name="support-agent")
def answer(question: str) -> str:
    with step("build_prompt", step_type="code") as s:
        messages = [{"role": "user", "content": question}]
        s.output = {"messages": messages}

    # Recorded automatically as an LLM step.
    response = client.chat.completions.create(model="gpt-4.1", messages=messages)
    return response.choices[0].message.content


answer("What is an execution record?")
```

For Anthropic, use `wrap_anthropic_client(Anthropic())` from
`leer.integrations.anthropic`. To record tool execution, use
`tool_step(name, tool_call_id=...)`. A wrapped client only records calls
made inside a `@trace` run; outside one, it behaves exactly like the
unwrapped client. The run is sent to the API when the traced function
returns. If that fails, the SDK prints a warning and never raises into your
code.

See [`apps/sdk-python/README.md`](apps/sdk-python/README.md) for the full
SDK surface.

---

## Examples

All examples live in [`examples/`](examples/). Run them from
`apps/sdk-python` with `uv run python ../../examples/<name>.py`.

| Example                       | Shows                                               |
| ----------------------------- | --------------------------------------------------- |
| `demo_agent.py`               | Minimal manual `trace` and `step` usage            |
| `demo_openai_wrapper.py`      | OpenAI wrapper, successful and failing calls        |
| `demo_anthropic_wrapper.py`   | Anthropic wrapper, successful and failing calls     |
| `demo_streaming.py`           | Streamed Anthropic calls with timing               |
| `demo_tool_calling.py`        | LLM → tool → LLM with `tool_step` linkage          |
| `demo_tool_lifecycle.py`      | Exact, heuristic, unmatched, and failed tool links |
| `demo_async_tool_fanout.py`   | Several tool calls fanned out from one LLM step    |
| `demo_structured_outputs.py`  | Structured output rendering across two runs        |
| `demo_outputs.py`             | Output shapes in the structured renderer           |
| `demo_multimodal.py`          | Image, PDF, and file artifacts                     |
| `demo_blob_storage.py`        | Inline and blob-backed artifacts in one run        |
| `demo_blob_stream_compare.py` | Comparing runs with blob-backed streams            |
| `demo_mcp_tracing.py`         | MCP metadata and capability identity               |
| `demo_rag_tracing.py`         | Retrieval phases and artifacts                     |
| `demo_compare.py`             | Three runs (two successes, one failure) to compare |

---

## Project structure

```
apps/
  api/          FastAPI ingestion + read API, Alembic migrations
  sdk-python/   Python SDK (leer) and provider wrappers
  web/          Next.js UI: runs list, run detail, compare
examples/       Runnable demos (fake clients, no API keys)
docs/
  00-product/       vision and positioning
  01-architecture/  data model, ingestion architecture
  02-decisions/     ADRs and scope decisions
  03-specs/         feature specs
  04-execution/     audits, QA signoffs, assessments
tasks/NOW.md    current goal and status
```

---

## Development

```bash
cd apps/sdk-python && uv run pytest -q    # SDK tests, incl. golden provider drift suites
cd apps/api && uv run pytest -q           # API tests (needs a migrated Postgres)
cd apps/web && bun test                   # web helper tests
cd apps/web && npm run build              # web build + typecheck
```

The SDK does not depend on `openai` or `anthropic`. Its unit tests use fake
clients. The golden drift suites validate recorded fixtures against the
real installed SDKs, which are dev dependencies. They cover both
streaming and non-streaming calls, so provider API changes surface as test
failures.

Contributor and agent guidelines are in [`AGENTS.md`](AGENTS.md). Current
status is in [`tasks/NOW.md`](tasks/NOW.md), and the roadmap is in
[`docs/04-growth/next-steps-roadmap.md`](docs/04-growth/next-steps-roadmap.md).

---

## Contributing

Issues and pull requests are welcome. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the project rules and how to run
the tests. Report vulnerabilities privately, as described in
[`SECURITY.md`](SECURITY.md).

---

## License

[MIT](LICENSE)
