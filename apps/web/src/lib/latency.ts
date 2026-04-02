// ---------------------------------------------------------------------------
// Canonical latency breakdown derivation for streamed LLM steps.
// Pure computation — no UI, no formatting, no side effects.
// ---------------------------------------------------------------------------

export interface LatencyBreakdownInput {
  durationMs: number | null | undefined;
  streamMeta: Record<string, unknown> | null | undefined;
  usage: {
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
    total_tokens?: number | null;
  } | null | undefined;
}

export interface LatencyBreakdown {
  is_stream: boolean;
  is_available: boolean;
  total_ms: number | null;
  ttfc_ms: number | null;
  stream_duration_ms: number | null;
  generation_ms: number | null;
  overhead_ms: number | null;
  chunk_count: number | null;
  text_chars: number | null;
  completion_tokens: number | null;
  chars_per_sec: number | null;
  tokens_per_sec: number | null;
  startup_pct: number | null;
  generation_pct: number | null;
  termination: string | null;
  truncated_chunks: boolean;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function toFinite(v: unknown): number | null {
  if (typeof v !== "number") return null;
  if (!Number.isFinite(v)) return null;
  return v;
}

function toNonNeg(v: unknown): number | null {
  const n = toFinite(v);
  if (n === null) return null;
  return n < 0 ? 0 : n;
}

function safeRate(numerator: number | null, denominationMs: number | null): number | null {
  if (numerator === null || denominationMs === null || denominationMs <= 0) return null;
  const secs = denominationMs / 1000;
  const rate = numerator / secs;
  return Number.isFinite(rate) ? rate : null;
}

function safePct(part: number | null, whole: number | null): number | null {
  if (part === null || whole === null || whole <= 0) return null;
  const pct = part / whole;
  return Number.isFinite(pct) ? pct : null;
}

// ---------------------------------------------------------------------------
// Main derivation
// ---------------------------------------------------------------------------

const UNAVAILABLE: LatencyBreakdown = {
  is_stream: false,
  is_available: false,
  total_ms: null,
  ttfc_ms: null,
  stream_duration_ms: null,
  generation_ms: null,
  overhead_ms: null,
  chunk_count: null,
  text_chars: null,
  completion_tokens: null,
  chars_per_sec: null,
  tokens_per_sec: null,
  startup_pct: null,
  generation_pct: null,
  termination: null,
  truncated_chunks: false,
};

export function computeLatencyBreakdown(input: LatencyBreakdownInput): LatencyBreakdown {
  const { streamMeta, usage } = input;

  if (!streamMeta || streamMeta.is_stream !== true) {
    return UNAVAILABLE;
  }

  const streamDurationMs = toNonNeg(streamMeta.stream_duration_ms);
  const ttfcMs = toNonNeg(streamMeta.time_to_first_chunk_ms);

  const totalMs = toNonNeg(input.durationMs) ?? streamDurationMs;

  let generationMs: number | null = null;
  if (streamDurationMs !== null && ttfcMs !== null) {
    generationMs = Math.max(0, streamDurationMs - ttfcMs);
  }

  let overheadMs: number | null = null;
  if (totalMs !== null && streamDurationMs !== null) {
    overheadMs = Math.max(0, totalMs - streamDurationMs);
  }

  const chunkCount = toNonNeg(streamMeta.chunk_count);
  const textChars = toNonNeg(streamMeta.assembled_text_chars);
  const completionTokens = toNonNeg(usage?.completion_tokens);

  return {
    is_stream: true,
    is_available: true,
    total_ms: totalMs,
    ttfc_ms: ttfcMs,
    stream_duration_ms: streamDurationMs,
    generation_ms: generationMs,
    overhead_ms: overheadMs,
    chunk_count: chunkCount,
    text_chars: textChars,
    completion_tokens: completionTokens,
    chars_per_sec: safeRate(textChars, generationMs),
    tokens_per_sec: safeRate(completionTokens, generationMs),
    startup_pct: safePct(ttfcMs, totalMs),
    generation_pct: safePct(generationMs, totalMs),
    termination: typeof streamMeta.termination === "string" ? streamMeta.termination : null,
    truncated_chunks: typeof streamMeta.truncated_chunks === "boolean" ? streamMeta.truncated_chunks : false,
  };
}
