# LLM Instrumentation Specs

This folder defines how Leer captures, stores, and renders LLM execution data.

## Order

1. [Wrapper Spec](01-wrapper-spec.md): how data is captured
2. [Artifact Model](02-artifact-mode.md): how data is stored
3. [Provider UI](03-provider-ui.md): how data is rendered
4. [Provider Support Matrix](04-provider-support-matrix.md): which OpenAI and Anthropic surfaces are covered
5. [Tool Calling](05-tool-calling-spec.md): tool calls, `tool_step`, and linkage to LLM calls
6. [Structured Outputs](06-structured-outputs.md): `output.parsed` and schema-constrained responses
7. [Streaming](07-streaming-spec.md): chunk capture, assembly, and streaming ↔ non-streaming parity
8. [Streaming Latency Breakdown](08-streaming-latency-breakdown.md): time to first chunk, stream duration, playback

Related platform specs, in [`../platform/`](../platform/):

- `content-parts.md`, `provider-hardening.md`
- `tool-linkage.md`, `tool-lifecycle.md`
- `blob-storage.md`, `multimodal.md`

## Principle

Capture → Normalize → Store → Render
