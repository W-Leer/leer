"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { errorHeadline, formatDate, rawJson, resolveData, statusClass, timeAgo } from "@/lib/format";
import { StructuredValue } from "@/components/structured-value";
import { RunSelector, type SelectedRun } from "@/components/run-selector";
import { GitCompareArrows, Lightbulb } from "lucide-react";
import type {
  CompareResponse,
  CompareRunDiff,
  CompareRunSummary,
  CompareStepDiff,
  ProjectRunsResponse,
  RunListItem,
  TimelineRun,
} from "@/lib/types";

type Dict = Record<string, unknown>;

function toSelected(run: TimelineRun | CompareRunSummary): SelectedRun {
  return {
    id: run.id,
    workflow_name: run.workflow_name,
    status: run.status,
    created_at: run.created_at,
  };
}

// Wrap the page in Suspense for useSearchParams
export default function ComparePageWrapper() {
  return (
    <Suspense fallback={<p className="text-neutral-500">Loading…</p>}>
      <ComparePage />
    </Suspense>
  );
}

function ComparePage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const paramA = searchParams.get("a");
  const paramB = searchParams.get("b");

  const [runA, setRunA] = useState<SelectedRun | null>(null);
  const [runB, setRunB] = useState<SelectedRun | null>(null);
  const [compareData, setCompareData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quickPicks, setQuickPicks] = useState<RunListItem[]>([]);

  const didAutoLoad = useRef(false);

  // Resolve URL params to SelectedRun objects
  useEffect(() => {
    if (paramA && (!runA || runA.id !== paramA)) {
      apiFetch<{ run: TimelineRun }>(`/v1/runs/${paramA}/timeline`)
        .then((d) => setRunA(toSelected(d.run)))
        .catch(() => {});
    }
    if (paramB && (!runB || runB.id !== paramB)) {
      apiFetch<{ run: TimelineRun }>(`/v1/runs/${paramB}/timeline`)
        .then((d) => setRunB(toSelected(d.run)))
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramA, paramB]);

  // Auto-fetch comparison when both URL params are present
  useEffect(() => {
    if (paramA && paramB && !didAutoLoad.current) {
      didAutoLoad.current = true;
      fetchComparison(paramA, paramB);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramA, paramB]);

  // Load quick picks on mount
  useEffect(() => {
    apiFetch<ProjectRunsResponse>("/v1/projects/demo-project/runs?limit=6&sort=newest")
      .then((d) => setQuickPicks(d.runs))
      .catch(() => {});
  }, []);

  const fetchComparison = useCallback(async (a: string, b: string) => {
    setLoading(true);
    setError(null);
    setCompareData(null);
    try {
      const data = await apiFetch<CompareResponse>(`/v1/runs/${a}/compare/${b}`);
      setCompareData(data);
      setRunA(toSelected(data.run_a));
      setRunB(toSelected(data.run_b));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to compare runs");
    } finally {
      setLoading(false);
    }
  }, []);

  function handleCompare() {
    if (!runA || !runB) return;
    router.replace(`/compare?a=${runA.id}&b=${runB.id}`, { scroll: false });
    fetchComparison(runA.id, runB.id);
  }

  function replaceUrl(a: SelectedRun | null, b: SelectedRun | null) {
    const params = new URLSearchParams();
    if (a) params.set("a", a.id);
    if (b) params.set("b", b.id);
    const qs = params.toString();
    router.replace(qs ? `/compare?${qs}` : "/compare", { scroll: false });
  }

  function handleChangeA(run: SelectedRun | null) {
    setRunA(run);
    setCompareData(null);
    setError(null);
    replaceUrl(run, runB);
  }

  function handleChangeB(run: SelectedRun | null) {
    setRunB(run);
    setCompareData(null);
    setError(null);
    replaceUrl(runA, run);
  }

  function handleQuickPick(run: RunListItem) {
    const sel: SelectedRun = {
      id: run.id,
      workflow_name: run.workflow_name,
      status: run.status,
      created_at: run.created_at,
    };
    if (!runA) {
      setRunA(sel);
      setCompareData(null);
      setError(null);
      replaceUrl(sel, runB);
    } else if (!runB && run.id !== runA.id) {
      setRunB(sel);
      setCompareData(null);
      setError(null);
      replaceUrl(runA, sel);
    }
  }

  const canCompare = runA && runB && runA.id !== runB.id;
  const sameRunError = runA && runB && runA.id === runB.id;
  const showQuickPicks = (!runA || !runB) && quickPicks.length > 0 && !compareData;
  const needsSelection = !runA || !runB;

  // Filter quick picks: exclude already-selected runs
  const visiblePicks = quickPicks.filter(
    (r) => r.id !== runA?.id && r.id !== runB?.id,
  );
  const failedPicks = visiblePicks.filter((r) => r.status === "failed");
  const otherPicks = visiblePicks.filter((r) => r.status !== "failed");

  return (
    <div className="max-w-5xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-[17px] font-semibold tracking-tight text-neutral-900">Compare Runs</h1>
        <p className="mt-0.5 text-[12px] text-neutral-400">
          Pick two runs from the same project to see what changed.
        </p>
      </div>

      {/* Run selectors */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <RunSelector
          label="Run A"
          value={runA}
          onChange={handleChangeA}
          excludeId={runB?.id}
        />
        <RunSelector
          label="Run B"
          value={runB}
          onChange={handleChangeB}
          excludeId={runA?.id}
          autoFocus={!!runA && !runB}
        />
      </div>

      {/* Quick picks */}
      {showQuickPicks && visiblePicks.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-[11px] font-medium text-neutral-400">
            {runA ? "Select Run B" : "Quick picks"}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {failedPicks.length > 0 && failedPicks.map((run) => (
              <QuickPickChip key={run.id} run={run} onClick={() => handleQuickPick(run)} />
            ))}
            {otherPicks.slice(0, failedPicks.length > 0 ? 4 : 6).map((run) => (
              <QuickPickChip key={run.id} run={run} onClick={() => handleQuickPick(run)} />
            ))}
          </div>
        </div>
      )}

      {/* Action area */}
      <div className="mb-8 mt-5">
        {sameRunError && (
          <p className="mb-2.5 text-xs text-[var(--error-accent)]">
            You&apos;ve selected the same run for both sides. Pick a different run for B.
          </p>
        )}

        {!compareData && !loading && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleCompare}
              disabled={!canCompare || loading}
              className="inline-flex items-center gap-2 rounded-lg bg-neutral-900 px-5 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-30"
            >
              <GitCompareArrows size={14} />
              Compare
            </button>
            {needsSelection && !sameRunError && (
              <span className="text-[11px] text-neutral-400">
                {!runA && !runB
                  ? "Select two runs to compare"
                  : !runB
                    ? "Now select Run B"
                    : "Now select Run A"}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="py-12 text-center">
          <div className="mx-auto mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-neutral-100">
            <GitCompareArrows size={16} className="animate-pulse text-neutral-400" />
          </div>
          <p className="text-sm text-neutral-500">Comparing runs…</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-[var(--tint-error-block)] p-4 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}

      {/* Empty state — no runs selected, no quick picks active */}
      {!compareData && !loading && !error && !runA && !runB && (
        <div className="rounded-lg border border-dashed border-neutral-200 px-6 py-14 text-center">
          <GitCompareArrows size={24} className="mx-auto mb-3 text-neutral-300" />
          <p className="text-sm font-medium text-neutral-500">No runs selected yet</p>
          <p className="mx-auto mt-1 max-w-[280px] text-[11px] leading-relaxed text-neutral-400">
            Use the selectors above, or open a run and click &ldquo;Compare&rdquo; to get started.
          </p>
        </div>
      )}

      {/* Tip — shown when one run is selected */}
      {!compareData && !loading && !error && runA && !runB && (
        <div className="flex items-start gap-2.5 rounded-lg bg-neutral-50 px-4 py-2.5">
          <Lightbulb size={13} className="mt-0.5 shrink-0 text-neutral-400" />
          <p className="text-[11px] leading-relaxed text-neutral-400">
            Run A is set. Search or pick a run for B to see what changed.
          </p>
        </div>
      )}

      {/* Results */}
      {compareData && <CompareResults data={compareData} />}
    </div>
  );
}

function QuickPickChip({ run, onClick }: { run: RunListItem; onClick: () => void }) {
  const failed = run.status === "failed";
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-medium transition-colors ${
        failed
          ? "border-[var(--accent-fail)] bg-[var(--tint-error)] text-neutral-700 hover:bg-[var(--tint-error-block)]"
          : "border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300 hover:bg-neutral-50"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          failed ? "bg-[var(--error-accent)]" : "bg-neutral-300"
        }`}
      />
      <span className="max-w-[140px] truncate">{run.workflow_name}</span>
      <span className="text-neutral-400">{timeAgo(run.created_at)}</span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Comparison results rendering
// ---------------------------------------------------------------------------

function CompareResults({ data }: { data: CompareResponse }) {
  return (
    <div>
      <div className="mb-6 grid grid-cols-2 gap-4">
        <RunSummaryCard label="Run A" run={data.run_a} />
        <RunSummaryCard label="Run B" run={data.run_b} />
      </div>

      <RunDiffSection diff={data.run_diff} />

      <section>
        <h2 className="mb-5 text-[13px] font-semibold tracking-tight text-neutral-900">Steps</h2>
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
    <div className="rounded-lg bg-white p-4 shadow-[0_1px_4px_rgba(0,0,0,0.05)]">
      <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        {label}
      </div>
      <div className="flex items-center gap-2">
        <span className="font-semibold text-neutral-900">{run.workflow_name}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(run.status)}`}
        >
          {run.status}
        </span>
      </div>
      <div className="mt-1 text-sm text-neutral-500">{formatDate(run.created_at)}</div>
      <div className="mt-0.5 font-mono text-xs text-neutral-400">
        <Link href={`/runs/${run.id}`} className="hover:text-neutral-600">
          {run.id.slice(0, 8)}
        </Link>
      </div>
    </div>
  );
}

