export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-800",
  running: "bg-blue-100 text-blue-800",
  failed: "bg-red-100 text-red-800",
  pending: "bg-neutral-100 text-neutral-600",
};

export function statusClass(status: string): string {
  return STATUS_COLORS[status] ?? "bg-neutral-100 text-neutral-600";
}

// ---------------------------------------------------------------------------
// Deep-parse helpers for double-encoded JSON
// ---------------------------------------------------------------------------

function deepParse(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return deepParse(JSON.parse(value));
  } catch {
    return value;
  }
}

type Dict = Record<string, unknown>;

/**
 * Return a structured representation of an output/error summary:
 *   - string[]  for array-of-strings (e.g. summary bullets)
 *   - string    for a single text value
 *   - null      if nothing meaningful
 */
export function extractLines(summary: Dict | null | undefined): string[] | null {
  if (!summary) return null;
  const parsed = deepParse(summary);
  return toLinesInner(parsed);
}

function toLinesInner(obj: unknown): string[] | null {
  if (obj == null) return null;
  if (typeof obj === "string") {
    const trimmed = obj.trim();
    return trimmed ? trimmed.split("\n") : null;
  }
  if (Array.isArray(obj)) {
    const flat = obj.flatMap((v) => toLinesInner(v) ?? []);
    return flat.length ? flat : null;
  }
  if (typeof obj === "object") {
    const rec = obj as Dict;
    if ("summary" in rec) return toLinesInner(rec.summary);
    if ("result_preview" in rec) return toLinesInner(rec.result_preview);
    if ("prompt_preview" in rec) return toLinesInner(rec.prompt_preview);
    if ("message" in rec) return toLinesInner(rec.message);
    if ("traceback" in rec) return toLinesInner(rec.traceback);
    const vals = Object.values(rec);
    if (vals.length === 1) return toLinesInner(vals[0]);
    return [JSON.stringify(obj, null, 2)];
  }
  return [String(obj)];
}

/**
 * Single-string version: joins lines, optionally truncates.
 */
export function formatSummary(
  summary: Dict | null | undefined,
  maxLen?: number,
): string {
  const lines = extractLines(summary);
  if (!lines) return "";
  const text = lines.join("\n");
  if (maxLen && text.length > maxLen) return text.slice(0, maxLen) + "…";
  return text;
}

/**
 * Return the raw JSON string for "View raw" toggle.
 */
export function rawJson(obj: Dict | null | undefined): string {
  if (!obj) return "";
  return JSON.stringify(obj, null, 2);
}

// ---------------------------------------------------------------------------
// Error-specific helpers
// ---------------------------------------------------------------------------

/**
 * Extract the first meaningful error line from an error summary.
 * e.g. "TimeoutError: LLM provider timed out after 30s"
 */
export function errorHeadline(summary: Dict | null | undefined): string {
  if (!summary) return "";
  const parsed = deepParse(summary);
  if (typeof parsed === "string") {
    const lines = parsed.trim().split("\n");
    const last = lines[lines.length - 1]?.trim();
    if (last) return last;
    return lines[0]?.trim() ?? "";
  }
  if (parsed && typeof parsed === "object") {
    const rec = parsed as Dict;
    if ("message" in rec && typeof rec.message === "string") return rec.message;
    if ("traceback" in rec && typeof rec.traceback === "string") {
      const lines = rec.traceback.trim().split("\n");
      return lines[lines.length - 1]?.trim() ?? "";
    }
  }
  return formatSummary(summary);
}

/**
 * Return the full traceback text if present, for the detail/collapsed view.
 */
export function errorDetail(summary: Dict | null | undefined): string | null {
  if (!summary) return null;
  const parsed = deepParse(summary);
  if (typeof parsed === "string") return parsed;
  if (parsed && typeof parsed === "object") {
    const rec = parsed as Dict;
    if ("traceback" in rec && typeof rec.traceback === "string") return rec.traceback;
  }
  return null;
}

/**
 * Preview for the run list: return first N lines as an array.
 */
export function previewLines(
  summary: Dict | null | undefined,
  maxLines = 3,
): string[] {
  const lines = extractLines(summary);
  if (!lines) return [];
  return lines.slice(0, maxLines);
}
