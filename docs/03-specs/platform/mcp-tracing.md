# MCP Tracing

Defines how Leer traces Model Context Protocol interactions in a provider-agnostic way.

This spec covers MCP client calls, server identity, protocol operations, linkage to tool-calling, artifacts, UI representation, and compare behavior.

---

## Goal

Trace external MCP interactions cleanly without forcing the rest of the product to understand MCP wire syntax.

Leer should be able to:
- capture MCP requests, responses, and errors
- identify the MCP server involved
- identify the MCP operation and target capability
- link MCP activity to the LLM/tool lifecycle when applicable
- preserve raw protocol payloads for debugging
- render MCP activity clearly in run detail and compare

---

## Scope

This spec covers:
- MCP client → server operations initiated during a run
- linkage between LLM-emitted tool calls and MCP operations
- standalone MCP operations not directly triggered by an LLM tool call
- protocol artifacts and summaries
- UI and compare representation

This spec does **not** define:
- generic skill taxonomy across all tools and retrieval systems
- retrieval-specific ranking/context semantics
- transport-specific wire implementations

Those are covered by:
- `skills-model.md`
- `rag-tracing.md`
- `retrieval-artifacts.md`

---

## Design Principles

### 1. MCP is traced as a protocol interaction, not just a generic tool call

An MCP call may look tool-like, but it contains protocol semantics that deserve first-class visibility:
- server identity
- operation kind
- target name
- protocol request/response payloads
- transport and endpoint hints

### 2. Preserve raw protocol payloads, normalize summaries separately

Leer should preserve raw MCP request/response/error payloads in artifacts.
Run-detail and compare should rely on stable summary metadata, not raw payload structure.

### 3. Prefer metadata-first v1

If current tool-step infrastructure is sufficient, v1 should avoid premature schema expansion.
A metadata-first representation is preferred over introducing new storage primitives too early.

### 4. Linkage matters as much as payload capture

MCP tracing is useful only when users can understand:
- which LLM/tool call caused the MCP interaction
- which server handled it
- whether it succeeded or failed
- how it differs across runs

---

## Canonical MCP Model

An MCP interaction should expose a stable internal shape, independent of raw wire format.

### MCP interaction fields

| Field | Type | Description |
|---|---|---|
| `protocol_kind` | string | Always `mcp` for this spec |
| `operation_kind` | string | Canonical operation type such as `tool_call`, `resource_read`, `prompt_get`, `sampling`, `unknown` |
| `target_name` | string \| null | Capability/resource/prompt name targeted by the operation |
| `server_name` | string \| null | Human-readable MCP server name |
| `server_id` | string \| null | Stable internal or configured server identifier |
| `transport_kind` | string \| null | `stdio`, `http`, `sse`, `websocket`, `unknown` |
| `tool_call_id` | string \| null | LLM/tool-call identifier when applicable |
| `parent_llm_step_id` | string \| null | Originating LLM step id when applicable |
| `parent_tool_step_id` | string \| null | Parent tool step id when applicable |
| `status` | string | `completed`, `failed`, `running`, `unmatched` |
| `latency_ms` | number \| null | Protocol roundtrip latency when available |

### v1 representation rule

For v1, this canonical MCP model may live inside:
- step metadata
- step summaries
- MCP-specific artifacts

A dedicated DB table is not required for v1.

---

## Recommended v1 Step Representation

### Preferred v1 approach

Represent MCP interactions as `step_type="tool"` steps with MCP metadata.

Required metadata keys:
- `protocol_kind="mcp"`
- `operation_kind`
- `target_name`
- `server_name`
- `server_id`
- `transport_kind`
- `tool_call_id` when applicable
- `parent_llm_step_id` when applicable

Why:
- reuses existing tool-step hierarchy, artifacts, linkage, and compare support
- avoids schema migration
- keeps run-detail and compare consistent with existing tool lifecycle work

### Future option