function RunDiffSection({ diff }: { diff: CompareRunDiff }) {
  const hasDiff = diff.status_diff || diff.output_diff || diff.error_diff;

  return (
    <section
      className={`mb-8 rounded-lg p-5 ${
        hasDiff
          ? "bg-[var(--tint-diff)] shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
          : "bg-white shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
      }`}
    >
      <h2 className="mb-5 text-[13px] font-semibold tracking-tight text-neutral-900">Run Result</h2>

      <div className="space-y-5">
        <DiffRow label="Status" diff={diff.status_diff}>
          <DiffCellText side="A" value={diff.status_a} />
          <DiffCellText side="B" value={diff.status_b} />
        </DiffRow>

        <DataDiffRow
          label="Output"
          diff={diff.output_diff}
          dataA={diff.output_summary_a}
          dataB={diff.output_summary_b}
        />

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

  const cardStyle = missing
    ? "bg-[var(--tint-diff-strong)] shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
    : hasDiff
      ? "bg-[var(--tint-diff)] shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
      : "bg-white shadow-[0_1px_4px_rgba(0,0,0,0.05)]";

  const stepName = step.name_a ?? step.name_b ?? "—";
  const stepType = step.step_type_a ?? step.step_type_b ?? "—";
  const isLlm = stepType === "llm";

  return (
    <div className={`rounded-lg p-5 ${cardStyle}`}>
      <div className="mb-5 flex items-center gap-2">
        <span className="font-mono text-xs text-neutral-400">#{step.sequence_index}</span>
        <span className="text-[13px] font-semibold tracking-tight text-neutral-900">
          {stepName}
        </span>
        <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
          isLlm
            ? "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400"
            : "bg-neutral-100 text-neutral-400"
        }`}>
          {stepType}
        </span>
        {missing && (
          <span className="rounded-full bg-[var(--diff-badge-bg)] px-2.5 py-0.5 text-[10px] font-medium text-[var(--diff-badge-text)]">
            {!step.exists_in_a ? "missing in A" : "missing in B"}
          </span>
        )}
      </div>

      <div className="space-y-5">
        <DiffRow label="Status" diff={step.status_diff}>
          <DiffCellText side="A" value={step.status_a} />
          <DiffCellText side="B" value={step.status_b} />
        </DiffRow>

        <DataDiffRow
          label="Output"
          diff={step.output_diff}
          dataA={step.output_summary_a}
          dataB={step.output_summary_b}
        />

        {(step.error_summary_a || step.error_summary_b) && (
          <DiffRow label="Error" diff={step.error_diff} isError>
            <DiffCellText
              side="A"
              value={errorHeadline(step.error_summary_a) || null}
              isError
            />
            <DiffCellText
              side="B"
              value={errorHeadline(step.error_summary_b) || null}
              isError
            />
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
    ? isError
      ? "bg-[var(--tint-diff-error-row)]"
      : "bg-[var(--tint-diff-row)]"
    : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        {label}
        {diff && (
          <span className="rounded bg-[var(--diff-badge-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--diff-badge-text)]">
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
  const textColor = isError ? "text-[var(--error-text)]" : "text-neutral-700";

  return (
    <div>
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        {side}
      </div>
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
  const bg = diff ? "bg-[var(--tint-diff-row)]" : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span className="flex items-center gap-2">
          {label}
          {diff && (
            <span className="rounded bg-[var(--diff-badge-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--diff-badge-text)]">
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
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        {side}
      </div>
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
