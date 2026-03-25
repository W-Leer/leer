"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
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

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [compareId, setCompareId] = useState("");
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
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Failed to load run: {error}
      </div>
    );
  }

  if (!data) return null;

  const { run, steps, events } = data;

  return (
    <div className="max-w-4xl">
      <Link href="/" className="mb-6 inline-block text-sm text-neutral-500 hover:text-neutral-800">
        ← Back to runs
      </Link>

      {/* Run header */}
      <div className="mb-10 rounded-lg border border-neutral-150 bg-white p-6">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-900">{run.workflow_name}</h1>
          <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${statusClass(run.status)}`}>
            {run.status}
          </span>
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

      {/* Compare action */}
      <div className="mb-10 flex items-center gap-2">
        <input
          type="text"
          placeholder="Other run ID…"
          value={compareId}
          onChange={(e) => setCompareId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const trimmed = compareId.trim();
              if (trimmed) router.push(`/runs/${id}/compare/${trimmed}`);
            }
          }}
          className="w-72 rounded border border-neutral-200 px-3 py-1.5 font-mono text-sm placeholder:text-neutral-400 focus:border-neutral-400 focus:outline-none"
        />
        <button
          onClick={() => {
            const trimmed = compareId.trim();
            if (trimmed) router.push(`/runs/${id}/compare/${trimmed}`);
          }}
          disabled={!compareId.trim()}
          className="rounded bg-neutral-800 px-4 py-1.5 text-sm font-medium text-white transition-opacity disabled:opacity-40"
        >
          Compare
        </button>
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
      <div className="rounded-md border border-neutral-100 bg-neutral-50 px-4 py-3">
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
        <span className="text-xs font-medium text-red-500">Error</span>
        <div className="flex items-center gap-1">
          <CopyButton text={raw ? rawText : (detail ?? headline)} />
          <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
        </div>
      </div>
      <div className="rounded-md border border-red-100 bg-red-50/60 px-4 py-3">
        {raw ? (
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-red-700">
            {rawText}
          </pre>
        ) : (
          <>
            <p className="font-mono text-[13px] font-medium leading-snug text-red-800">
              {headline}
            </p>
            {detail && detail !== headline && (
              <>
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="mt-2.5 text-xs font-medium text-red-500 hover:text-red-700"
                >
                  {expanded ? "Hide full traceback" : "Show full traceback"}
                </button>
                {expanded && (
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-red-600/80">
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

function stepDuration(step: TimelineStep): string {
  if (!step.started_at || !step.ended_at) return "—";
  const ms = new Date(step.ended_at).getTime() - new Date(step.started_at).getTime();
  return formatDuration(ms);
}

function StepCard({
  step,
  expanded,
  onToggle,
}: {
  step: TimelineStep;
  expanded: boolean;
  onToggle: () => void;
}) {
  const dotColor = expanded
    ? "border-neutral-500 bg-neutral-500"
    : step.status === "failed"
      ? "border-red-400 bg-red-400"
      : "border-neutral-300 bg-white";

  return (
    <div className="relative mb-7 last:mb-0">
      {/* Timeline dot — centered on the border-l-2 line */}
      <div className={`absolute -left-[34px] top-[17px] h-2.5 w-2.5 rounded-full border-2 transition-colors duration-150 ${dotColor}`} />

      <div
        className={`rounded-lg border transition-all duration-150 ${
          expanded
            ? "border-neutral-300 bg-white shadow-sm"
            : "border-neutral-150 bg-white hover:border-neutral-300 hover:shadow-sm"
        }`}
      >
        {/* Clickable header */}
        <button onClick={onToggle} className="w-full cursor-pointer px-5 py-3.5 text-left">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className={`text-[10px] transition-transform duration-150 ${expanded ? "rotate-90" : ""} text-neutral-400`}>▶</span>
              <span className="text-[13px] font-semibold tracking-tight text-neutral-900">{step.name}</span>
              <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400">
                {step.step_type}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(step.status)}`}>
                {step.status}
              </span>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-neutral-400">
              <span>{stepDuration(step)}</span>
              <span className="font-mono">#{step.sequence_index}</span>
            </div>
          </div>
        </button>

        {/* Expand/collapse with CSS grid — handles dynamic content height */}
        <div
          className={`grid transition-[grid-template-rows] duration-200 ease-in-out ${
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          }`}
        >
          <div className="overflow-hidden">
            <StepDetailPanel step={step} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step detail panel
// ---------------------------------------------------------------------------

function StepDetailPanel({ step }: { step: TimelineStep }) {
  const hasInput = step.input_summary && Object.keys(step.input_summary).length > 0;
  const hasOutput = step.output_summary && Object.keys(step.output_summary).length > 0;
  const hasError = step.error_summary && Object.keys(step.error_summary).length > 0;
  const metaEntries = step.metadata ? Object.entries(step.metadata) : [];

  return (
    <div className="space-y-5 border-t border-neutral-100 px-5 pb-5 pt-4">
      {/* Metadata bar */}
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-neutral-400">
        <span>type <span className="font-medium text-neutral-600">{step.step_type}</span></span>
        <span>duration <span className="font-medium text-neutral-600">{stepDuration(step)}</span></span>
        {step.started_at && <span>started <span className="font-medium text-neutral-600">{formatDate(step.started_at)}</span></span>}
        {step.ended_at && <span>ended <span className="font-medium text-neutral-600">{formatDate(step.ended_at)}</span></span>}
        {metaEntries.map(([k, v]) => (
          <span key={k}>{k} <span className="font-medium text-neutral-600">{String(v)}</span></span>
        ))}
      </div>

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
    input: "bg-blue-50/40 border-blue-100",
    output: "bg-neutral-50 border-neutral-150",
    error: "bg-red-50/40 border-red-100",
  }[variant];

  return (
    <div className={`rounded-md border px-4 py-3 ${bg}`}>
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
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-red-700">
          {rawText}
        </pre>
      ) : (
        <>
          <p className="font-mono text-[13px] font-medium leading-snug text-red-800">{headline}</p>
          {detail && detail !== headline && (
            <>
              <button
                onClick={() => setExpanded(!expanded)}
                className="mt-2 text-xs font-medium text-red-500 hover:text-red-700"
              >
                {expanded ? "Hide full traceback" : "Show full traceback"}
              </button>
              {expanded && (
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-red-600/80">
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
