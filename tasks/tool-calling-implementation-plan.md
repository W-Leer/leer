# Tool Calling Implementation Plan

This document defines the implementation plan for first-class tool calling in Leer.

It is intentionally detailed so implementation can proceed in a disciplined order without product drift.

---

# 1. Objective

Introduce first-class tool support in Leer so that:

- tool execution appears as real `tool` steps
- inputs / outputs / errors are inspectable
- tool usage fits naturally into run detail and compare
- linkage with LLM-emitted tool calls is preserved
- the system remains explicit and provider-agnostic

---

# 2. Guiding Principle

Do not build an execution engine.

Build the minimum explicit tracing primitives needed to make tool usage observable and debuggable.

---

# 3. Deliverables

Implementation should produce:

1. canonical tool-calling spec
2. SDK `tool_step` tracing helper
3. tool request / response / error artifacts
4. metadata contract for tool steps
5. basic timeline visibility
6. basic compare support
7. tests
8. one end-to-end demo flow

---

# 4. Implementation Phases

## Phase 1 — Data Model and Contracts

### Goal
Make sure the existing model can represent tool execution cleanly.

### Tasks
- confirm `step_type="tool"` is supported everywhere it needs to be
- define canonical metadata fields:
  - `tool_name`
  - `tool_call_id`
  - `source_provider`
  - `source_model`
- confirm artifact taxonomy supports:
  - `tool_request`
  - `tool_response`
  - `tool_error`
- confirm summaries are enough for first UI pass

### Success criteria
- tool steps can be persisted and ingested cleanly
- artifacts can represent tool flows without schema hacks

### Risks
- overfitting metadata to one provider
- hiding tool execution inside llm metadata

---

## Phase 2 — SDK Helper

### Goal
Provide an explicit and ergonomic tracing primitive for tool execution.

### Canonical API
```python
with tool_step("get_weather", tool_call_id="call_123") as s:
    s.input = {"city": "Paris"}
    result = get_weather(city="Paris")
    s.output = result
```

### Tasks
- implement `tool_step(...)`
- ensure it creates `step_type="tool"`
- ensure `name = tool_name`
- ensure standard step lifecycle works
- support optional linkage metadata:
  - `tool_call_id`
  - `source_provider`
  - `source_model`

### Success criteria
- a developer can trace a tool step with one small explicit wrapper
- normal exceptions still propagate

### Constraints
- no global auto-wrapping
- no hidden execution engine
- keep API parallel in spirit to existing trace/step APIs

---

## Phase 3 — Artifact Handling

### Goal
Capture request / response / error payloads for tool steps.

### Tasks
- attach `tool_request` artifact when input is set
- attach `tool_response` artifact when output is set
- attach `tool_error` artifact or equivalent error capture on failure
- generate readable preview_text for each artifact
- ensure artifact sequence indexes are stable

### Success criteria
- tool step artifacts appear in timeline data
- request/response are easy to inspect
- artifacts are linked to the correct tool step

### Notes
This phase should reuse the existing artifact foundation as much as possible.

---

## Phase 4 — Error Handling

### Goal
Failed tool execution must still be highly debuggable.

### Tasks
- mark tool step as failed on exception
- populate `error_summary`
- include traceback when appropriate
- preserve original exception behavior
- optionally attach `tool_error` artifact if useful

### Success criteria
- failures are visible in run detail
- SDK does not swallow provider or tool exceptions
- compare can surface tool failures just like other step failures

### Invariant
Observability must never change tool semantics.

---

## Phase 5 — LLM Integration

### Goal
Preserve the link between LLM-emitted tool calls and tool execution.

### Tasks
- ensure normalized LLM output includes:
  - tool_call_id
  - tool name
  - tool arguments
- ensure tool step can reuse the same `tool_call_id`
- store source provider/model in tool step metadata where available

### Success criteria
- one can visually or programmatically tell which tool step corresponds to which model-emitted call

### Important note
This phase does not require advanced UI linking yet.
It only requires preserving enough data for future linking.

---

## Phase 6 — Run Detail Validation

### Goal
Verify that tool steps are readable with minimal or no UI redesign.

### Tasks
- run one real/fake end-to-end flow:
  - LLM emits tool call
  - tool runs
  - LLM continues
