/**
 * Provider-hardening detection + formatting helpers (Step 3).
 *
 * Steps 1 and 2 added four canonical signals to the normalized LLM model that
 * the UI did not previously read:
 *   - `metadata.capture === "partial"`  (Step 1: degraded observability flag)
 *   - `llm.meta.refusal`                (Step 1: provider refusal text)
 *   - `llm.usage.cached_tokens`         (Step 2: prompt cache-read tokens)
 *   - `thinking` / `redacted_thinking` content blocks (Step 2 streaming parity
 *     + pre-existing non-streaming Anthropic)
 *
 * These helpers are the single place those detection/format rules live, so
 * run-detail and compare never drift (same pattern as `step-metadata.ts`).
 * They are pure functions over the data the API already returns — nothing is
 * re-derived from raw provider payloads.
 *
 * Design Principle 7 (canonical content channels are structurally distinct):
 * thinking is a separate channel and must NOT be merged into `output.text`
 * compare diffs. These helpers expose it for dedicated rendering only.
 */

import type { LLMShape } from "@/lib/types";

export type Meta = Record<string, unknown> | null | undefined;

// ---------------------------------------------------------------------------
// Partial capture (Step 1: metadata.capture === "partial")
// ---------------------------------------------------------------------------

/**
 * True when the wrapper preserved raw payloads but canonical normalization or
 * summary generation could not complete. Per Step 1's contract this is
 * *degraded observability*, NOT failed model execution — the provider call may
 * have succeeded exactly as requested.
 */
export function isPartialCapture(meta: Meta): boolean {
  return meta?.capture === "partial";
}

export const PARTIAL_CAPTURE_LABEL = "partial";

export const PARTIAL_CAPTURE_TOOLTIP =
  "Raw payloads preserved, canonical view incomplete. The provider call may have succeeded; only Leer's normalized view is degraded.";

// ---------------------------------------------------------------------------
// Refusal (Step 1: llm.meta.refusal)
// ---------------------------------------------------------------------------

/** Raw refusal string, or null when no refusal was signalled / no llm. */
export function getRefusal(llm: LLMShape | null | undefined): string | null {
  const r = llm?.meta?.refusal;
  return typeof r === "string" && r.length > 0 ? r : null;
}

export function hasRefusal(llm: LLMShape | null | undefined): boolean {
  return getRefusal(llm) !== null;
}

export interface RefusalCompareState {
  /** Refusal present on side A. */
  a: boolean;
  /** Refusal present on side B. */
  b: boolean;
  /** Exactly one side refused — a high-signal divergence. */
  diverges: boolean;
}

export function refusalCompareState(
  a: LLMShape | null | undefined,
  b: LLMShape | null | undefined,
): RefusalCompareState {
  const ra = hasRefusal(a);
  const rb = hasRefusal(b);
  return { a: ra, b: rb, diverges: ra !== rb };
}

// ---------------------------------------------------------------------------
// Cached tokens (Step 2: llm.usage.cached_tokens)
// ---------------------------------------------------------------------------

/**
 * Cache-read token count, or null when the provider did not report it.
 * Note: `0` is a real value ("provider reported, no cache hit") and is
 * returned as `0`, not collapsed to null.
 */
export function getCachedTokens(
  usage: { cached_tokens?: number | null } | null | undefined,
): number | null {
  const c = usage?.cached_tokens;
  return typeof c === "number" ? c : null;
}

/**
 * True when both sides report cache-read tokens and the counts differ. Absent
 * data on either side is not a divergence (cannot compare what isn't reported).
 */
export function cachedTokensDiverges(
  a: { cached_tokens?: number | null } | null | undefined,
  b: { cached_tokens?: number | null } | null | undefined,
): boolean {
  const ca = getCachedTokens(a);
  const cb = getCachedTokens(b);
  if (ca === null || cb === null) return false;
  return ca !== cb;
}

// ---------------------------------------------------------------------------
// Thinking channel (Step 2: thinking / redacted_thinking content blocks)
// ---------------------------------------------------------------------------

const THINKING_BLOCK_TYPES = new Set(["thinking", "redacted_thinking"]);

export interface ThinkingBlock {
  redacted: boolean;
  /** Thinking text; null for redacted blocks (carry no text). */
  text: string | null;
}

/**
 * Extract thinking / redacted_thinking blocks from canonical output, in order.
 * Returns an empty list when none are present.
 */
export function getThinkingBlocks(llm: LLMShape | null | undefined): ThinkingBlock[] {
  const blocks = llm?.output?.content_blocks ?? [];
  const out: ThinkingBlock[] = [];
  for (const block of blocks) {
    if (!block || typeof block !== "object") continue;
    const b = block as Record<string, unknown>;
    const t = b.type;
    if (typeof t !== "string" || !THINKING_BLOCK_TYPES.has(t)) continue;
    if (t === "redacted_thinking") {
      out.push({ redacted: true, text: null });
    } else {
      const txt = b.thinking;
      out.push({ redacted: false, text: typeof txt === "string" ? txt : null });
    }
  }
  return out;
}

export function hasThinking(llm: LLMShape | null | undefined): boolean {
  return getThinkingBlocks(llm).length > 0;
}
