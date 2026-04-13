/**
 * Derived tool-call linkage for run-detail.
 *
 * Produces a ToolCallLink per tool call in an LLM step, with:
 *   - linked tool step info (id, name, index, status) when found
 *   - confidence: exact | heuristic | unlinked
 *   - lifecycle: completed | failed | unmatched
 *
 * Priority:
 *   1. Exact  — shared tool_call_id
 *   2. Heuristic — same parent + same tool name + ordered alignment
 *   3. Unlinked — no match
 */

import type { TimelineStep } from "@/lib/types";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type LinkageConfidence = "exact" | "heuristic" | "unlinked";
export type ToolCallLifecycle = "completed" | "failed" | "unmatched";

export interface ToolCallLink {
  toolStepId: string;
  toolStepName: string;
  toolStepIndex: number;
  toolStepStatus: string;
  confidence: LinkageConfidence;
}

export interface ToolCallLinkResult {
  link: ToolCallLink | null;
  confidence: LinkageConfidence;
  lifecycle: ToolCallLifecycle;
}

// ---------------------------------------------------------------------------
// Lifecycle derivation (strict — same rules as Step 1)
// ---------------------------------------------------------------------------

export function deriveLifecycle(link: ToolCallLink | null): ToolCallLifecycle {
  if (!link) return "unmatched";
  if (link.toolStepStatus === "completed") return "completed";
  if (link.toolStepStatus === "failed") return "failed";
  return "unmatched";
}

// ---------------------------------------------------------------------------
// Tool-step name extraction
// ---------------------------------------------------------------------------

function toolStepName(step: TimelineStep): string {
  const metaName = step.metadata?.tool_name;
  if (typeof metaName === "string" && metaName) return metaName;
  return step.name;
}

// ---------------------------------------------------------------------------
// Core linker
// ---------------------------------------------------------------------------

/**
 * Build linkage for every tool call emitted by every LLM step in the timeline.
 *
 * Returns two maps:
 *   - `callLinks`:  Map<callKey, ToolCallLinkResult>
 *       where callKey = `${llmStepId}:${callIndex}`
 *   - `toolStepToLlm`: Map<toolStepId, { llmStep, confidence }>
 *       reverse lookup for the tool-step back-link UI
 */
export function buildToolCallLinkage(steps: TimelineStep[]): {
  callLinks: Map<string, ToolCallLinkResult>;
  toolStepToLlm: Map<string, { llmStep: TimelineStep; confidence: LinkageConfidence }>;
} {
  const callLinks = new Map<string, ToolCallLinkResult>();
  const toolStepToLlm = new Map<string, { llmStep: TimelineStep; confidence: LinkageConfidence }>();

  // Index: tool_call_id → tool step (for exact matching)
  const idToToolStep = new Map<string, TimelineStep>();
  // Index: all tool steps for heuristic pool
  const toolSteps: TimelineStep[] = [];

  for (const s of steps) {
    if (s.step_type === "tool") {
      toolSteps.push(s);
      const tcId = s.metadata?.tool_call_id;
      if (typeof tcId === "string" && tcId) {
        idToToolStep.set(tcId, s);
      }
    }
  }

  // Track which tool steps have been claimed (by any match)
  const claimed = new Set<string>();

  // Phase 1: exact matches for all LLM steps
  for (const llmStep of steps) {
    const calls = llmStep.llm?.output?.tool_calls;
    if (!calls?.length) continue;

    for (let ci = 0; ci < calls.length; ci++) {
      const tc = calls[ci] as Record<string, unknown>;
      const callId = typeof tc.id === "string" ? tc.id : null;
      const key = `${llmStep.id}:${ci}`;

      if (callId) {
        const matched = idToToolStep.get(callId);
        if (matched) {
          const link: ToolCallLink = {
            toolStepId: matched.id,
            toolStepName: matched.name,
            toolStepIndex: matched.sequence_index,
            toolStepStatus: matched.status,
            confidence: "exact",
          };
          callLinks.set(key, { link, confidence: "exact", lifecycle: deriveLifecycle(link) });
          toolStepToLlm.set(matched.id, { llmStep, confidence: "exact" });
          claimed.add(matched.id);
        }
      }
    }
  }

  // Phase 2: heuristic fallback for unresolved calls
  for (const llmStep of steps) {
    const calls = llmStep.llm?.output?.tool_calls;
    if (!calls?.length) continue;

    // Collect unresolved calls from this LLM step
    const unresolvedIndices: number[] = [];
    const unresolvedNames: string[] = [];
    for (let ci = 0; ci < calls.length; ci++) {
      const key = `${llmStep.id}:${ci}`;
      if (callLinks.has(key)) continue;
      const tc = calls[ci] as Record<string, unknown>;
      const name = typeof tc.name === "string" ? tc.name : "";
      unresolvedIndices.push(ci);
      unresolvedNames.push(name);
    }

    if (unresolvedIndices.length === 0) continue;

    // Find candidate tool steps:
    // Tier 1: unclaimed tool steps with parent_step_id === llmStep.id
    // Tier 2: unclaimed tool steps after llmStep (by sequence_index), no parent or different parent
    const tier1: TimelineStep[] = [];
    const tier2: TimelineStep[] = [];

    for (const ts of toolSteps) {
      if (claimed.has(ts.id)) continue;
      if (ts.parent_step_id === llmStep.id) {
        tier1.push(ts);
      } else if (ts.sequence_index > llmStep.sequence_index) {
        tier2.push(ts);
      }
    }

    // Sort both tiers by sequence_index for ordered alignment
    tier1.sort((a, b) => a.sequence_index - b.sequence_index);
    tier2.sort((a, b) => a.sequence_index - b.sequence_index);

    // Prefer tier1 candidates; fall back to tier2 only if tier1 has no match
    const candidates = tier1.length > 0 ? tier1 : tier2;

    // Ordered alignment: match nth unresolved call to nth name-compatible candidate
    const candidateClaimed = new Set<string>();

    for (let ui = 0; ui < unresolvedIndices.length; ui++) {
      const callName = unresolvedNames[ui];
      if (!callName) continue;

      let bestMatch: TimelineStep | null = null;

      for (const cand of candidates) {
        if (candidateClaimed.has(cand.id)) continue;
        const candName = toolStepName(cand);
        if (candName !== callName) continue;
        bestMatch = cand;
        break;
      }

      if (!bestMatch) continue;

      const ci = unresolvedIndices[ui];
      const key = `${llmStep.id}:${ci}`;
      const link: ToolCallLink = {
        toolStepId: bestMatch.id,
        toolStepName: bestMatch.name,
        toolStepIndex: bestMatch.sequence_index,
        toolStepStatus: bestMatch.status,
        confidence: "heuristic",
      };
      callLinks.set(key, { link, confidence: "heuristic", lifecycle: deriveLifecycle(link) });
      toolStepToLlm.set(bestMatch.id, { llmStep, confidence: "heuristic" });
      claimed.add(bestMatch.id);
      candidateClaimed.add(bestMatch.id);
    }
  }

  // Phase 3: fill unlinked for any remaining calls
  for (const llmStep of steps) {
    const calls = llmStep.llm?.output?.tool_calls;
    if (!calls?.length) continue;
    for (let ci = 0; ci < calls.length; ci++) {
      const key = `${llmStep.id}:${ci}`;
      if (!callLinks.has(key)) {
        callLinks.set(key, { link: null, confidence: "unlinked", lifecycle: "unmatched" });
      }
    }
  }

  return { callLinks, toolStepToLlm };
}
