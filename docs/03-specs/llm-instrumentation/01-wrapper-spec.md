# Leer — LLM Wrapper Spec

## Purpose
Provide first-class, explicit wrappers for LLM providers (OpenAI, Anthropic) to:
- reduce instrumentation friction
- capture rich provider-aware data
- normalize data for UI
- preserve raw payloads for debugging

---

## Core Principles

### 1. Explicit, not magical
No monkey-patching.

```python
from leer.integrations.openai import wrap_openai_client
client = wrap_openai_client(OpenAI())
```

### 2. Provider-aware, core-agnostic
- Core SDK stays generic (`trace`, `step`)
- Providers live in:
  - `leer.integrations.openai`
  - `leer.integrations.anthropic`

### 3. Normalize + Preserve
Every call produces:
- normalized LLM shape (for UI)
- raw artifacts (for debugging)

### 4. Start narrow
V1 supports:
- OpenAI (one main API path)
- Anthropic messages API

---

## Wrapper Behavior

When inside a trace:
- create or enrich a step
- `step_type = "llm"`
- attach metadata
- create artifacts
- generate summaries

When outside a trace:
- do NOT break
- call still executes normally

---

## Captured Fields

### Metadata
- provider
- model
- latency_ms
- finish_reason
- request_id
- status

### Usage
- prompt_tokens
- completion_tokens
- total_tokens

### Input
- system
- messages
- tools
- params (temperature, etc.)

### Output
- text
- content blocks
- tool calls
- raw response

### Errors
- error class
- message
- optional traceback summary

---

## Normalized LLM Shape

```json
{
  "provider": "openai",
  "model": "gpt-4.1",
  "input": {
    "system": "...",
    "messages": [...]
  },
  "output": {
    "text": "...",
    "tool_calls": []
  },
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 40,
    "total_tokens": 160
  },
  "meta": {
    "latency_ms": 812,
    "finish_reason": "stop"
  }
}
```

---

## Artifacts Produced
- llm_request
- llm_response
- tool_call (if present)

---

## Summary Rules
- input_summary → concise description
- output_summary → readable result

---

## Error Handling
- never break provider call
- never swallow exceptions

---

## SDK Structure

```
leer/
  integrations/
    openai.py
    anthropic.py
    normalize.py
    summaries.py
    artifacts.py
```

---

## Non-goals (V1)
- streaming
- embeddings
- multimodal
- LangChain
- Bedrock
