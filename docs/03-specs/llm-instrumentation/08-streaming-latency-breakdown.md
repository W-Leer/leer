Goal

Make latency visible as a real breakdown, not a single number.

For streaming LLM steps, a developer should quickly understand:
	•	total latency
	•	TTFC
	•	generation duration
	•	token throughput
	•	where time was spent

And in compare:
	•	which part regressed
	•	whether the slowdown came from startup, generation, or both

Scope for v1

Only do LLM streaming latency breakdown first.

In scope:
	•	run detail latency breakdown for streaming LLM steps
	•	compare latency breakdown for streaming LLM steps
	•	derived metrics from existing metadata where possible
	•	graceful empty state for non-streaming or incomplete data

Out of scope:
	•	full multi-step waterfall for the whole run
	•	tool-wait attribution across multiple steps
	•	provider-specific deep network phases
	•	hallucination detection
	•	semantic stream divergence
	•	replay

What metrics v1 should show

For a streamed LLM step:
	•	Total latency
	•	already effectively available from step duration / latency
	•	TTFC
	•	from stream metadata
	•	Generation duration
	•	stream_duration_ms - time_to_first_chunk_ms
	•	Chunks
	•	from stream metadata
	•	Output chars
	•	from stream metadata
	•	Chars/sec
	•	assembled_text_chars / generation_duration_s
	•	optional:
	•	ms per chunk
	•	only if it reads clearly

Do not overdo it. The key three are:
	•	total
	•	TTFC
	•	generation

Product rules

Rule 1 — Breakdown must explain latency

Not just more numbers. It should answer “why was this slow?”

Rule 2 — Stream-only first

Do not invent fake breakdowns for non-streaming calls.

Rule 3 — Derived metrics must be obvious

Every derived metric should be easily explainable from existing fields.

Rule 4 — Compare should show delta clearly

The compare page should make regressions pop immediately.

Rule 5 — No provider branching in UI

Use the same breakdown component for OpenAI and Anthropic.

⸻

Does it require compare page changes?

Yes.

Minimum compare changes:
	•	add a Latency block for streamed LLM steps
	•	show per-side metrics
	•	show deltas
	•	mark changed

Without that, the feature is only half useful.

⸻