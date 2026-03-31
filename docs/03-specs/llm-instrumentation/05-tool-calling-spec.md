# Tool Calling Spec

This document defines the canonical design for tool calling in Leer.

It covers:

- product goals
- SDK contract
- data model
- artifacts
- timeline semantics
- UI behavior
- compare behavior
- invariants
- edge cases
- examples

This is the source of truth for first-class tool support in Leer.

---

# 1. Purpose

Leer should make tool use inside LLM workflows obvious, inspectable, and debuggable.

A developer should be able to answer:

- Which tool was called?
- Why was it called?
- With what arguments?
- Did the tool succeed or fail?
- What did it return?
- What did the model do after receiving the result?
- Did anything change between two runs?

---

# 2. Product Principle

Tool calling is **not just a property of an LLM response**.

It is a sequence of related execution events that should be represented explicitly.

A correct mental model is:

1. LLM emits a tool call
2. Tool executes as its own step
3. Tool produces a result or error
4. LLM continues afterward

Leer must preserve this structure in:

- SDK tracing
- run timeline
- artifacts
- compare
- future replay

---

# 3. Scope

## In scope

- first-class `tool` steps
- explicit tool tracing helper in SDK
- tool request / response / error artifacts
- linkage between LLM tool call and tool step via `tool_call_id`
- timeline visibility
- basic compare support for tool steps
- generic provider-agnostic tool model

## Out of scope

- automatic tool execution engine
- retries / orchestration
- MCP support
- skills registry
- streaming tool calls
- multimodal tool payload rendering
- advanced tool graph visualization
- provider-specific tool UI forks

---

# 4. Core Concepts

## 4.1 Tool call
A model-generated intent to invoke a tool.

Example:

```json
{
  "id": "call_123",
  "name": "get_weather",
  "arguments": {
    "city": "Paris"
  }
}
```

## 4.2 Tool step
A first-class traced step representing actual tool execution.

Example:
- `step_type = "tool"`
- `name = "get_weather"`

## 4.3 Tool result
The value returned by the tool, captured as output summary + artifact.

## 4.4 Tool error
A failed tool execution, captured as error summary + optional error artifact.

---

# 5. Canonical Timeline Shape

The ideal visible execution flow is:

```text
[code] prepare_prompt
[llm]  gpt-4.1 → emits tool call get_weather(call_123)
[tool] get_weather → executes with city=Paris
[llm]  gpt-4.1 → final response after tool result
```

This is the mental model Leer should reinforce.

---

# 6. SDK Contract

## 6.1 Explicit over magic

Leer should **not** auto-wrap arbitrary tool functions globally.

Tool tracing must be explicit.

## 6.2 Canonical API

### Context manager

```python
from leer import tool_step

with tool_step("get_weather", tool_call_id="call_123") as s:
    result = get_weather(city="Paris")
    s.input = {"city": "Paris"}
    s.output = result
```

### Optional decorator

```python
@tool_step("get_weather")
def get_weather(city: str) -> dict:
    ...
```

The context-manager version is the canonical first-class API.
Decorator support is optional.

## 6.3 What `tool_step(...)` must do automatically

At minimum, `tool_step(...)` should:

- create a step with `step_type="tool"`
- set `name` to the tool name
- preserve standard lifecycle fields:
  - started_at
  - ended_at
  - duration_ms
  - status
- attach metadata
- attach artifacts when input/output/error is set
- preserve normal exception behavior

## 6.4 Required arguments

The tool helper should support:

- `tool_name`
- optional `tool_call_id`
- optional provider/model metadata if the caller wants to set linkage info

Example:

```python
with tool_step(
    "get_weather",
    tool_call_id="call_123",
    source_provider="openai",
    source_model="gpt-4.1",
) as s:
    ...
```

---

# 7. Data Model

## 7.1 Step type

Tool execution is represented as:

```text
step_type = "tool"
```

## 7.2 Tool step fields

A tool step uses the normal step model plus metadata.

