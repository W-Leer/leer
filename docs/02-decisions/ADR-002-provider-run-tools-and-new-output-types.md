# ADR-002: Provider-run tools and new output types

## Context
Both providers now return output the normalizer did not know, and it labelled
all of it as a generic `file` part ("unknown output item: …"):

- tools the provider runs itself: OpenAI `web_search_call`, `file_search_call`,
  `code_interpreter_call`, `mcp_call`; Anthropic `server_tool_use` plus its
  result blocks (`web_search_tool_result`, `web_fetch_tool_result`,
  `code_execution_tool_result`, …)
- OpenAI `reasoning` items
- OpenAI tools the *caller* runs: `computer_call`, `local_shell_call`,
  `shell_call`, `apply_patch_call`

Provider-run tools never get a local tool step, so putting them in
`output.tool_calls` would show them as "unmatched" in tool linkage.

## Decision
- Add one canonical content part, `provider_tool`: one part per tool execution
  the provider ran, with `id`, `name`, `input`, and when known `status`,
  `output`, `error`, `server` (MCP server label), plus `provider`,
  `provider_part_type`, and `preview_text`. It is **not** added to
  `output.tool_calls`.
- OpenAI returns call and result in one item. Anthropic returns them as two
  blocks linked by `tool_use_id`; the result is merged into the matching
  `provider_tool` part so both providers produce the same shape. A result with
  no matching call becomes its own `provider_tool` part.
- Opaque provider blobs (`encrypted_content`, `encrypted_index`) are dropped
  from `output`; they stay in the raw response artifact.
- OpenAI `reasoning` becomes `thinking` (summary text) or `redacted_thinking`
  (no visible text), the same channel Anthropic thinking uses.
- Caller-run OpenAI tools become ordinary tool calls (`name` is the item type
  without `_call`; `arguments` is the `action` / `operation`), like
  `custom_tool_call`.
- Other unknown types still fall back to `file`.

## Why
- "Which tools were called" must include tools the provider ran, without
  breaking linkage for the tools the caller runs.
- One shape across providers, as the content-parts spec requires.

## Consequences
- Additive only: a new part type and new values in existing lists. Records
  written before this keep their `file` parts.
- The UI renders `provider_tool` as "run by provider".
- Anthropic streaming must rebuild content blocks by index (as the SDK does)
  instead of joining text, or streamed provider-tool blocks are lost.
