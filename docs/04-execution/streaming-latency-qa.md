# Streaming Latency Breakdown — QA Checklist

## Setup

1. Run the streaming demo to produce fast + slow runs:
   ```
   cd apps/sdk-python && uv run python ../../examples/demo_streaming.py
   ```
2. Open the Leer UI at `http://localhost:3000`.

## Run Detail

- [ ] Open a `streaming-fast` run
- [ ] Compact **Latency** row is visible below Tool calls
  - Shows: Total, TTFC, Generation, chars/s, tok/s
  - No trailing spaces in rate values
  - Termination hidden when "completed"
  - Truncated hidden when false
- [ ] Expand the **Stream** section
  - Latency summary grid appears at top with: Total latency, TTFC, Generation time, Chunks, Output chars, Chars/s, Tok/s, Startup share, Generation share
  - Overhead omitted when 0
  - Values are readable, no NaN or Infinity
- [ ] Open a `streaming-slow` run
  - TTFC and Generation values are visibly larger
  - Startup share is higher than in the fast run

## Compare

- [ ] Compare `streaming-fast` vs `streaming-slow`
- [ ] **Latency** block appears after Metadata
  - Shows A/B columns with: Total, TTFC, Generation, Chars/s, Tok/s
  - Changed metrics highlighted
  - Overhead shown only when > 0 on at least one side
- [ ] Delta values make sense (slow run has higher TTFC, longer generation)

## One-Sided Streaming

- [ ] Compare a streaming run vs a non-streaming run
- [ ] Latency block renders with callout: "A only · B is non-streaming" (or vice versa)
- [ ] Metrics shown only for the streaming side; "—" for the other

## Non-Streaming Runs

- [ ] Open a non-streaming LLM run (e.g. from `demo_openai_wrapper.py`)
- [ ] No Latency row appears
- [ ] No Stream section appears

## Failed Partial Stream

- [ ] If a failed streaming run exists, open it
- [ ] Latency row still renders with available partial data
- [ ] Termination shows "failed"

## Edge Cases

- [ ] No NaN, Infinity, or negative values in any surface
- [ ] Empty/null metrics render as "—" in compare, omitted in run detail
- [ ] Percentages display as whole numbers (e.g. "24%", not "24.3%")
