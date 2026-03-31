"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
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
import type { TimelineResponse, TimelineStep, TimelineEvent } from "@/lib/types";
import { StructuredValue } from "@/components/structured-value";
import { LlmStepDetail } from "@/components/llm-step-detail";
import type { ToolCallLinkInfo } from "@/components/llm-step-detail";
import { ChevronRight, GitCompareArrows } from "lucide-react";

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedStepId, setExpandedStepId] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    apiFetch<TimelineResponse>(`/v1/runs/${id}/timeline`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-neutral-500">Loading…</p>;

  if (error) {
    return (
      <div className="rounded-lg bg-[var(--tint-error-block)] p-4 text-sm text-[var(--error-text)]">
        Failed to load run: {error}
      </div>
    );
  }

  if (!data) return null;

  const { run, steps, events } = data;

  // Build tool_call_id linkage maps from the timeline data
  const { toolCallIdToToolStep, toolCallIdToLlmStep } = useMemo(() => {
    const toTool = new Map<string, TimelineStep>();
    const toLlm = new Map<string, TimelineStep>();

    for (const s of steps) {
      if (s.step_type === "tool" && s.metadata?.tool_call_id) {
        toTool.set(String(s.metadata.tool_call_id), s);
      }
      if (s.llm?.output?.tool_calls) {
        for (const tc of s.llm.output.tool_calls) {
          const tcId = (tc as Record<string, unknown>).id;
          if (typeof tcId === "string") {
            toLlm.set(tcId, s);
          }
        }
      }
    }
    return { toolCallIdToToolStep: toTool, toolCallIdToLlmStep: toLlm };
  }, [steps]);

  const scrollToStep = useCallback((stepId: string) => {
    const el = document.getElementById(`step-${stepId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setExpandedStepId(stepId);
    }
  }, []);

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
                toolCallIdToToolStep={toolCallIdToToolStep}
                toolCallIdToLlmStep={toolCallIdToLlmStep}
                onJumpToStep={scrollToStep}
              />
            ))}
          </div>
        )}
      </section>

      {/* Events list */}
      <section className="mb-12">
        <h2 className="mb-6 text-lg font-semibold tracking-tight text-neutral-900">Events</h2>
        {events.length === 0 ? (
          <p className="text-sm text-neutral-500">No events recorded.</p>
        ) : (
          <div className="space-y-1">
            {events.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </div>
        )}
      </section>
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
        ) : (
          <>
            <p className="font-mono text-[13px] font-medium leading-snug text-[var(--error-text-emphasis)]">
              {headline}
            </p>
            {detail && detail !== headline && (
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
  toolCallIdToToolStep,
  toolCallIdToLlmStep,
  onJumpToStep,
}: {
  step: TimelineStep;
  expanded: boolean;
  onToggle: () => void;
  toolCallIdToToolStep: Map<string, TimelineStep>;
  toolCallIdToLlmStep: Map<string, TimelineStep>;
  onJumpToStep: (stepId: string) => void;
}) {
  const isTool = step.step_type === "tool";
  const toolCallId = isTool ? String(step.metadata?.tool_call_id ?? "") : "";
  const sourceLlmStep = toolCallId ? toolCallIdToLlmStep.get(toolCallId) : undefined;
  const isLinkedTool = isTool && !!sourceLlmStep;

  // Build tool call link map for LLM steps
  const llmToolCallLinks = useMemo(() => {
    if (!step.llm?.output?.tool_calls?.length) return undefined;
    const links = new Map<string, ToolCallLinkInfo>();
    for (const tc of step.llm.output.tool_calls) {
      const tcId = (tc as Record<string, unknown>).id;
      if (typeof tcId === "string") {
        const toolStep = toolCallIdToToolStep.get(tcId);
        if (toolStep) {
          links.set(tcId, {
            toolStepId: toolStep.id,
            toolStepName: toolStep.name,
            toolStepIndex: toolStep.sequence_index,
            toolStepStatus: toolStep.status,
          });
        }
      }
    }
    return links.size > 0 ? links : undefined;
  }, [step.llm, toolCallIdToToolStep]);

  const dotColor = expanded
    ? "border-neutral-500 bg-neutral-500"
    : step.status === "failed"
      ? "border-[var(--error-dot)] bg-[var(--error-dot)]"
      : "border-neutral-300 bg-white";

  const sourceLabel = sourceLlmStep
    ? `Triggered by ${String(step.metadata?.model || step.metadata?.provider || "")} tool call`
        .replace(/\s+tool call$/, " tool call")
        .replace(/^Triggered by\s+tool call$/, "Triggered by previous LLM step")
    : null;

  return (
    <div id={`step-${step.id}`} className={`relative mb-7 last:mb-0 ${isLinkedTool ? "ml-5" : ""}`}>
      {/* Timeline dot */}
      <div className={`absolute -left-[34px] top-[17px] h-2.5 w-2.5 rounded-full border-2 transition-colors duration-150 ${dotColor}`} />

      {/* Linked tool accent */}
      {isLinkedTool && (
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
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className={`text-[10px] transition-transform duration-150 ${expanded ? "rotate-90" : ""} text-neutral-400`}>▶</span>
              <span className="text-[13px] font-semibold tracking-tight text-neutral-900">{step.name}</span>
              <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${stepTypeBadge(step.step_type)}`}>
                {step.step_type}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(step.status)}`}>
                {step.status}
              </span>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-neutral-400">
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
          {/* Context line for linked tool steps */}
          {sourceLabel && (
            <div className="mt-1.5 pl-[22px] text-[11px] text-neutral-400">
              <span className="mr-1 text-amber-400">↳</span>
              {sourceLabel}
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
                toolCallLinks={llmToolCallLinks}
                onJumpToStep={onJumpToStep}
              />
            ) : (
              <StepDetailPanel
                step={step}
                sourceLlmStep={sourceLlmStep}
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

const TOOL_META_KEYS = new Set(["tool_name", "tool_call_id", "provider", "model"]);

function StepDetailPanel({
  step,
  sourceLlmStep,
  onJumpToStep,
}: {
  step: TimelineStep;
  sourceLlmStep?: TimelineStep;
  onJumpToStep?: (stepId: string) => void;
}) {
  const hasInput = step.input_summary && Object.keys(step.input_summary).length > 0;
  const hasOutput = step.output_summary && Object.keys(step.output_summary).length > 0;
  const hasError = step.error_summary && Object.keys(step.error_summary).length > 0;

  const isTool = step.step_type === "tool";
  const meta = step.metadata ?? {};
  const extraEntries = Object.entries(meta).filter(([k]) => !isTool || !TOOL_META_KEYS.has(k));

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
          {sourceLlmStep && onJumpToStep && (
            <button
              onClick={() => onJumpToStep(sourceLlmStep.id)}
              className="text-neutral-400 transition-colors hover:text-neutral-600 hover:underline"
            >
              from step #{sourceLlmStep.sequence_index}
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

      {/* Extra metadata */}
      {extraEntries.length > 0 && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-neutral-400">
          {extraEntries.map(([k, v]) => (
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
    </div>
  );
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
      ) : (
        <>
          <p className="font-mono text-[13px] font-medium leading-snug text-[var(--error-text-emphasis)]">{headline}</p>
          {detail && detail !== headline && (
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
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event row
// ---------------------------------------------------------------------------

function EventRow({ event }: { event: TimelineEvent }) {
  return (
    <div className="flex items-center gap-3 rounded px-3 py-2 text-sm hover:bg-neutral-50">
      <span className="font-mono text-[11px] text-neutral-400">#{event.sequence_index}</span>
      <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[11px] text-neutral-500">
        {event.event_type}
      </span>
      <span className="text-[11px] text-neutral-400">{formatDate(event.timestamp)}</span>
      {Object.keys(event.payload).length > 0 && (
        <span className="truncate font-mono text-[11px] text-neutral-400">
          {JSON.stringify(event.payload)}
        </span>
      )}
    </div>
  );
}
