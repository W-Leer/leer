"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { formatDate, formatDuration, statusClass } from "@/lib/format";
import type { TimelineResponse, TimelineStep, TimelineEvent } from "@/lib/types";

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [compareId, setCompareId] = useState("");

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
    <div>
      <Link href="/" className="mb-4 inline-block text-sm text-neutral-500 hover:text-neutral-800">
        ← Back to runs
      </Link>

      {/* Run header */}
      <div className="mb-8 rounded-lg border border-neutral-200 p-5">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{run.workflow_name}</h1>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(run.status)}`}>
            {run.status}
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-3">
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
          <div className="mt-3">
            <span className="text-xs font-medium text-neutral-500">Output</span>
            <pre className="mt-1 rounded bg-neutral-100 p-2 font-mono text-xs text-neutral-700">
              {JSON.stringify(run.output_summary, null, 2)}
            </pre>
          </div>
        )}

        {run.error_summary && (
          <div className="mt-3">
            <span className="text-xs font-medium text-red-600">Error</span>
            <pre className="mt-1 rounded bg-red-50 p-2 font-mono text-xs text-red-700">
              {JSON.stringify(run.error_summary, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* Compare action */}
      <div className="mb-8 flex items-center gap-2">
        <input
          type="text"
          placeholder="Other run ID…"
          value={compareId}
          onChange={(e) => setCompareId(e.target.value)}
          className="rounded border border-neutral-300 px-3 py-1.5 font-mono text-sm placeholder:text-neutral-400 focus:border-neutral-500 focus:outline-none"
        />
        <button
          onClick={() => {
            const trimmed = compareId.trim();
            if (trimmed) router.push(`/runs/${id}/compare/${trimmed}`);
          }}
          disabled={!compareId.trim()}
          className="rounded bg-neutral-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
        >
          Compare
        </button>
      </div>

      {/* Steps timeline */}
      <section className="mb-8">
        <h2 className="mb-4 text-lg font-semibold">Steps</h2>
        {steps.length === 0 ? (
          <p className="text-sm text-neutral-500">No steps recorded.</p>
        ) : (
          <div className="relative border-l-2 border-neutral-200 pl-6">
            {steps.map((step) => (
              <StepCard key={step.id} step={step} />
            ))}
          </div>
        )}
      </section>

      {/* Events list */}
      <section>
        <h2 className="mb-4 text-lg font-semibold">Events</h2>
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
      <span className="text-neutral-500">{label}: </span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function StepCard({ step }: { step: TimelineStep }) {
  return (
    <div className="relative mb-4 pb-4 last:mb-0 last:pb-0">
      {/* Timeline dot */}
      <div className="absolute -left-[31px] top-1 h-3 w-3 rounded-full border-2 border-neutral-300 bg-white" />

      <div className="rounded-lg border border-neutral-200 p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-medium">{step.name}</span>
            <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-500">
              {step.step_type}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(step.status)}`}>
              {step.status}
            </span>
          </div>
          <span className="font-mono text-xs text-neutral-400">#{step.sequence_index}</span>
        </div>

        <div className="mt-1 flex gap-4 text-xs text-neutral-500">
          {step.started_at && <span>Started {formatDate(step.started_at)}</span>}
          {step.ended_at && <span>Ended {formatDate(step.ended_at)}</span>}
        </div>

        {step.output_summary && (
          <pre className="mt-2 truncate rounded bg-neutral-100 px-2 py-1 font-mono text-xs text-neutral-600">
            {JSON.stringify(step.output_summary)}
          </pre>
        )}

        {step.error_summary && (
          <pre className="mt-2 truncate rounded bg-red-50 px-2 py-1 font-mono text-xs text-red-700">
            {JSON.stringify(step.error_summary)}
          </pre>
        )}
      </div>
    </div>
  );
}

function EventRow({ event }: { event: TimelineEvent }) {
  return (
    <div className="flex items-center gap-3 rounded px-2 py-1.5 text-sm hover:bg-neutral-50">
      <span className="font-mono text-xs text-neutral-400">#{event.sequence_index}</span>
      <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs">
        {event.event_type}
      </span>
      <span className="text-xs text-neutral-500">{formatDate(event.timestamp)}</span>
      {Object.keys(event.payload).length > 0 && (
        <span className="truncate font-mono text-xs text-neutral-400">
          {JSON.stringify(event.payload)}
        </span>
      )}
    </div>
  );
}