### Core step fields
- id
- run_id
- parent_step_id (optional)
- sequence_index
- name
- step_type = "tool"
- status
- started_at
- ended_at
- duration_ms
- input_summary
- output_summary
- error_summary
- metadata

## 7.3 Required metadata fields

Suggested metadata shape:

```json
{
  "tool_name": "get_weather",
  "tool_call_id": "call_123",
  "source_provider": "openai",
  "source_model": "gpt-4.1"
}
```

### Field meanings

- `tool_name`: canonical tool name
- `tool_call_id`: provider-emitted call id if available
- `source_provider`: upstream provider that requested the tool
- `source_model`: upstream model that requested the tool

These fields should be optional at DB level but expected in tool-traced flows.

---

# 8. Artifact Model

Tool execution should create first-class artifacts.

## 8.1 Tool request artifact

### Type
- `artifact_type = "tool_request"`
- `role = "input"`

### Contents
Arguments or invocation payload.

Example:
```json
{
  "city": "Paris"
}
```

## 8.2 Tool response artifact

### Type
- `artifact_type = "tool_response"`
- `role = "output"`

### Contents
Returned result.

Example:
```json
{
  "temperature": 18,
  "condition": "sunny"
}
```

## 8.3 Tool error artifact

### Type
- `artifact_type = "tool_error"`
- `role = "error"`

### Contents
Structured failure info if useful.

Example:
```json
{
  "error_type": "TimeoutError",
  "error_message": "weather provider timed out"
}
```

## 8.4 Preview text rules

Each artifact should have readable preview text.

Examples:
- request preview: `city=Paris`
- response preview: `temperature=18, condition=sunny`
- error preview: `TimeoutError: weather provider timed out`

---

# 9. Summary Rules

## 9.1 Input summary
Tool input summary should be concise and readable.

Examples:
- `{"city": "Paris"}`
- `{"query": "top restaurants in London"}`

## 9.2 Output summary
Tool output summary should be readable and compact.

Examples:
- `{"temperature": 18, "condition": "sunny"}`
- `{"result_preview": "Found 24 matching documents"}`

## 9.3 Error summary
Must surface:
- error type
- message
- traceback when useful

Example:
```json
{
  "error_type": "TimeoutError",
  "message": "weather provider timed out",
  "traceback": "..."
}
```

---

# 10. LLM Integration Contract

## 10.1 Normalized LLM output must preserve tool calls

If an LLM emits a tool call, the normalized LLM payload must include:

```json
{
  "tool_calls": [
    {
      "id": "call_123",
      "name": "get_weather",
      "arguments": {
        "city": "Paris"
      }
    }
  ]
}
```

## 10.2 Linking rule
If a tool step is created as a result of an LLM tool call:

- `tool_call_id` on the tool step should equal the LLM tool call id
- this ID should remain stable across:
  - metadata
  - artifacts
  - future linking

This is the minimum linking contract.

## 10.3 What we are not doing yet
We are **not** requiring automatic UI graph linking or automated execution chaining yet.

But the data model must preserve enough identity to support it later.

---

# 11. UI Contract

## 11.1 Run detail UI for tool steps

Tool steps should render clearly as tool steps, not generic code blobs.

### Required display
- tool name
- tool step badge / type
- duration
- input
- output
- error if failed

### Nice-to-have
- tool_call_id
- source provider/model in metadata row

## 11.2 LLM step UI
If LLM output contains tool calls:
- show tool call section in output
- render tool name + arguments
- preserve readability

## 11.3 Compare UI
Tool steps should compare at least generically:
- status
- input_summary
- output_summary
- error_summary

Later, richer compare can include:
- args diff
- result diff
- duration diff

---

# 12. Compare Contract

## 12.1 Initial compare behavior
Tool steps are first-class steps in compare, just like code or llm steps.

They should use:
- normal step matching rules
- normal missing-step logic
- standard diff booleans

## 12.2 Future richer compare
Possible future tool-specific compare:
- argument diff
- result field diff
- call-id display
- provider/model linkage display

Not required now.

---

# 13. Full End-to-End Example

## 13.1 Example application flow

