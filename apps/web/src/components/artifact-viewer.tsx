"use client";

import { useState, useCallback } from "react";
import { fetchArtifactContent } from "@/lib/api";
import type { StepArtifactRef } from "@/lib/types";
import { StructuredValue } from "@/components/structured-value";
import { isMediaArtifact, MediaArtifactRenderer } from "@/components/media-artifact";

type LoadState = "idle" | "loading" | "loaded" | "error";

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Renders a single artifact with blob-awareness.
 *
 * Inline artifacts render data immediately.
 * Blob-backed artifacts show a compact summary with a "Load" button
 * that fetches the full content on demand.
 */
export function ArtifactViewer({ artifact }: { artifact: StepArtifactRef }) {
  if (isMediaArtifact(artifact)) {
    return <MediaArtifactRenderer artifact={artifact} />;
  }

  const isBlob = artifact.storage_kind === "blob";
  const hasInlineData = artifact.inline_data != null;

  const [loadState, setLoadState] = useState<LoadState>(
    hasInlineData ? "loaded" : "idle",
  );
  const [resolvedData, setResolvedData] = useState<Record<string, unknown> | null>(
    hasInlineData ? (artifact.inline_data ?? null) : null,
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [raw, setRaw] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const handleLoad = useCallback(async () => {
    setLoadState("loading");
    setErrorMsg(null);
    try {
      const resp = await fetchArtifactContent(artifact.id);
      setResolvedData(resp.data);
      setLoadState("loaded");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load artifact");
      setLoadState("error");
    }
  }, [artifact.id]);

  const dataLoaded = loadState === "loaded" && resolvedData != null;
  const rawText = dataLoaded ? JSON.stringify(resolvedData, null, 2) : "";
  const copyText = rawText;

  return (
    <div className="rounded-md border border-neutral-200 bg-white">
      {/* Compact header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <div className="flex items-center gap-2">
          <span className={`text-[10px] transition-transform duration-150 ${expanded ? "rotate-90" : ""} text-neutral-400`}>
            ▶
          </span>
          <span className="font-mono text-[11px] font-medium text-neutral-600">
            {artifact.kind}
          </span>
          {artifact.role && (
            <span className="text-[10px] text-neutral-400">{artifact.role}</span>
          )}
          {isBlob && (
            <span className="rounded bg-indigo-50 px-1.5 py-px text-[9px] font-medium text-indigo-500 dark:bg-indigo-950/30 dark:text-indigo-400">
              blob
            </span>
          )}
          {artifact.size_bytes != null && (
            <span className="text-[10px] tabular-nums text-neutral-400">
              {formatBytes(artifact.size_bytes)}
            </span>
          )}
        </div>
        {artifact.sequence_index != null && (
          <span className="font-mono text-[10px] text-neutral-400">
            #{artifact.sequence_index}
          </span>
        )}
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-neutral-100 px-3 pb-3 pt-2">
          {/* Preview text */}
          {artifact.preview_text && !dataLoaded && (
            <p className="mb-2 font-mono text-xs text-neutral-500">
              {artifact.preview_text}
            </p>
          )}

          {/* Load states */}
          {loadState === "idle" && (
            <button
              onClick={handleLoad}
              className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50 hover:text-neutral-700"
            >
              Load artifact
            </button>
          )}

          {loadState === "loading" && (
            <p className="text-xs text-neutral-400">Loading…</p>
          )}

          {loadState === "error" && (
            <div className="space-y-2">
              <p className="text-xs text-red-500">{errorMsg}</p>
              <button
                onClick={handleLoad}
                className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50 hover:text-neutral-700"
              >
                Retry
              </button>
            </div>
          )}

          {/* Loaded data */}
          {dataLoaded && (
            <div>
              <div className="mb-1.5 flex justify-end gap-1">
                <CopyBtn text={copyText} />
                <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
              </div>
              {raw ? (
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 px-3 py-2 font-mono text-xs leading-6 text-neutral-600">
                  {rawText}
                </pre>
              ) : (
                <StructuredValue value={resolvedData} />
              )}
            </div>
          )}

          {loadState === "loaded" && resolvedData == null && (
            <p className="text-xs italic text-neutral-400">No artifact content</p>
          )}

          {/* SHA256 in expanded view only */}
          {artifact.sha256 && (
            <div className="mt-2 font-mono text-[10px] text-neutral-400">
              sha256: {artifact.sha256}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Internal micro-components (mirrors patterns in llm-step-detail)     */
/* ------------------------------------------------------------------ */

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);

  return (
    <button
      onClick={copy}
      className="rounded px-1.5 py-0.5 text-[10px] text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function RawToggle({ raw, onToggle }: { raw: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600"
    >
      {raw ? "Formatted" : "Raw"}
    </button>
  );
}
