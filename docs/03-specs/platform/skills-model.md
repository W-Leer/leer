# Skills Model

Defines Leer's provider-agnostic model for capabilities, tools, MCP-backed operations, and higher-level skills.

---

## Goal

Give Leer a stable language for describing **what capability was used**, regardless of where it came from.

This model should let the product distinguish between:
- a plain local tool
- an MCP-backed capability
- a retrieval operation
- a higher-level named skill composed of one or more steps

---

## Problem

Today many systems overload raw names:
- `step.name`
- `tool_name`
- provider-native tool names
- server-specific names

That makes it hard to answer:
- was this a local tool or remote server capability?
- are these two calls conceptually the same skill?
- how should compare group them?
- how should the UI label them?

---

## Design Principles

### 1. Capability identity should be separate from presentation

Keep a canonical identity and a human-readable label distinct.

### 2. Skills can sit above tools

A skill may map to:
- one local tool
- one MCP capability
- one retrieval flow
- a composite chain of calls

### 3. v1 should be metadata-first

The first implementation should avoid a dedicated capability table.
Metadata on steps and artifacts is sufficient for v1.

---

## Canonical Capability Fields

These fields may be attached to steps, artifacts, summaries, and compare views.

| Field | Type | Description |
|---|---|---|
| `capability_kind` | string | `tool`, `mcp_tool`, `retrieval`, `skill`, `unknown` |
| `capability_name` | string \| null | Stable canonical name |
| `capability_label` | string \| null | Human-facing label |
| `capability_namespace` | string \| null | Grouping namespace such as app/module/server |
| `server_name` | string \| null | Relevant for MCP-backed capabilities |
| `server_id` | string \| null | Stable server identifier when available |
| `skill_name` | string \| null | Optional higher-level skill grouping |
| `skill_label` | string \| null | Optional human-friendly skill label |

---

## Capability Kinds

### `tool`
A local or ordinary tool call with no protocol/server semantics.

### `mcp_tool`
A capability executed through MCP and backed by a specific MCP server.

### `retrieval`
A retrieval or ranking capability, whether implemented locally or remotely.

### `skill`
A higher-level named capability that may contain several lower-level operations.

### `unknown`
Fallback when Leer cannot classify the capability safely.

---

## Recommended v1 Usage

### On tool steps

Tool steps should continue to exist, but may include:
- `capability_kind`
- `capability_name`
- `capability_label`
- `server_name` / `server_id` when MCP-backed
- `skill_name` when part of a named workflow

### On MCP-backed tool steps

Use:
- `capability_kind="mcp_tool"`
- `capability_name` = canonical target/capability name
- `server_name` / `server_id`

### On retrieval steps

Use either:
- `step_type="tool"` or `step_type="code"` in v1
- plus `capability_kind="retrieval"`

---

## UI Expectations

Run-detail and compare should be able to show:
- capability label
- capability kind badge
- server badge when relevant
- skill grouping badge when relevant

The UI should not rely only on `step.name` once capability metadata exists.

---

## Compare Expectations

Compare should be able to surface:
- capability kind changes
- capability name changes
- server changes
- skill grouping changes

Full graph-level skill diffing is out of scope for v1.

---

## Artifact Relationship

Artifacts associated with a capability should carry enough metadata to make their origin clear.

Recommended shared artifact metadata:
- `capability_kind`
- `capability_name`
- `skill_name` when present
- `server_name` / `server_id` when present

---

## Non-Goals for v1

- dedicated capability registry table
- normalized cross-run skill DAGs
- auto-discovery of all capability equivalence relationships
- perfect grouping across arbitrary custom tool names

---

## v1 Status Target

Skills/server modeling v1 is complete when Leer can:
- label local tools vs MCP tools vs retrieval cleanly
- show capability metadata in run detail
- show capability/server differences in compare
- do all of the above without schema migrations