```python
from leer import trace, step, tool_step
from leer.integrations.openai import wrap_openai_client

client = wrap_openai_client(OpenAI())

@trace(workflow_name="tool-calling-demo")
def run_demo():
    with step("prepare_prompt", step_type="code") as s:
        prompt = "What is the weather in Paris?"
        s.output = {"prompt": prompt}

    llm_response_1 = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        tools=[{
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"}
                    },
                    "required": ["city"]
                }
            }
        }]
    )

    tool_call = {
        "id": "call_123",
        "name": "get_weather",
        "arguments": {"city": "Paris"}
    }

    with tool_step(
        "get_weather",
        tool_call_id=tool_call["id"],
        source_provider="openai",
        source_model="gpt-4.1",
    ) as s:
        s.input = tool_call["arguments"]
        result = {"temperature": 18, "condition": "sunny"}
        s.output = result

    llm_response_2 = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "tool_calls": [tool_call]},
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "content": '{"temperature": 18, "condition": "sunny"}'
            }
        ]
    )

    return {"ok": True}
```

## 13.2 Expected timeline
- `prepare_prompt` (code)
- `gpt-4.1` (llm, emitted tool call)
- `get_weather` (tool)
- `gpt-4.1` (llm, post-tool continuation)

## 13.3 Expected artifacts
- llm_request
- llm_response
- tool_request
- tool_response
- llm_request
- llm_response

---

# 14. Invariants

These invariants should remain true across implementations.

## 14.1 A tool execution is always its own step
Never model actual tool execution only as a subfield inside an LLM step.

## 14.2 Tool tracing must be explicit
No hidden global auto-instrumentation of arbitrary Python functions.

## 14.3 Tool artifacts must be preserved
At minimum:
- request
- response
- error if failed

## 14.4 Exceptions must propagate
If the tool function raises, Leer may capture metadata/artifacts, but must not swallow the original exception.

## 14.5 Provider-specific origin is optional, not required
A tool step must still make sense even without OpenAI/Anthropic linkage fields.

## 14.6 Compare must not special-case away tool steps
Tool steps are real steps and must remain visible in compare.

---

# 15. Edge Cases

## 15.1 Tool returns a very large payload
Current expected behavior:
- keep summary concise
- artifact stores full inline payload if still reasonable
- blob strategy is future work

## 15.2 Tool raises before output exists
Expected behavior:
- status = failed
- error_summary exists
- tool_error artifact may exist
- no fake output summary

## 15.3 Missing `tool_call_id`
Tool step should still work.
Linkage becomes weaker, but the step remains valid.

## 15.4 Tool called outside an active trace
Behavior should remain safe.
Tool helper may no-op or behave predictably depending on current SDK conventions.

## 15.5 Same tool called multiple times in one run
Each execution must become its own tool step.

---

# 16. Testing Requirements

## 16.1 Unit tests
At minimum:
- tool step success
- tool step failure
- request artifact creation
- response artifact creation
- error artifact or error summary creation
- metadata correctness
- exception propagation

## 16.2 Integration tests
At minimum:
- LLM tool call + tool step + LLM continuation
- preserved tool_call_id linkage

## 16.3 UI validation
At minimum:
- tool step readable in run detail
- tool step compare does not break
- LLM step still shows tool calls in output

---

# 17. Non-Goals

The following are explicitly not part of this spec:

- tool orchestration engine
- retry policies
- queueing or scheduling
- MCP protocol support
- skills registry
- streaming tool calls
- multimodal tool payload rendering
- automatic semantic linking in compare

---

# 18. Design Principles

- explicit over magical
- truthful over implicit
- tool execution is first-class
- provider-agnostic model first
- preserve enough structure for future linking
- optimize for debugging value per unit of complexity

---

# 19. Summary

Tool calling in Leer is not “just another field.”

It is a first-class execution concept.

Leer should make tool use:

- visible
- structured
- debuggable
- comparable
- ready for future replay and richer execution flows

---

# 20. Core Question

**What happened when my agent used tools, and what changed between runs?**
