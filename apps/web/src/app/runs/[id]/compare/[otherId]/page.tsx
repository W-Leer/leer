"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { errorHeadline, formatDate, rawJson, resolveData, statusClass } from "@/lib/format";
import { StructuredValue } from "@/components/structured-value";
import type { CompareResponse, CompareRunDiff, CompareRunSummary, CompareStepDiff } from "@/lib/types";

type Dict = Record<string, unknown>;

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
    <div className="max-w-5xl">
      <Link href={`/runs/${id}`} className="mb-6 inline-block text-sm text-neutral-500 hover:text-neutral-800">
        ← Back to run
      </Link>

      <h1 className="mb-8 text-2xl font-semibold tracking-tight">Compare Runs</h1>

      <div className="mb-6 grid grid-cols-2 gap-4">
        <RunSummaryCard label="Run A" run={data.run_a} />
        <RunSummaryCard label="Run B" run={data.run_b} />
      </div>

      <RunDiffSection diff={data.run_diff} />

      <section>
        <h2 className="mb-6 text-lg font-semibold tracking-tight">Steps</h2>
        {data.steps.length === 0 ? (
          <p className="text-sm text-neutral-500">No steps to compare.</p>
        ) : (
          <div className="space-y-5">
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
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-neutral-400">{label}</div>
      <div className="flex items-center gap-2">
        <span className="font-semibold">{run.workflow_name}</span>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(run.status)}`}>
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
    <section className={`mb-8 rounded-lg border p-5 ${hasDiff ? "border-amber-200" : "border-neutral-200"}`}>
      <h2 className="mb-5 text-lg font-semibold tracking-tight">Run Result</h2>

      <div className="space-y-5">
        <DiffRow label="Status" diff={diff.status_diff}>
          <DiffCellText side="A" value={diff.status_a} />
          <DiffCellText side="B" value={diff.status_b} />
        </DiffRow>

        <DataDiffRow label="Output" diff={diff.output_diff} dataA={diff.output_summary_a} dataB={diff.output_summary_b} />

        {(diff.error_summary_a || diff.error_summary_b) && (
          <DiffRow label="Error" diff={diff.error_diff} isError>
            <DiffCellText side="A" value={errorHeadline(diff.error_summary_a) || null} isError />
            <DiffCellText side="B" value={errorHeadline(diff.error_summary_b) || null} isError />
          </DiffRow>
        )}
      </div>
    </section>
  );
}

function StepDiffCard({ step }: { step: CompareStepDiff }) {
  const hasDiff = step.status_diff || step.output_diff || step.error_diff;
  const missing = !step.exists_in_a || !step.exists_in_b;

  const borderColor = missing
    ? "border-amber-300"
    : hasDiff
      ? "border-amber-200"
      : "border-neutral-200";

  const stepName = step.name_a ?? step.name_b ?? "—";
  const stepType = step.step_type_a ?? step.step_type_b ?? "—";

  return (
    <div className={`rounded-lg border p-5 ${borderColor}`}>
      <div className="mb-5 flex items-center gap-2">
        <span className="font-mono text-xs text-neutral-400">#{step.sequence_index}</span>
        <span className="text-[13px] font-semibold tracking-tight text-neutral-900">{stepName}</span>
        <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400">
          {stepType}
        </span>
        {missing && (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[10px] font-medium text-amber-700">
            {!step.exists_in_a ? "missing in A" : "missing in B"}
          </span>
        )}
      </div>

      <div className="space-y-5">
        <DiffRow label="Status" diff={step.status_diff}>
          <DiffCellText side="A" value={step.status_a} />
          <DiffCellText side="B" value={step.status_b} />
        </DiffRow>

        <DataDiffRow label="Output" diff={step.output_diff} dataA={step.output_summary_a} dataB={step.output_summary_b} />

        {(step.error_summary_a || step.error_summary_b) && (
          <DiffRow label="Error" diff={step.error_diff} isError>
            <DiffCellText side="A" value={errorHeadline(step.error_summary_a) || null} isError />
            <DiffCellText side="B" value={errorHeadline(step.error_summary_b) || null} isError />
          </DiffRow>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared diff components
// ---------------------------------------------------------------------------

function DiffRow({
  label,
  diff,
  isError,
  children,
}: {
  label: string;
  diff: boolean;
  isError?: boolean;
  children: [React.ReactNode, React.ReactNode];
}) {
  const bg = diff
    ? isError ? "bg-red-50/60" : "bg-amber-50/60"
    : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[11px] font-medium text-neutral-400">
        {label}
        {diff && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
            changed
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-0">
        <div className="pr-4">{children[0]}</div>
        <div className="border-l border-neutral-200 pl-4">{children[1]}</div>
      </div>
    </div>
  );
}

function DiffCellText({
  side,
  value,
  isError,
}: {
  side: string;
  value: string | null;
  isError?: boolean;
}) {
  const textColor = isError ? "text-red-700" : "text-neutral-700";

  return (
    <div>
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-neutral-400">{side}</div>
      {value ? (
        <p className={`whitespace-pre-wrap break-words font-mono text-xs leading-6 ${textColor}`}>
          {value}
        </p>
      ) : (
        <p className="text-xs italic text-neutral-400">No output</p>
      )}
    </div>
  );
}

function DataDiffRow({
  label,
  diff,
  dataA,
  dataB,
}: {
  label: string;
  diff: boolean;
  dataA: Dict | null;
  dataB: Dict | null;
}) {
  const [raw, setRaw] = useState(false);
  const hasAny = dataA != null || dataB != null;
  const bg = diff ? "bg-amber-50/60" : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[11px] font-medium text-neutral-400">
        <span className="flex items-center gap-2">
          {label}
          {diff && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
              changed
            </span>
          )}
        </span>
        {hasAny && (
          <button
            onClick={() => setRaw(!raw)}
            className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600"
          >
            {raw ? "Formatted" : "Raw"}
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-0">
        <div className="pr-4">
          <DataCell side="A" data={dataA} raw={raw} />
        </div>
        <div className="border-l border-neutral-200 pl-4">
          <DataCell side="B" data={dataB} raw={raw} />
        </div>
      </div>
    </div>
  );
}

function DataCell({ side, data, raw }: { side: string; data: Dict | null; raw: boolean }) {
  const resolved = resolveData(data);
  const rawText = rawJson(data);

  return (
    <div>
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-neutral-400">{side}</div>
      {resolved == null ? (
        <p className="text-xs italic text-neutral-400">No output</p>
      ) : raw ? (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-neutral-600">
          {rawText}
        </pre>
      ) : (
        <StructuredValue value={resolved} />
      )}
    </div>
  );
}
