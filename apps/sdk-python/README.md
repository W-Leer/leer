# leer (Python SDK)

Records AI agent runs as Leer execution records (Run → Step → Event →
Artifact) and sends them to the Leer API.

- Python 3.11+. The only runtime dependency is `httpx`.
- The SDK does not depend on `openai` or `anthropic`. The wrappers work
  with the client objects you already have.

## Install

The package is not published yet. Install it from this repo:

```bash
# inside this repo (development)
cd apps/sdk-python
uv sync

# from another project
uv add --editable /path/to/leer/apps/sdk-python
# or: pip install -e /path/to/leer/apps/sdk-python
```

## Configure

```python
from leer import configure

configure(api_base_url="http://127.0.0.1:8000", project_slug="my-project")
```

The project is created on first ingest and appears in the web UI's project
picker. The run is sent to the API in one
request when the outermost `@trace` function returns. If sending fails,
the SDK prints a warning to stderr and does not raise.

## Runs and steps

```python
from leer import step, trace


@trace(workflow_name="summarize")
def summarize(text: str) -> dict:
    with step("clean_input", step_type="code") as s:
        s.input = {"text": text}
        cleaned = text.strip()
        s.output = {"text": cleaned}
    return {"summary": cleaned[:100]}
```

- `@trace(workflow_name, metadata=None)` creates a run. Nested `@trace`
  calls join the outer run.
- `step(name, step_type="code", metadata=None, input=None)` is a context
  manager. Set `.input` and `.output` on the yielded step. An exception
  marks the step as failed and re-raises. If the exception escapes the
  `@trace` function, the run is marked as failed too.

## LLM calls (OpenAI and Anthropic)

```python
from anthropic import Anthropic
from openai import OpenAI

from leer.integrations.anthropic import wrap_anthropic_client
from leer.integrations.openai import wrap_openai_client

openai_client = wrap_openai_client(OpenAI())
anthropic_client = wrap_anthropic_client(Anthropic())
```

Inside a `@trace` run, every call through a wrapped client becomes an
`llm` step. The step holds the request, the normalized response, usage,
timing, and the raw provider payload as artifacts. Outside a run, the
wrapped client behaves exactly like the original.

| Provider  | Recorded surfaces |
| --------- | ----------------- |
| OpenAI    | `chat.completions.create` / `.stream` / `.parse` (also under `beta.chat`), `responses.create` / `.stream` / `.parse` |
| Anthropic | `messages.create` / `.stream` / `.parse`, the same under `beta.messages`, and every turn of `beta.messages.tool_runner` / `beta.messages.thread` |

Both providers normalize into one canonical shape (`NormalizedLLMCall` in
`leer/integrations/normalize.py`). That shape carries text, tool calls,
structured output (`output.parsed`), refusals, reasoning and thinking,
provider-run tools, and usage, including cached tokens. Streamed calls
produce the same canonical output as non-streamed calls, plus the
captured chunks and their timing.

Not recorded yet:
- async clients (`AsyncOpenAI`, `AsyncAnthropic`);
- the tool functions that `tool_runner` runs itself. Each model turn is an
  LLM step, and the tool requests and results appear in those turns, but
  there are no separate `tool` steps.

## Tool calls

```python
from leer import tool_step

with tool_step("get_weather", tool_call_id="call_123",
               source_provider="openai", source_model="gpt-4.1") as s:
    s.input = {"city": "Paris"}
    s.output = get_weather("Paris")
```

`tool_step` creates a `tool` step linked to the LLM call that requested it
through `tool_call_id`. The request and response artifacts are built from
`.input` and `.output`.

## Artifacts

```python
from leer import attach_artifact, create_binary_artifact, create_json_artifact

attach_artifact(create_json_artifact("retrieved_docs", data={"ids": [1, 2]}))
attach_artifact(create_binary_artifact("chart", data=png_bytes, mime_type="image/png"))
```

`attach_artifact` attaches to the current step, or to the run if no step
is active. `create_text_artifact` is also available. Large payloads are
stored in blob storage by the API.

## MCP, skills, and RAG helpers

- Metadata builders: `mcp_metadata`, `capability_metadata`,
  `retrieval_metadata`, `retrieval_output_summary`.
- MCP artifacts: `create_mcp_request_artifact`,
  `create_mcp_response_artifact`, `create_mcp_error_artifact`.
- Retrieval artifacts: `create_retrieval_request_artifact`,
  `..._candidates_artifact`, `..._rerank_artifact`,
  `..._selected_artifact`, `..._context_artifact`.

See `examples/demo_mcp_tracing.py` and `examples/demo_rag_tracing.py`.

## Tests

```bash
uv run pytest -q
```

Unit tests use fake clients. The real `openai` and `anthropic` packages
are dev dependencies only, used by the contract tests and the golden
drift suites (`tests/test_provider_drift.py`,
`tests/test_provider_drift_streaming.py`). The drift suites check
recorded provider payloads against the installed SDKs. See
`tests/fixtures/provider_payloads/README.md`.