- inspect the run detail page
- verify:
  - tool step name is clear
  - input summary is readable
  - output summary is readable
  - error state works

### Success criteria
- timeline tells the truth clearly
- tool step does not look like an accidental generic code step

---

## Phase 7 — Compare Validation

### Goal
Ensure tool steps behave sensibly in compare without special-case complexity.

### Tasks
- compare runs where:
  - tool succeeds in both
  - tool succeeds in one and fails in the other
  - tool missing on one side
- verify compare still uses the same matching system
- verify generic compare fields are enough initially

### Success criteria
- tool steps remain first-class in compare
- missing / changed / failed cases are obvious

---

## Phase 8 — Optional Small UI Improvements

### Goal
Polish clarity without building a separate tool UI system.

### Possible improvements
- tool badge in step header
- better rendering of input args
- clearer output rendering for structured tool results
- slightly richer failure treatment

### Important
Do not block the core tool-calling feature on this.
The first objective is correct observability.

---

# 5. Test Plan

## Unit tests
Add at least:

- tool_step success
- tool_step failure
- request artifact created
- response artifact created
- error captured
- metadata correctness
- tool_call_id preserved
- exception propagation

## Integration tests
Add at least:

- LLM → tool → LLM flow
- multiple tool executions in one run
- tool without tool_call_id
- compare with tool step differences

## UI validation
Manual is acceptable initially:
- run detail
- compare

---

# 6. Example End-to-End Scenario

A strong demo scenario should look like:

1. prepare prompt
2. model decides to call weather tool
3. tool executes with `city=Paris`
4. tool returns forecast
5. model writes final answer

### Expected timeline
- `prepare_prompt` (code)
- `gpt-4.1` (llm, emits tool call)
- `get_weather` (tool, succeeds)
- `gpt-4.1` (llm, final answer)

### Expected artifacts
- llm_request
- llm_response
- tool_request
- tool_response
- llm_request
- llm_response

---

# 7. Execution Order (What to do now)

## Strict recommended order

### NOW
1. confirm data model + artifact taxonomy
2. implement `tool_step(...)`
3. attach request/response artifacts
4. add failure handling
5. write tests
6. run one end-to-end demo
7. verify UI / compare

### AFTER NOW
8. richer LLM/tool linkage in UI
9. richer compare for tool args/results

### LATER
10. streaming tool calls
11. MCP / skills
12. multimodal tool payload handling

---

# 8. What not to do now

Do **not** add these during the first implementation:

- automatic tool orchestration
- retries
- queues
- background execution engine
- MCP integration
- streaming support
- full tool graph visualization
- provider-specific branching in timeline UI

These will slow down the feature and blur the product boundary.

---

# 9. Risks

## 9.1 Over-automation
If the SDK starts executing or wrapping tools magically, the product becomes harder to trust.

## 9.2 Tool/LLM conflation
If tool execution is represented only inside LLM metadata, the timeline becomes much less useful.

## 9.3 Provider coupling
If tool metadata is designed around only one provider, Anthropic/OpenAI parity becomes messy later.

## 9.4 Premature UI ambition
If you try to fully solve graph linking before core tracing exists, you will slow down delivery.

---

# 10. Definition of Done

Tool calling is “done enough” when:

- tool steps appear in the run timeline
- tool input is visible
- tool output is visible
- failures are visible
- request/response artifacts are created
- `tool_call_id` can be preserved
- compare works at a basic but truthful level
- the system remains explicit and provider-agnostic

---

# 11. Invariants

These must remain true during implementation:

1. tool execution is a real step
2. tool tracing is explicit
3. exceptions propagate
4. artifacts remain attached to the tool step
5. provider-specific origin is optional, not mandatory
6. compare must not hide tool steps

---

# 12. Recommended Files to Touch

Likely areas:

- SDK tracing helper module
- step lifecycle / context helpers
- artifact helper usage
- tests
- one example/demo script

Potential later files:
- run detail UI
- compare UI

---

# 13. Final Recommendation

Implement tool calling as the next contained feature slice.

It gives high debugging value while preserving product clarity.

Do not expand scope into orchestration or protocols yet.

---

# 14. Guiding Question

**How do we make tool usage obvious, inspectable, and trustworthy without making the SDK magical?**
