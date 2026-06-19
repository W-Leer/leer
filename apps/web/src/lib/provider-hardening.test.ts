import { describe, expect, test } from "bun:test";
import {
  isPartialCapture,
  getRefusal,
  hasRefusal,
  refusalCompareState,
  getCachedTokens,
  cachedTokensDiverges,
  getThinkingBlocks,
  hasThinking,
} from "./provider-hardening";
import type { LLMShape } from "./types";

/** Build a minimal LLMShape with overridable output/usage/meta. */
function makeLlm(partial: {
  content_blocks?: Record<string, unknown>[];
  cached_tokens?: number | null;
  refusal?: string | null;
}): LLMShape {
  return {
    provider: "openai",
    model: "gpt-4.1",
    input: { system: null, messages: [], tools: [], params: {} },
    output: { text: "hi", tool_calls: [], content_blocks: partial.content_blocks ?? [] },
    usage: {
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
      cached_tokens: partial.cached_tokens,
    },
    meta: { finish_reason: null, request_id: null, latency_ms: null, refusal: partial.refusal },
  };
}

// ---------------------------------------------------------------------------
// isPartialCapture (Step 1: metadata.capture === "partial")
// ---------------------------------------------------------------------------

describe("isPartialCapture", () => {
  test("true only for the exact 'partial' value", () => {
    expect(isPartialCapture({ capture: "partial" })).toBe(true);
  });

  test("false when capture absent", () => {
    expect(isPartialCapture({})).toBe(false);
    expect(isPartialCapture({ provider: "openai" })).toBe(false);
  });

  test("false for other capture values (no false positives)", () => {
    expect(isPartialCapture({ capture: "full" })).toBe(false);
    expect(isPartialCapture({ capture: "" })).toBe(false);
    expect(isPartialCapture({ capture: true as unknown as string })).toBe(false);
  });

  test("safe on null / undefined", () => {
    expect(isPartialCapture(null)).toBe(false);
    expect(isPartialCapture(undefined)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Refusal (Step 1: llm.meta.refusal)
// ---------------------------------------------------------------------------

describe("getRefusal / hasRefusal", () => {
  test("returns the refusal string when present", () => {
    const llm = makeLlm({ refusal: "I can't help with that." });
    expect(getRefusal(llm)).toBe("I can't help with that.");
    expect(hasRefusal(llm)).toBe(true);
  });

  test("null when refusal is null / empty / missing", () => {
    expect(getRefusal(makeLlm({ refusal: null }))).toBeNull();
    expect(getRefusal(makeLlm({ refusal: "" }))).toBeNull();
    expect(getRefusal(makeLlm({}))).toBeNull();
    expect(hasRefusal(makeLlm({ refusal: "" }))).toBe(false);
  });

  test("safe on null / undefined llm", () => {
    expect(getRefusal(null)).toBeNull();
    expect(getRefusal(undefined)).toBeNull();
    expect(hasRefusal(null)).toBe(false);
  });
});

describe("refusalCompareState", () => {
  test("both refused → not a divergence", () => {
    const s = refusalCompareState(makeLlm({ refusal: "no" }), makeLlm({ refusal: "nope" }));
    expect(s).toEqual({ a: true, b: true, diverges: false });
  });

  test("one-sided refusal → divergence", () => {
    expect(refusalCompareState(makeLlm({ refusal: "no" }), makeLlm({})).diverges).toBe(true);
    expect(refusalCompareState(makeLlm({}), makeLlm({ refusal: "no" })).diverges).toBe(true);
  });

  test("neither refused → not a divergence", () => {
    expect(refusalCompareState(makeLlm({}), makeLlm({})).diverges).toBe(false);
    expect(refusalCompareState(null, null).diverges).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Cached tokens (Step 2: llm.usage.cached_tokens)
// ---------------------------------------------------------------------------

describe("getCachedTokens", () => {
  test("returns the number when reported", () => {
    expect(getCachedTokens({ cached_tokens: 128 })).toBe(128);
  });

  test("0 is a real value, not collapsed to null", () => {
    expect(getCachedTokens({ cached_tokens: 0 })).toBe(0);
  });

  test("null when not reported / missing / wrong type", () => {
    expect(getCachedTokens({ cached_tokens: null })).toBeNull();
    expect(getCachedTokens({})).toBeNull();
    expect(getCachedTokens(null)).toBeNull();
    expect(getCachedTokens({ cached_tokens: "5" as unknown as number })).toBeNull();
  });
});

describe("cachedTokensDiverges", () => {
  test("both reported and differ → diverges", () => {
    expect(cachedTokensDiverges({ cached_tokens: 10 }, { cached_tokens: 20 })).toBe(true);
  });

  test("both reported and equal (incl 0) → no divergence", () => {
    expect(cachedTokensDiverges({ cached_tokens: 10 }, { cached_tokens: 10 })).toBe(false);
    expect(cachedTokensDiverges({ cached_tokens: 0 }, { cached_tokens: 0 })).toBe(false);
  });

  test("one side absent → not a divergence (cannot compare unreported)", () => {
    expect(cachedTokensDiverges({ cached_tokens: 10 }, {})).toBe(false);
    expect(cachedTokensDiverges({}, { cached_tokens: 10 })).toBe(false);
    expect(cachedTokensDiverges(null, null)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Thinking channel (Step 2: thinking / redacted_thinking content blocks)
// ---------------------------------------------------------------------------

describe("getThinkingBlocks / hasThinking", () => {
  test("extracts thinking text blocks in order", () => {
    const llm = makeLlm({
      content_blocks: [
        { type: "thinking", thinking: "step one" },
        { type: "text", text: "answer" },
        { type: "thinking", thinking: "step two" },
      ],
    });
    expect(getThinkingBlocks(llm)).toEqual([
      { redacted: false, text: "step one" },
      { redacted: false, text: "step two" },
    ]);
    expect(hasThinking(llm)).toBe(true);
  });

  test("redacted_thinking blocks carry no text", () => {
    const llm = makeLlm({ content_blocks: [{ type: "redacted_thinking" }] });
    expect(getThinkingBlocks(llm)).toEqual([{ redacted: true, text: null }]);
  });

  test("ignores non-thinking blocks (text / tool_call / media)", () => {
    const llm = makeLlm({
      content_blocks: [
        { type: "text", text: "hi" },
        { type: "tool_call", name: "f" },
        { type: "image", url: "x" },
      ],
    });
    expect(getThinkingBlocks(llm)).toEqual([]);
    expect(hasThinking(llm)).toBe(false);
  });

  test("missing thinking text degrades to null, not crash", () => {
    const llm = makeLlm({ content_blocks: [{ type: "thinking" }] });
    expect(getThinkingBlocks(llm)).toEqual([{ redacted: false, text: null }]);
  });

  test("safe on null / undefined / malformed blocks", () => {
    expect(getThinkingBlocks(null)).toEqual([]);
    expect(getThinkingBlocks(undefined)).toEqual([]);
    const llm = makeLlm({ content_blocks: [null as unknown as Record<string, unknown>, { type: 42 as unknown as string }] });
    expect(getThinkingBlocks(llm)).toEqual([]);
  });
});