A dedicated `step_type="mcp"` may be introduced later if:
- MCP operations need distinct grouping/filtering
- MCP becomes materially different from tool-step UX
- protocol-level behaviors grow beyond tool semantics

That is **not required** for v1.

---

## MCP Artifact Taxonomy

MCP interactions should use explicit artifact types.

### Required v1 artifact types

- `mcp_request`
- `mcp_response`
- `mcp_error`

### Optional later artifact types

- `mcp_tool_schema`
- `mcp_resource_content`
- `mcp_prompt_payload`
- `mcp_sampling_request`
- `mcp_sampling_response`
- `mcp_server_capabilities`

### Artifact rules

#### `mcp_request`
Represents the protocol request payload sent to the server.

Recommended metadata:
- `protocol_kind="mcp"`
- `operation_kind`
- `target_name`
- `server_name`
- `server_id`
- `transport_kind`
- `tool_call_id` when present
- `parent_llm_step_id` when present

#### `mcp_response`
Represents the protocol response payload returned by the server.

Same metadata shape as request where applicable.

#### `mcp_error`
Represents protocol failure payload, exception data, or normalized error summary.

Same metadata shape plus:
- `error_type`
- `error_code` when available

### Blob/storage rule

Large MCP payloads may be blob-backed using the existing artifact model.
No MCP-specific storage mechanism is needed.

---

## Linkage Rules

MCP interactions may be linked in several ways.

### LLM-driven MCP

When an LLM emits a tool call that is implemented via MCP:
- keep existing `tool_call_id`
- preserve normal tool lifecycle linkage
- include MCP metadata on the corresponding tool step
- attach MCP request/response artifacts to that tool step

### Non-LLM MCP

If a run performs MCP activity outside an LLM-emitted tool call:
- record MCP metadata anyway
- omit `tool_call_id`
- use `parent_step_id` / `parent_llm_step_id` only when meaningful

### Linkage confidence

Run-detail may continue to rely on existing tool-linkage confidence (`exact`, `heuristic`, `unlinked`) for v1.
MCP does not need a separate confidence vocabulary.

---

## Summary / Compare Model

Run-detail and compare should not depend on raw MCP payloads.

### Suggested summary fields

For MCP steps, `output_summary` and/or step metadata should surface:
- `protocol_kind`
- `operation_kind`
- `target_name`
- `server_name`
- `transport_kind`
- `status`
- `latency_ms` when known

### Compare expectations in v1

Compare should support:
- server identity differences
- operation kind differences
- target differences
- status differences
- request/response artifact presence differences
- no crashes when MCP payloads are blob-backed

Full protocol-level diffing is not required for v1.

---

## Run-Detail UI Strategy

### v1

MCP activity should appear within tool-step detail using MCP-specific metadata rows and artifacts.

Show:
- MCP badge / protocol badge
- server name
- operation kind
- target name
- transport kind
- linkage to source LLM step if present
- request/response/error artifacts

### Later

Possible dedicated MCP panels:
- server capability card
- protocol request/response viewer
- grouped server timeline

---

## Security / Privacy

MCP payloads may contain:
- server endpoints
- credentials-like headers or tokens
- sensitive resource content

Requirements:
- preserve artifacts carefully
- avoid leaking secrets into summary metadata
- keep direct endpoints/headers out of display unless explicitly safe
- use blob storage for large payloads

---

## Non-Goals for v1

- full wire-level protocol replay
- server transport emulation
- dedicated MCP database tables
- protocol-specific filtering beyond metadata/UI affordances
- perfect parity across all MCP server implementations

---

## v1 Status Target

MCP tracing v1 is complete when Leer can:
- represent MCP interactions as enriched tool steps
- capture `mcp_request` / `mcp_response` / `mcp_error` artifacts
- show server/operation/target metadata in run detail
- preserve linkage to LLM/tool lifecycle where available
- compare MCP-rich runs without crashing

---

## Beyond v1

- dedicated `mcp` step type if warranted
- richer MCP compare views
- grouped server/session views
- protocol replay
- capability schema introspection panels