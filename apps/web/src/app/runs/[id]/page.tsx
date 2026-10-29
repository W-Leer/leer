"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiFetch, fetchArtifactContent } from "@/lib/api";
import {
  errorDetail,
  errorHeadline,
  extractLines,
  formatDate,
  formatDuration,
  rawJson,
  resolveData,
  statusClass,
} from "@/lib/format";
import type { TimelineResponse, TimelineStep, TimelineEvent, StepArtifactRef } from "@/lib/types";
import { StructuredValue } from "@/components/structured-value";
import { LlmStepDetail } from "@/components/llm-step-detail";
import { ArtifactViewer } from "@/components/artifact-viewer";
import { buildToolCallLinkage } from "@/lib/tool-linkage";
import type { ToolCallLinkResult, LinkageConfidence } from "@/lib/tool-linkage";
import {
  isMcpStep,
  getCapabilityKind,
  isRetrievalStep,
  getRetrievalStage,
  getMcpDisplayInfo,
  extraMetadataEntries,
  CAPABILITY_BADGE,
  MCP_BADGE,
  RETRIEVAL_STAGE_BADGE,
} from "@/lib/step-metadata";
import { isPartialCapture, hasRefusal, getRefusalCategory, isJsonOutput, PARTIAL_CAPTURE_TOOLTIP } from "@/lib/provider-hardening";
import { ChevronRight, GitCompareArrows } from "lucide-react";

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedStepId, setExpandedStepId] = useState<string | null>(null);
  const [eventsExpanded, setEventsExpanded] = useState(false);

  useEffect(() => {
    if (!id) return;
    apiFetch<TimelineResponse>(`/v1/runs/${id}/timeline`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  const steps = useMemo(() => data?.steps ?? [], [data]);

  // Build tool-call linkage (exact + heuristic + unlinked)
  const { callLinks, toolStepToLlm } = useMemo(
    () => buildToolCallLinkage(steps),
    [steps],
  );

  // Parent/child hierarchy maps — derived client-side, no reordering
  const { stepById, childrenByParentId } = useMemo(() => {
    const byId = new Map<string, TimelineStep>();
    const byParent = new Map<string, TimelineStep[]>();
    for (const s of steps) {
      byId.set(s.id, s);
      if (s.parent_step_id) {
        const siblings = byParent.get(s.parent_step_id);
        if (siblings) siblings.push(s);
        else byParent.set(s.parent_step_id, [s]);
      }
    }
    return { stepById: byId, childrenByParentId: byParent };
  }, [steps]);

  const scrollToStep = useCallback((stepId: string) => {
    const el = document.getElementById(`step-${stepId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setExpandedStepId(stepId);
    }
  }, []);

  if (loading) return <p className="text-neutral-500">Loading…</p>;

  if (error) {
    return (
      <div className="rounded-lg bg-[var(--tint-error-block)] p-4 text-sm text-[var(--error-text)]">
        Failed to load run: {error}
      </div>
    );
  }

  if (!data) return null;

  const { run, events } = data;

  return (
    <div className="max-w-4xl">
      {/* Breadcrumb */}
      <nav className="mb-4 flex items-center gap-1 text-[12px]">
        <Link href="/" className="text-neutral-400 transition-colors hover:text-neutral-700">
          Runs
        </Link>
        <ChevronRight size={12} className="text-neutral-300" />
        <span className="truncate font-medium text-neutral-600">{run.workflow_name}</span>
      </nav>

      {/* Run header */}
      <div className="mb-10 rounded-lg bg-white p-6 shadow-[0_1px_4px_rgba(0,0,0,0.05)]">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-neutral-900">{run.workflow_name}</h1>
            <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${statusClass(run.status)}`}>
              {run.status}
            </span>
          </div>
          <Link
            href={`/compare?a=${id}`}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50 hover:text-neutral-700"
          >
            <GitCompareArrows size={13} />
            Compare
          </Link>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-3">
          <Field label="Created" value={formatDate(run.created_at)} />
          <Field label="Started" value={run.started_at ? formatDate(run.started_at) : "—"} />
          <Field label="Ended" value={run.ended_at ? formatDate(run.ended_at) : "—"} />
          <Field label="Duration" value={formatDuration(run.total_duration_ms)} />
          <Field label="Steps" value={`${run.completed_steps}/${run.total_steps}`} />
          {run.failed_steps > 0 && (
            <Field label="Failed" value={String(run.failed_steps)} />
          )}
        </div>

        {run.output_summary && (
          <OutputBlock label="Output" data={run.output_summary} />
        )}

        {run.error_summary && (
          <ErrorBlock data={run.error_summary} />
        )}
      </div>

      {/* Steps timeline */}
      <section className="mb-12">
        <h2 className="mb-6 text-lg font-semibold tracking-tight text-neutral-900">Steps</h2>
        {steps.length === 0 ? (
          <p className="text-sm text-neutral-500">No steps recorded.</p>
        ) : (
          <div className="relative border-l-2 border-neutral-300 pl-7">
            {steps.map((s) => (
              <StepCard
                key={s.id}
                step={s}
                expanded={expandedStepId === s.id}
                onToggle={() => setExpandedStepId(expandedStepId === s.id ? null : s.id)}
                callLinks={callLinks}
                toolStepToLlm={toolStepToLlm}
                stepById={stepById}
                childrenByParentId={childrenByParentId}
                onJumpToStep={scrollToStep}
              />
            ))}
          </div>
        )}
      </section>

      {/* Events list — collapsible, grouped by step */}
      {events.length > 0 && (
        <EventsSection
          events={events}
          expanded={eventsExpanded}
          onToggle={() => setEventsExpanded(!eventsExpanded)}
          runStartedAt={run.started_at}
          stepById={stepById}
        />
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-neutral-400">{label}: </span>
      <span className="font-medium text-neutral-700">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Copy button
// ---------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="rounded px-1.5 py-0.5 text-[10px] text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600"
      title="Copy to clipboard"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Output block (run-level)
// ---------------------------------------------------------------------------

function OutputBlock({ label, data }: { label: string; data: Record<string, unknown> }) {
  const [raw, setRaw] = useState(false);
  const resolved = resolveData(data);
  const rawText = rawJson(data);
  const copyText = extractLines(data)?.join("\n") ?? rawText;
  if (resolved == null && !rawText) return null;

  return (
    <div className="mt-6">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium text-neutral-500">{label}</span>
        <div className="flex items-center gap-1">
          <CopyButton text={raw ? rawText : copyText} />
          <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
        </div>
      </div>
      <div className="rounded-md bg-neutral-50/80 px-4 py-3">
        {raw ? (
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-neutral-600">
            {rawText}
          </pre>
        ) : (
          <StructuredValue value={resolved} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error block (run-level)
// ---------------------------------------------------------------------------

function ErrorBlock({ data }: { data: Record<string, unknown> }) {
  const [raw, setRaw] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const headline = errorHeadline(data);
  const detail = errorDetail(data);
  const rawText = rawJson(data);
  if (!headline && !rawText) return null;

  return (
    <div className="mt-6">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium text-[var(--error-accent)]">Error</span>
        <div className="flex items-center gap-1">
          <CopyButton text={raw ? rawText : (detail ?? headline)} />
          <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
        </div>
      </div>
      <div className="rounded-md bg-[var(--tint-error-block)] px-4 py-3">
        {raw ? (
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-[var(--error-text)]">
            {rawText}
          </pre>
        ) : detail ? (
          <>
            <p className="font-mono text-[13px] font-medium leading-snug text-[var(--error-text-emphasis)]">
              {headline}
            </p>
            {detail !== headline && (
              <>
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="mt-2.5 text-xs font-medium text-[var(--error-accent)] hover:text-[var(--error-text)]"
                >
                  {expanded ? "Hide full traceback" : "Show full traceback"}
                </button>
                {expanded && (
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-[var(--error-text-muted)]">
                    {detail}
                  </pre>
                )}
              </>
            )}
          </>
        ) : (
          <StructuredValue value={resolveData(data)} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Raw toggle button
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Step card (clickable, expandable)
// ---------------------------------------------------------------------------

function truncateId(id: string, max = 16): string {
  return id.length > max ? id.slice(0, max) + "…" : id;
}

function stepTypeBadge(stepType: string): string {
  if (stepType === "llm") return "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400";
  if (stepType === "tool") return "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400";
  return "bg-neutral-100 text-neutral-400";
}

function stepDuration(step: TimelineStep): string {
  if (!step.started_at || !step.ended_at) return "—";
  const ms = new Date(step.ended_at).getTime() - new Date(step.started_at).getTime();
  return formatDuration(ms);
}

function StepCard({
  step,
  expanded,
  onToggle,
  callLinks,
  toolStepToLlm,
  stepById,
  childrenByParentId,
  onJumpToStep,
}: {
  step: TimelineStep;
  expanded: boolean;
  onToggle: () => void;
  callLinks: Map<string, ToolCallLinkResult>;
  toolStepToLlm: Map<string, { llmStep: TimelineStep; confidence: LinkageConfidence }>;
  stepById: Map<string, TimelineStep>;
  childrenByParentId: Map<string, TimelineStep[]>;
  onJumpToStep: (stepId: string) => void;
}) {
  const isTool = step.step_type === "tool";
  const toolCallId = isTool ? String(step.metadata?.tool_call_id ?? "") : "";
  const backLink = isTool ? toolStepToLlm.get(step.id) : undefined;
  const sourceLlmStep = backLink?.llmStep;
  const backLinkConfidence = backLink?.confidence ?? ("unlinked" as LinkageConfidence);

  // Parent/child hierarchy
  const isChildStep = !!step.parent_step_id;
  const parentStep = step.parent_step_id ? stepById.get(step.parent_step_id) : undefined;
  const children = childrenByParentId.get(step.id);
  const childCount = children?.length ?? 0;
  const allChildrenAreTools = childCount > 0 && children!.every((c) => c.step_type === "tool");

  // Extract stream events from llm_stream artifact (inline or lazy-fetched)
  const streamArtifact = useMemo(() => {
    if (step.step_type !== "llm") return undefined;
    return step.artifacts.find((a) => a.kind === "llm_stream");
  }, [step.step_type, step.artifacts]);

  const inlineStreamEvents = useMemo(() => {
    if (!streamArtifact?.inline_data) return undefined;
    const evts = streamArtifact.inline_data.events;
    return Array.isArray(evts) ? (evts as Record<string, unknown>[]) : undefined;
  }, [streamArtifact]);

  const streamIsBlob = streamArtifact != null && streamArtifact.storage_kind === "blob" && !streamArtifact.inline_data;

  const [blobStreamEvents, setBlobStreamEvents] = useState<Record<string, unknown>[] | undefined>(undefined);
  const [blobStreamLoading, setBlobStreamLoading] = useState(false);
  const [blobStreamError, setBlobStreamError] = useState<string | null>(null);

  const loadBlobStreamEvents = useCallback(async () => {
    if (!streamArtifact || !streamIsBlob) return;
    setBlobStreamLoading(true);
    setBlobStreamError(null);
    try {
      const resp = await fetchArtifactContent(streamArtifact.id);
      const evts = resp.data?.events;
      setBlobStreamEvents(Array.isArray(evts) ? (evts as Record<string, unknown>[]) : []);
    } catch (err) {
      setBlobStreamError(err instanceof Error ? err.message : "Failed to load stream events");
    } finally {
      setBlobStreamLoading(false);
    }
  }, [streamArtifact, streamIsBlob]);

  const streamEvents = inlineStreamEvents ?? blobStreamEvents;

  // Collect per-call linkage results for this LLM step
  const llmToolCallLinkResults = useMemo(() => {
    const calls = step.llm?.output?.tool_calls;
    if (!calls?.length) return undefined;
    const results = new Map<number, ToolCallLinkResult>();
    for (let ci = 0; ci < calls.length; ci++) {
      const key = `${step.id}:${ci}`;
      const result = callLinks.get(key);
      if (result) results.set(ci, result);
    }
    return results.size > 0 ? results : undefined;
  }, [step.id, step.llm, callLinks]);

  const dotColor = expanded
    ? "border-neutral-500 bg-neutral-500"
    : step.status === "failed"
      ? "border-[var(--error-dot)] bg-[var(--error-dot)]"
      : "border-neutral-300 bg-white";

  const contextLabel = parentStep
    ? `← ${parentStep.name} (#${parentStep.sequence_index})`
    : null;

  return (
    <div id={`step-${step.id}`} className={`relative mb-7 last:mb-0 ${isChildStep ? "ml-5" : ""}`}>
      {/* Timeline dot */}
      <div className={`absolute -left-[34px] top-[17px] h-2.5 w-2.5 rounded-full border-2 transition-colors duration-150 ${dotColor}`} />

      {/* Child step accent line */}
      {isChildStep && (
        <div className="absolute -left-[7px] top-0 bottom-0 w-[2px] rounded-full bg-amber-200 dark:bg-amber-800/40" />
      )}

      <div
        className={`rounded-lg transition-all duration-150 ${
          expanded
            ? "bg-white shadow-[0_1px_5px_rgba(0,0,0,0.06)]"
            : "bg-white hover:bg-neutral-50/60 hover:shadow-[0_1px_4px_rgba(0,0,0,0.04)]"
        }`}
      >
        {/* Clickable header */}
        <button onClick={onToggle} className="w-full cursor-pointer px-5 py-3.5 text-left">
          <div className="flex items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2 gap-y-1.5">
              <span className={`text-[10px] transition-transform duration-150 ${expanded ? "rotate-90" : ""} text-neutral-400`}>▶</span>
              <span className="text-[13px] font-semibold tracking-tight text-neutral-900">{step.name}</span>
              <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${stepTypeBadge(step.step_type)}`}>
                {step.step_type}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(step.status)}`}>
                {step.status}
              </span>
              {step.step_type === "llm" && (step.metadata?.stream as Record<string, unknown>)?.is_stream === true && (
                <span className="rounded px-1.5 py-0.5 font-mono text-[10px] bg-violet-50 text-violet-500 dark:bg-violet-950/30 dark:text-violet-400">
                  stream
                </span>
              )}
              {hasRefusal(step.llm) && (
                <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-rose-50 text-rose-600 dark:bg-rose-950/30 dark:text-rose-400">
                  {getRefusalCategory(step.llm) ? `refusal · ${getRefusalCategory(step.llm)}` : "refusal"}
                </span>
              )}
              {step.step_type === "llm" && isJsonOutput(step.llm) && (
                <span
                  title="Structured output — the model returned a JSON object/array."
                  className="rounded px-1.5 py-0.5 font-mono text-[10px] bg-sky-50 text-sky-600 dark:bg-sky-950/30 dark:text-sky-400"
                >
                  JSON
                </span>
              )}
              {isPartialCapture(step.metadata) && (
                <span
                  title={PARTIAL_CAPTURE_TOOLTIP}
                  className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400"
                >
                  partial
                </span>
              )}
              {isMcpStep(step) && (
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${MCP_BADGE}`}>MCP</span>
              )}
              {(() => {
                const ck = getCapabilityKind(step);
                return ck && ck !== "unknown" ? (
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${CAPABILITY_BADGE[ck] ?? CAPABILITY_BADGE.unknown}`}>
                    {ck}
                  </span>
                ) : null;
              })()}
              {(() => {
                const rs = getRetrievalStage(step);
                return rs ? (
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${RETRIEVAL_STAGE_BADGE}`}>{rs}</span>
                ) : null;
              })()}
              {childCount > 0 && (
                <span className="text-[10px] text-neutral-400">
                  {childCount} {allChildrenAreTools ? `tool call${childCount !== 1 ? "s" : ""}` : `child${childCount !== 1 ? "ren" : ""}`}
                </span>
              )}
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-x-4 gap-y-1 text-[11px] text-neutral-400">
              {step.model_name && (
                <span className="font-mono text-neutral-500">{step.model_name}</span>
              )}
              {isTool && !!toolCallId && (
                <span className="font-mono text-neutral-400" title={toolCallId}>{truncateId(toolCallId, 12)}</span>
              )}
              <span>{stepDuration(step)}</span>
              <span className="font-mono">#{step.sequence_index}</span>
            </div>
          </div>
          {/* Context line for child steps */}
          {contextLabel && (
            <div className="mt-1.5 pl-[22px] text-[11px] text-neutral-400">
              <span className="mr-1 text-amber-400">↳</span>
              {contextLabel}
            </div>
          )}
        </button>

        {/* Expand/collapse with CSS grid */}
        <div
          className={`grid transition-[grid-template-rows] duration-200 ease-in-out ${
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          }`}
        >
          <div className="overflow-hidden">
            {step.llm ? (
              <LlmStepDetail
                llm={step.llm}
                errorSummary={step.error_summary}
                toolCallLinkResults={llmToolCallLinkResults}
                onJumpToStep={onJumpToStep}
                durationMs={step.duration_ms}
                streamMeta={step.metadata?.stream as Record<string, unknown> | undefined}
                streamEvents={streamEvents}
                blobStreamState={streamIsBlob ? {
                  loading: blobStreamLoading,
                  error: blobStreamError,
                  loaded: blobStreamEvents != null,
                  onLoad: loadBlobStreamEvents,
                } : undefined}
                artifacts={step.artifacts}
              />
            ) : (
              <StepDetailPanel
                step={step}
                parentStep={parentStep}
                sourceLlmStep={sourceLlmStep}
                backLinkConfidence={backLinkConfidence}
                onJumpToStep={onJumpToStep}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step detail panel
// ---------------------------------------------------------------------------

function StepDetailPanel({
  step,
  parentStep,
  sourceLlmStep,
  backLinkConfidence,
  onJumpToStep,
}: {
  step: TimelineStep;
  parentStep?: TimelineStep;
  sourceLlmStep?: TimelineStep;
  backLinkConfidence?: LinkageConfidence;
  onJumpToStep?: (stepId: string) => void;
}) {
  const hasInput = step.input_summary && Object.keys(step.input_summary).length > 0;
  const hasOutput = step.output_summary && Object.keys(step.output_summary).length > 0;
  const hasError = step.error_summary && Object.keys(step.error_summary).length > 0;

  const isTool = step.step_type === "tool";
  const meta = step.metadata ?? {};

  const mcpInfo = getMcpDisplayInfo(step);
  const capKind = getCapabilityKind(step);
  const retrievalStage = getRetrievalStage(step);
  const isRetrieval = isRetrievalStep(step);

  const extras = extraMetadataEntries(step.metadata, isTool);

  const linkTarget = sourceLlmStep ?? parentStep;

  return (
    <div className="space-y-5 border-t border-neutral-100 px-5 pb-5 pt-4">
      {/* Tool linkage row */}
      {isTool && (
        <div className="flex flex-wrap items-center gap-x-[14px] gap-y-1.5 text-[11px]">
          {!!meta.provider && (
            <span className="rounded bg-amber-50 px-1.5 py-0.5 font-medium text-amber-600 dark:bg-amber-950/30 dark:text-amber-400">
              {String(meta.provider)}
            </span>
          )}
          {!!meta.model && (
            <span className="font-mono text-neutral-500">{String(meta.model)}</span>
          )}
          <span className="text-neutral-400">{stepDuration(step)}</span>
          {!!meta.tool_call_id && (
            <span className="font-mono text-neutral-400" title={String(meta.tool_call_id)}>
              {truncateId(String(meta.tool_call_id))}
            </span>
          )}
          {linkTarget && onJumpToStep && (
            <button
              onClick={() => onJumpToStep(linkTarget.id)}
              className="text-neutral-400 transition-colors hover:text-neutral-600 hover:underline"
            >
              ← {linkTarget.name} (#{linkTarget.sequence_index})
            </button>
          )}
          {isTool && backLinkConfidence && backLinkConfidence !== "unlinked" && (
            <span className={`rounded px-1.5 py-px text-[9px] font-medium ${
              backLinkConfidence === "exact"
                ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400"
                : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400"
            }`}>
              {backLinkConfidence}
            </span>
          )}
        </div>
      )}

      {/* Parent linkage row for non-tool child steps */}
      {!isTool && parentStep && (
        <div className="flex flex-wrap items-center gap-x-[14px] gap-y-1.5 text-[11px]">
          <span className="text-neutral-400">child of</span>
          <span className="font-medium text-neutral-500">{parentStep.name}</span>
          {onJumpToStep && (
            <button
              onClick={() => onJumpToStep(parentStep.id)}
              className="text-neutral-400 transition-colors hover:text-neutral-600 hover:underline"
            >
              step #{parentStep.sequence_index}
            </button>
          )}
        </div>
      )}

      {/* Generic metadata bar */}
      {!isTool && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-neutral-400">
          <span>type <span className="font-medium text-neutral-600">{step.step_type}</span></span>
          <span>duration <span className="font-medium text-neutral-600">{stepDuration(step)}</span></span>
          {step.started_at && <span>started <span className="font-medium text-neutral-600">{formatDate(step.started_at)}</span></span>}
          {step.ended_at && <span>ended <span className="font-medium text-neutral-600">{formatDate(step.ended_at)}</span></span>}
        </div>
      )}

      {/* MCP metadata rows */}
      {mcpInfo && (
        <MetadataRows
          label="MCP"
          badgeClass={MCP_BADGE}
          entries={[
            ["server", mcpInfo.serverName],
            ["operation", mcpInfo.operationKind],
            ["target", mcpInfo.targetName],
            ["transport", mcpInfo.transportKind],
            ["server_id", mcpInfo.serverId],
          ]}
        />
      )}

      {/* Capability / skill metadata rows */}
      {capKind && (
        <MetadataRows
          label={capKind}
          badgeClass={CAPABILITY_BADGE[capKind] ?? CAPABILITY_BADGE.unknown}
          entries={[
            ["name", _strMeta(meta.capability_name)],
            ["label", _strMeta(meta.capability_label)],
            ["namespace", _strMeta(meta.capability_namespace)],
            ["skill", _strMeta(meta.skill_name)],
            ["skill_label", _strMeta(meta.skill_label)],
          ]}
        />
      )}

      {/* Retrieval metadata rows */}
      {isRetrieval && (
        <MetadataRows
          label={retrievalStage ?? "retrieval"}
          badgeClass={RETRIEVAL_STAGE_BADGE}
          entries={[
            ["backend", _strMeta(meta.retrieval_backend)],
            ["index", _strMeta(meta.index_name)],
            ["query", _strMeta(meta.query_text)],
            ["queries", _numMeta(meta.query_count)],
            ["candidates", _numMeta(meta.candidate_count)],
            ["selected", _numMeta(meta.selected_count)],
            ["tokens", _numMeta(meta.context_token_estimate)],
            ["latency", _numMeta(meta.latency_ms) != null ? `${_numMeta(meta.latency_ms)}ms` : null],
          ]}
        />
      )}

      {/* Extra metadata */}
      {extras.length > 0 && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-neutral-400">
          {extras.map(([k, v]) => (
            <span key={k}>{k} <span className="font-medium text-neutral-600">{String(v)}</span></span>
          ))}
        </div>
      )}

      {/* Input */}
      <StepSection label="Input" variant="input">
        {hasInput ? (
          <StepDataBlock data={step.input_summary!} variant="input" />
        ) : (
          <p className="py-1 text-xs italic text-neutral-400">No input</p>
        )}
      </StepSection>

      {/* Output */}
      <StepSection label="Output" variant="output">
        {hasOutput ? (
          <StepDataBlock data={step.output_summary!} variant="output" />
        ) : (
          <p className="py-1 text-xs italic text-neutral-400">No output</p>
        )}
      </StepSection>

      {/* Error */}
      {hasError && (
        <StepSection label="Error" variant="error">
          <InlineError data={step.error_summary!} />
        </StepSection>
      )}

      {/* Artifacts */}
      {step.artifacts.length > 0 && (
        <ArtifactList artifacts={step.artifacts} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metadata rows component — renders labeled key/value pairs with a badge
// ---------------------------------------------------------------------------

function MetadataRows({
  label,
  badgeClass,
  entries,
}: {
  label: string;
  badgeClass: string;
  entries: [string, string | number | null | undefined][];
}) {
  const visible = entries.filter(([, v]) => v != null && v !== "");
  if (visible.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-[14px] gap-y-1.5 text-[11px]">
      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badgeClass}`}>{label}</span>
      {visible.map(([k, v]) => (
        <span key={k} className="text-neutral-400">
          {k} <span className="font-medium text-neutral-600">{String(v)}</span>
        </span>
      ))}
    </div>
  );
}

function _strMeta(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}

function _numMeta(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

// ---------------------------------------------------------------------------
// Step section wrapper with visual variants
// ---------------------------------------------------------------------------

function StepSection({
  label,
  variant,
  children,
}: {
  label: string;
  variant: "input" | "output" | "error";
  children: React.ReactNode;
}) {
  const bg = {
    input: "bg-[var(--tint-input)]",
    output: "bg-[var(--tint-output)]",
    error: "bg-[var(--tint-error)]",
  }[variant];

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2 text-[11px] font-medium text-neutral-400">{label}</div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step data block (for input/output inside detail panel)
// ---------------------------------------------------------------------------

function StepDataBlock({
  data,
}: {
  data: Record<string, unknown>;
  variant: "input" | "output";
}) {
  const [raw, setRaw] = useState(false);
  const resolved = resolveData(data);
  const rawText = rawJson(data);
  const copyText = extractLines(data)?.join("\n") ?? rawText;

  return (
    <div>
      <div className="mb-1.5 flex justify-end gap-1">
        <CopyButton text={raw ? rawText : copyText} />
        <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
      </div>
      {raw ? (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-neutral-600">
          {rawText}
        </pre>
      ) : (
        <StructuredValue value={resolved} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline error (inside step detail panel)
// ---------------------------------------------------------------------------

function InlineError({ data }: { data: Record<string, unknown> }) {
  const [raw, setRaw] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const headline = errorHeadline(data);
  const detail = errorDetail(data);
  const rawText = rawJson(data);

  return (
    <div>
      <div className="mb-1.5 flex justify-end gap-1">
        <CopyButton text={raw ? rawText : (detail ?? headline)} />
        <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
      </div>
      {raw ? (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-[var(--error-text)]">
          {rawText}
        </pre>
      ) : detail ? (
        <>
          <p className="font-mono text-[13px] font-medium leading-snug text-[var(--error-text-emphasis)]">{headline}</p>
          {detail !== headline && (
            <>
              <button
                onClick={() => setExpanded(!expanded)}
                className="mt-2 text-xs font-medium text-[var(--error-accent)] hover:text-[var(--error-text)]"
              >
                {expanded ? "Hide full traceback" : "Show full traceback"}
              </button>
              {expanded && (
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-[var(--error-text-muted)]">
                  {detail}
                </pre>
              )}
            </>
          )}
        </>
      ) : (
        <StructuredValue value={resolveData(data)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Artifact list (shown in step detail panels)
// ---------------------------------------------------------------------------

function ArtifactList({ artifacts }: { artifacts: StepArtifactRef[] }) {
  const [expanded, setExpanded] = useState(false);
  if (artifacts.length === 0) return null;

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] text-neutral-400 transition-colors hover:text-neutral-600"
      >
        <span className={`text-[9px] transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}>▶</span>
        <span className="font-medium">Artifacts</span>
        <span className="tabular-nums">{artifacts.length}</span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {artifacts.map((a) => (
            <ArtifactViewer key={a.id} artifact={a} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Events section — collapsible, grouped by step
// ---------------------------------------------------------------------------

type EventGroup = {
  stepId: string | null;
  stepName: string | null;
  events: TimelineEvent[];
};

function groupEventsByStep(
  events: TimelineEvent[],
  stepById: Map<string, TimelineStep>,
): EventGroup[] {
  const groups: EventGroup[] = [];
  let current: EventGroup | null = null;

  for (const ev of events) {
    if (!current || current.stepId !== ev.step_id) {
      const step = ev.step_id ? stepById.get(ev.step_id) : undefined;
      current = {
        stepId: ev.step_id,
        stepName: step?.name ?? null,
        events: [],
      };
      groups.push(current);
    }
    current.events.push(ev);
  }
  return groups;
}

function EventsSection({
  events,
  expanded,
  onToggle,
  runStartedAt,
  stepById,
}: {
  events: TimelineEvent[];
  expanded: boolean;
  onToggle: () => void;
  runStartedAt: string | null;
  stepById: Map<string, TimelineStep>;
}) {
  const groups = useMemo(() => groupEventsByStep(events, stepById), [events, stepById]);
  const baseTime = useMemo(() => {
    if (runStartedAt) return new Date(runStartedAt).getTime();
    if (events.length > 0) return new Date(events[0].timestamp).getTime();
    return 0;
  }, [runStartedAt, events]);

  return (
    <section className="mb-12">
      <button
        onClick={onToggle}
        className="mb-4 flex w-full items-center gap-2 text-left"
      >
        <span className={`text-[10px] transition-transform duration-150 ${expanded ? "rotate-90" : ""} text-neutral-400`}>▶</span>
        <h2 className="text-lg font-semibold tracking-tight text-neutral-900">Events</h2>
        <span className="text-[11px] tabular-nums text-neutral-400">{events.length}</span>
      </button>

      {expanded && (
        <div className="rounded-lg border border-neutral-200 bg-white">
          <div className="divide-y divide-neutral-100">
            {groups.map((group, gi) => (
              <div key={gi}>
                {group.stepId && group.stepName && (
                  <div className="px-4 pt-2.5 pb-0.5">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-neutral-400">
                      {group.stepName}
                    </span>
                  </div>
                )}
                <div className="py-1">
                  {group.events.map((ev) => (
                    <EventRow key={ev.id} event={ev} baseTime={baseTime} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

const EVENT_BADGE_STYLES: Record<string, string> = {
  "run.created": "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400",
  "run.started": "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400",
  "run.completed": "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400",
  "run.failed": "bg-red-50 text-red-500 dark:bg-red-950/30 dark:text-red-400",
  "step.created": "bg-neutral-100 text-neutral-500",
  "step.started": "bg-neutral-100 text-neutral-500",
  "step.completed": "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400",
  "step.failed": "bg-red-50 text-red-500 dark:bg-red-950/30 dark:text-red-400",
};

function EventRow({ event, baseTime }: { event: TimelineEvent; baseTime: number }) {
  const offsetMs = baseTime ? new Date(event.timestamp).getTime() - baseTime : null;
  const badgeStyle = EVENT_BADGE_STYLES[event.event_type] ?? "bg-neutral-100 text-neutral-400";
  const hasPayload = Object.keys(event.payload).length > 0;

  return (
    <div className="flex items-baseline gap-2.5 px-4 py-[3px] font-mono text-[11px] hover:bg-neutral-100">
      <span className="w-5 shrink-0 text-right tabular-nums text-neutral-400">
        {event.sequence_index}
      </span>
      <span className={`shrink-0 rounded px-1.5 py-px text-[9px] font-medium ${badgeStyle}`}>
        {event.event_type}
      </span>
      {offsetMs != null && (
        <span className="shrink-0 tabular-nums text-neutral-400">
          +{offsetMs}ms
        </span>
      )}
      {hasPayload && (
        <span className="min-w-0 truncate text-neutral-400" title={JSON.stringify(event.payload)}>
          {JSON.stringify(event.payload)}
        </span>
      )}
    </div>
  );
}
