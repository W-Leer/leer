/**
 * MCP / capability / retrieval metadata detection helpers.
 *
 * Two API layers:
 *   1. **Raw-metadata functions** (`isMcpMeta`, `getCapabilityKindFromMeta`, …)
 *      accept a plain metadata dict and are safe to call from both run-detail
 *      and compare pages.
 *   2. **Step-wrapper conveniences** (`isMcpStep`, `getCapabilityKind`, …)
 *      accept `{ metadata }` objects for ergonomic use in run-detail.
 *
 * Step 4 (compare) should import the raw-metadata variants directly so
 * detection rules stay in one place and never drift between pages.
 */

import type { CapabilityKind } from "@/lib/types";

export type Meta = Record<string, unknown> | null | undefined;

// ---------------------------------------------------------------------------
// Raw-metadata detection (reusable by both run-detail and compare)
// ---------------------------------------------------------------------------

export function isMcpMeta(meta: Meta): boolean {
  return meta?.protocol_kind === "mcp";
}

export function getCapabilityKindFromMeta(meta: Meta): CapabilityKind | null {
  const v = meta?.capability_kind;
  if (typeof v === "string" && (v === "tool" || v === "mcp_tool" || v === "retrieval" || v === "skill" || v === "unknown")) {
    return v;
  }
  return null;
}

export function isRetrievalMeta(meta: Meta): boolean {
  return getCapabilityKindFromMeta(meta) === "retrieval" || typeof meta?.retrieval_stage === "string";
}

export function getRetrievalStageFromMeta(meta: Meta): string | null {
  const v = meta?.retrieval_stage;
  return typeof v === "string" ? v : null;
}

export interface McpDisplayInfo {
  operationKind: string | null;
  targetName: string | null;
  serverName: string | null;
  serverId: string | null;
  transportKind: string | null;
}

export function getMcpDisplayInfoFromMeta(meta: Meta): McpDisplayInfo | null {
  if (!isMcpMeta(meta)) return null;
  return {
    operationKind: _str(meta!.operation_kind),
    targetName: _str(meta!.target_name),
    serverName: _str(meta!.server_name),
    serverId: _str(meta!.server_id),
    transportKind: _str(meta!.transport_kind),
  };
}

// ---------------------------------------------------------------------------
// Step-wrapper conveniences (call raw functions on step.metadata)
// ---------------------------------------------------------------------------

export function isMcpStep(step: { metadata: Meta }): boolean {
  return isMcpMeta(step.metadata);
}

export function getCapabilityKind(step: { metadata: Meta }): CapabilityKind | null {
  return getCapabilityKindFromMeta(step.metadata);
}

export function isRetrievalStep(step: { metadata: Meta }): boolean {
  return isRetrievalMeta(step.metadata);
}

export function getRetrievalStage(step: { metadata: Meta }): string | null {
  return getRetrievalStageFromMeta(step.metadata);
}

export function getMcpDisplayInfo(step: { metadata: Meta }): McpDisplayInfo | null {
  return getMcpDisplayInfoFromMeta(step.metadata);
}

// ---------------------------------------------------------------------------
// Metadata exclusion keys (avoid duplicate display in "Extra metadata")
// ---------------------------------------------------------------------------

/** Keys already handled by tool-step dedicated UI rows. */
export const TOOL_META_KEYS = new Set([
  "tool_name",
  "tool_call_id",
  "provider",
  "model",
]);

/** Keys promoted to MCP-specific UI rows. */
export const MCP_META_KEYS = new Set([
  "protocol_kind",
  "operation_kind",
  "target_name",
  "server_name",
  "server_id",
  "transport_kind",
]);

/** Keys promoted to capability/skill UI rows. */
export const CAPABILITY_META_KEYS = new Set([
  "capability_kind",
  "capability_name",
  "capability_label",
  "capability_namespace",
  "skill_name",
  "skill_label",
]);

/** Keys promoted to retrieval-specific UI rows. */
export const RETRIEVAL_META_KEYS = new Set([
  "retrieval_stage",
  "retrieval_backend",
  "index_name",
  "query_text",
  "query_count",
  "candidate_count",
  "selected_count",
  "context_token_estimate",
  "latency_ms",
]);

/** Parent-linkage keys excluded from all extra metadata displays. */
export const LINKAGE_META_KEYS = new Set([
  "parent_llm_step_id",
  "parent_tool_step_id",
]);

/**
 * Load-bearing retrieval fields for Step 4 compare diffing.
 * Compare should diff these rather than the full retrieval key set.
 */
export const RETRIEVAL_DIFF_KEYS = [
  "retrieval_stage",
  "retrieval_backend",
  "index_name",
  "candidate_count",
  "selected_count",
  "context_token_estimate",
] as const;

/**
 * Return metadata entries that should render in the generic "Extra metadata"
 * section, after removing all keys handled by dedicated UI rows.
 *
 * Used by both run-detail and compare pages — do not duplicate this logic.
 */
export function extraMetadataEntries(
  meta: Meta,
  isTool: boolean,
): [string, unknown][] {
  if (!meta) return [];
  const exclude = new Set<string>();
  if (isTool) for (const k of TOOL_META_KEYS) exclude.add(k);

  if (isMcpMeta(meta)) for (const k of MCP_META_KEYS) exclude.add(k);

  if (typeof meta.capability_kind === "string") {
    for (const k of CAPABILITY_META_KEYS) exclude.add(k);
  }

  if (isRetrievalMeta(meta)) for (const k of RETRIEVAL_META_KEYS) exclude.add(k);

  for (const k of LINKAGE_META_KEYS) exclude.add(k);

  return Object.entries(meta).filter(([k]) => !exclude.has(k));
}

// ---------------------------------------------------------------------------
// Badge styling
// ---------------------------------------------------------------------------

export const CAPABILITY_BADGE: Record<string, string> = {
  mcp_tool: "bg-violet-50 text-violet-600 dark:bg-violet-950/30 dark:text-violet-400",
  retrieval: "bg-teal-50 text-teal-600 dark:bg-teal-950/30 dark:text-teal-400",
  skill: "bg-indigo-50 text-indigo-500 dark:bg-indigo-950/30 dark:text-indigo-400",
  tool: "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400",
  unknown: "bg-neutral-100 text-neutral-400",
};

export const MCP_BADGE = "bg-violet-50 text-violet-600 dark:bg-violet-950/30 dark:text-violet-400";
export const RETRIEVAL_STAGE_BADGE = "bg-teal-50 text-teal-600 dark:bg-teal-950/30 dark:text-teal-400";

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

function _str(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}
