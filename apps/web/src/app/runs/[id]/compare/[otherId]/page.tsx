"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { formatDate, statusClass } from "@/lib/format";
import type { CompareResponse, CompareRunDiff, CompareRunSummary, CompareStepDiff } from "@/lib/types";

export default function ComparePage() {
  const { id, otherId } = useParams<{ id: string; otherId: string }>();
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id || !otherId) return;
    apiFetch<CompareResponse>(`/v1/runs/${id}/compare/${otherId}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id, otherId]);

  if (loading) return <p className="text-neutral-500">Loading comparison…</p>;

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Failed to load comparison: {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div>
      <Link href={`/runs/${id}`} className="mb-4 inline-block text-sm text-neutral-500 hover:text-neutral-800">
        ← Back to run
      </Link>

      <h1 className="mb-6 text-2xl font-semibold">Compare Runs</h1>

      {/* Run summaries */}
      <div className="mb-8 grid grid-cols-2 gap-4">
        <RunSummaryCard label="Run A" run={data.run_a} />
        <RunSummaryCard label="Run B" run={data.run_b} />
      </div>

      {/* Run-level diff */}
      <RunDiffSection diff={data.run_diff} />

      {/* Step diffs */}
      <section>
        <h2 className="mb-4 text-lg font-semibold">Steps</h2>
        {data.steps.length === 0 ? (
          <p className="text-sm text-neutral-500">No steps to compare.</p>
        ) : (
          <div className="space-y-4">
            {data.steps.map((step) => (
              <StepDiffCard key={step.sequence_index} step={step} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RunSummaryCard({ label, run }: { label: string; run: CompareRunSummary }) {
  return (
    <div className="rounded-lg border border-neutral-200 p-4">
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-neutral-400">{label}</div>
      <div className="flex items-center gap-2">
        <span className="font-medium">{run.workflow_name}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(run.status)}`}>
          {run.status}
        </span>
      </div>
      <div className="mt-1 text-sm text-neutral-500">{formatDate(run.created_at)}</div>
      <div className="mt-0.5 font-mono text-xs text-neutral-400">{run.id.slice(0, 8)}</div>
    </div>
  );
}

function RunDiffSection({ diff }: { diff: CompareRunDiff }) {
  const hasDiff = diff.status_diff || diff.output_diff || diff.error_diff;

  return (
    <section className={`mb-8 rounded-lg border p-4 ${hasDiff ? "border-red-300" : "border-neutral-200"}`}>
      <h2 className="mb-3 text-lg font-semibold">Run Result</h2>

      <DiffRow label="Status" a={diff.status_a} b={diff.status_b} diff={diff.status_diff} />

      <DiffRow
        label="Output"
        a={diff.output_summary_a ? JSON.stringify(diff.output_summary_a) : null}
        b={diff.output_summary_b ? JSON.stringify(diff.output_summary_b) : null}
        diff={diff.output_diff}
        mono
      />

      {(diff.error_summary_a || diff.error_summary_b) && (
        <DiffRow
          label="Error"
          a={diff.error_summary_a ? JSON.stringify(diff.error_summary_a) : null}
          b={diff.error_summary_b ? JSON.stringify(diff.error_summary_b) : null}
          diff={diff.error_diff}
          mono
          isError
        />
      )}
    </section>
  );
}

function StepDiffCard({ step }: { step: CompareStepDiff }) {
  const hasDiff = step.status_diff || step.output_diff || step.error_diff;
  const missing = !step.exists_in_a || !step.exists_in_b;

  const borderColor = missing
    ? "border-amber-300"
    : hasDiff
      ? "border-red-300"
      : "border-neutral-200";

  const stepName = step.name_a ?? step.name_b ?? "—";
  const stepType = step.step_type_a ?? step.step_type_b ?? "—";

  return (
    <div className={`rounded-lg border p-4 ${borderColor}`}>
      {/* Step header */}
      <div className="mb-3 flex items-center gap-2">
        <span className="font-mono text-xs text-neutral-400">#{step.sequence_index}</span>
        <span className="font-medium">{stepName}</span>
        <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-500">
          {stepType}
        </span>
        {missing && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
            {!step.exists_in_a ? "missing in A" : "missing in B"}
          </span>
        )}
      </div>

      {/* Status */}
      <DiffRow label="Status" a={step.status_a} b={step.status_b} diff={step.status_diff} />

      {/* Output summary */}
      <DiffRow
        label="Output"
        a={step.output_summary_a ? JSON.stringify(step.output_summary_a) : null}
        b={step.output_summary_b ? JSON.stringify(step.output_summary_b) : null}
        diff={step.output_diff}
        mono
      />

      {/* Error summary — only if either side has one */}
      {(step.error_summary_a || step.error_summary_b) && (
        <DiffRow
          label="Error"
          a={step.error_summary_a ? JSON.stringify(step.error_summary_a) : null}
          b={step.error_summary_b ? JSON.stringify(step.error_summary_b) : null}
          diff={step.error_diff}
          mono
          isError
        />
      )}
    </div>
  );
}

function DiffRow({
  label,
  a,
  b,
  diff,
  mono,
  isError,
}: {
  label: string;
  a: string | null;
  b: string | null;
  diff: boolean;
  mono?: boolean;
  isError?: boolean;
}) {
  const bgDiff = isError ? "bg-red-50" : "bg-amber-50";
  const textClass = mono ? "font-mono text-xs" : "text-sm";

  return (
    <div className={`rounded px-3 py-1.5 ${diff ? bgDiff : ""}`}>
      <div className="mb-0.5 text-xs font-medium text-neutral-500">
        {label}
        {diff && <span className="ml-1 text-amber-600">changed</span>}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <span className="text-[10px] uppercase text-neutral-400">A </span>
          <span className={`${textClass} ${isError ? "text-red-700" : "text-neutral-700"}`}>
            {a ?? "—"}
          </span>
        </div>
        <div>
          <span className="text-[10px] uppercase text-neutral-400">B </span>
          <span className={`${textClass} ${isError ? "text-red-700" : "text-neutral-700"}`}>
            {b ?? "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
