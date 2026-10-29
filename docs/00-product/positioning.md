# Positioning

## Category
Execution records for AI agents

## One-liner
The execution record for AI agents.

## What it answers
For any agent run: what happened and why, which tools and LLMs were called,
which inputs produced which outputs, which intermediate artifacts existed,
which path was taken, and what the final result was.

## Alternative framing
Bring clarity to AI workflows: a durable, provider-agnostic record of every run
that stays readable when providers, models, prompts, or tool schemas change.

## Not
- not an agent framework
- not a chatbot wrapper
- not a logging, tracing, or observability tool. Leer captures and inspects
  runs, but the record is the product, not a dashboard on top of logs.
- not prompt management

## Future expansion
Replay and execution control, built on the same records. Capture comes first,
and replay is not built yet (see `AGENTS.md`).
