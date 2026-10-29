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
  getParsedOutput,
  isJsonOutput,
  jsonOutputDiverges,
  toolCallLabel,
  getRefusalCategory,
  isProviderTool,
  providerToolLabel,
} from "./provider-hardening";
import type { LLMShape } from "./types";

/** Build a minimal LLMShape with overridable output/usage/meta. */
function makeLlm(partial: {
  content_blocks?: Record<string, unknown>[];
  cached_tokens?: number | null;
  refusal?: string | null;
  refusal_category?: string | null;
  parsed?: unknown;
  output_is_json?: boolean;
}): LLMShape {
  return {
    provider: "openai",
    model: "gpt-4.1",
    input: { system: null, messages: [], tools: [], params: {} },
    output: {
      text: "hi",
      tool_calls: [],
      content_blocks: partial.content_blocks ?? [],
      parsed: partial.parsed,
    },
    usage: {
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
      cached_tokens: partial.cached_tokens,
    },
    meta: {
      finish_reason: null,
      request_id: null,
      latency_ms: null,
      refusal: partial.refusal,
      refusal_category: partial.refusal_category,
      output_is_json: partial.output_is_json,
    },
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

// ---------------------------------------------------------------------------
// Structured output (Step 1: output.parsed / meta.output_is_json)
// ---------------------------------------------------------------------------

describe("getParsedOutput", () => {
  test("returns the parsed object when present", () => {
    const obj = { intent: "q", confidence: 0.9 };
    expect(getParsedOutput(makeLlm({ parsed: obj }))).toEqual(obj);
  });

  test("returns parsed arrays", () => {
    expect(getParsedOutput(makeLlm({ parsed: [1, 2, 3] }))).toEqual([1, 2, 3]);
  });

  test("null when absent / scalar / wrong type", () => {
    expect(getParsedOutput(makeLlm({}))).toBeNull();
    expect(getParsedOutput(makeLlm({ parsed: null }))).toBeNull();
    expect(getParsedOutput(makeLlm({ parsed: 42 as unknown }))).toBeNull();
    expect(getParsedOutput(makeLlm({ parsed: "hi" as unknown }))).toBeNull();
  });

  test("safe on null / undefined llm", () => {
    expect(getParsedOutput(null)).toBeNull();
    expect(getParsedOutput(undefined)).toBeNull();
  });
});

describe("isJsonOutput", () => {
  test("true when meta.output_is_json is true", () => {
    expect(isJsonOutput(makeLlm({ output_is_json: true }))).toBe(true);
  });

  test("true when a parsed object is present even without the flag", () => {
    expect(isJsonOutput(makeLlm({ parsed: { a: 1 } }))).toBe(true);
  });

  test("false for plain text outputs and missing data", () => {
    expect(isJsonOutput(makeLlm({}))).toBe(false);
    expect(isJsonOutput(makeLlm({ output_is_json: false }))).toBe(false);
    expect(isJsonOutput(null)).toBe(false);
  });
});

describe("jsonOutputDiverges", () => {
  test("one side JSON, other not → diverges", () => {
    expect(jsonOutputDiverges(makeLlm({ output_is_json: true }), makeLlm({}))).toBe(true);
    expect(jsonOutputDiverges(makeLlm({}), makeLlm({ parsed: { a: 1 } }))).toBe(true);
  });

  test("both JSON or both not → no divergence", () => {
    expect(jsonOutputDiverges(makeLlm({ output_is_json: true }), makeLlm({ parsed: { a: 1 } }))).toBe(false);
    expect(jsonOutputDiverges(makeLlm({}), makeLlm({}))).toBe(false);
    expect(jsonOutputDiverges(null, null)).toBe(false);
  });
});

describe("toolCallLabel", () => {
  test("plain name when there is no namespace", () => {
    expect(toolCallLabel({ name: "search" })).toBe("search");
  });

  test("qualifies the name with its namespace", () => {
    expect(toolCallLabel({ name: "search", namespace: "github" })).toBe("github.search");
  });

  test("same-named tools in different namespaces get different labels", () => {
    expect(toolCallLabel({ name: "search", namespace: "github" })).not.toBe(
      toolCallLabel({ name: "search", namespace: "jira" }),
    );
  });

  test("falls back when the name is missing", () => {
    expect(toolCallLabel({})).toBe("call");
    expect(toolCallLabel(null, "?")).toBe("?");
    expect(toolCallLabel({ namespace: "github" }, "?")).toBe("?");
  });

  test("ignores a non-string namespace", () => {
    expect(toolCallLabel({ name: "search", namespace: 42 })).toBe("search");
  });
});

describe("getRefusalCategory", () => {
  test("returns the category alongside a refusal", () => {
    expect(getRefusalCategory(makeLlm({ refusal: "No.", refusal_category: "cyber" }))).toBe("cyber");
  });

  test("null without a refusal, on old records, or with no llm", () => {
    expect(getRefusalCategory(makeLlm({ refusal_category: "cyber" }))).toBeNull();
    expect(getRefusalCategory(makeLlm({ refusal: "No." }))).toBeNull();
    expect(getRefusalCategory(null)).toBeNull();
  });
});

describe("isProviderTool / providerToolLabel", () => {
  const search = { type: "provider_tool", name: "web_search", provider_part_type: "web_search_call" };

  test("detects provider-run tool parts only", () => {
    expect(isProviderTool(search)).toBe(true);
    expect(isProviderTool({ type: "tool_call", name: "x" })).toBe(false);
    expect(isProviderTool({ type: "file" })).toBe(false);
  });

  test("labels with the MCP server when present", () => {
    expect(providerToolLabel(search)).toBe("web_search");
    expect(providerToolLabel({ type: "provider_tool", name: "read_wiki", server: "deepwiki" })).toBe("deepwiki.read_wiki");
  });

  test("falls back to the provider type when the name is unknown", () => {
    expect(providerToolLabel({ type: "provider_tool", provider_part_type: "code_execution_tool_result" })).toBe(
      "code_execution_tool_result",
    );
  });
});
