"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { errorHeadline, formatDate, formatDuration, rawJson, resolveData, statusClass, timeAgo } from "@/lib/format";
import { StructuredValue } from "@/components/structured-value";
import { ROLE_STYLES, extractMessageContent } from "@/components/llm-step-detail";
import { RunSelector, type SelectedRun } from "@/components/run-selector";
import { GitCompareArrows, Lightbulb } from "lucide-react";
import type {
  CompareResponse,
  CompareRunDiff,
  CompareRunSummary,
  CompareStepDiff,
  LLMShape,
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

  useEffect(() => {
    if (paramA && paramB && !didAutoLoad.current) {
      didAutoLoad.current = true;
      fetchComparison(paramA, paramB);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramA, paramB]);

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

  const visiblePicks = quickPicks.filter(
    (r) => r.id !== runA?.id && r.id !== runB?.id,
  );
  const failedPicks = visiblePicks.filter((r) => r.status === "failed");
  const otherPicks = visiblePicks.filter((r) => r.status !== "failed");

  return (
    <div className="max-w-5xl">
      <div className="mb-6">
        <h1 className="text-[17px] font-semibold tracking-tight text-neutral-900">Compare Runs</h1>
        <p className="mt-0.5 text-[12px] text-neutral-400">
          Pick two runs from the same project to see what changed.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <RunSelector label="Run A" value={runA} onChange={handleChangeA} excludeId={runB?.id} />
        <RunSelector label="Run B" value={runB} onChange={handleChangeB} excludeId={runA?.id} autoFocus={!!runA && !runB} />
      </div>

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

      {loading && (
        <div className="py-12 text-center">
          <div className="mx-auto mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-neutral-100">
            <GitCompareArrows size={16} className="animate-pulse text-neutral-400" />
          </div>
          <p className="text-sm text-neutral-500">Comparing runs…</p>
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-[var(--tint-error-block)] p-4 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}

      {!compareData && !loading && !error && !runA && !runB && (
        <div className="rounded-lg border border-dashed border-neutral-200 px-6 py-14 text-center">
          <GitCompareArrows size={24} className="mx-auto mb-3 text-neutral-300" />
          <p className="text-sm font-medium text-neutral-500">No runs selected yet</p>
          <p className="mx-auto mt-1 max-w-[280px] text-[11px] leading-relaxed text-neutral-400">
            Use the selectors above, or open a run and click &ldquo;Compare&rdquo; to get started.
          </p>
        </div>
      )}

      {!compareData && !loading && !error && runA && !runB && (
        <div className="flex items-start gap-2.5 rounded-lg bg-neutral-50 px-4 py-2.5">
          <Lightbulb size={13} className="mt-0.5 shrink-0 text-neutral-400" />
          <p className="text-[11px] leading-relaxed text-neutral-400">
            Run A is set. Search or pick a run for B to see what changed.
          </p>
        </div>
      )}

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

// ===========================================================================
// Comparison results
// ===========================================================================

function stepDiffKey(s: CompareStepDiff): string {
  return `${s.match_kind}:${s.sequence_index_a ?? "x"}-${s.sequence_index_b ?? "x"}:${s.name_a ?? ""}:${s.name_b ?? ""}`;
}

function CompareResults({ data }: { data: CompareResponse }) {
  const matchedCount = data.steps.filter((s) => s.match_kind !== "missing").length;
  const missingCount = data.steps.filter((s) => s.match_kind === "missing").length;
  const lowOverlap = data.steps.length >= 3 && missingCount > matchedCount;

  return (
    <div>
      <div className="mb-6 grid grid-cols-2 gap-4">
        <RunSummaryCard label="Run A" run={data.run_a} />
        <RunSummaryCard label="Run B" run={data.run_b} />
      </div>

      <RunDiffSection diff={data.run_diff} />

      <section>
        <div className="mb-5 flex items-center gap-3">
          <h2 className="text-[13px] font-semibold tracking-tight text-neutral-900">Steps</h2>
          {data.steps.length > 0 && (
            <span className="text-[11px] text-neutral-400">
              {matchedCount} matched · {missingCount} missing
            </span>
          )}
        </div>

        {lowOverlap && (
          <div className="mb-4 flex items-start gap-2.5 rounded-lg bg-neutral-50 px-4 py-2.5">
            <Lightbulb size={13} className="mt-0.5 shrink-0 text-neutral-400" />
            <p className="text-[11px] leading-relaxed text-neutral-400">
              Low structural overlap between these runs. Most steps could not be matched.
            </p>
          </div>
        )}

        {data.steps.length === 0 ? (
          <p className="text-sm text-neutral-500">No steps to compare.</p>
        ) : (
          <div className="space-y-5">
            {data.steps.map((step) => (
              <StepDiffCard key={stepDiffKey(step)} step={step} />
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
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(run.status)}`}>
          {run.status}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-3 text-sm text-neutral-500">
        <span>{formatDate(run.created_at)}</span>
        {run.total_steps > 0 && (
          <span className="text-xs text-neutral-400">{run.total_steps} steps</span>
        )}
        {run.total_duration_ms != null && (
          <span className="text-xs text-neutral-400">{formatDuration(run.total_duration_ms)}</span>
        )}
      </div>
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

// ===========================================================================
// Step diff card — switches between generic and LLM-aware rendering
// ===========================================================================

function StepDiffCard({ step }: { step: CompareStepDiff }) {
  const hasDiff = step.status_diff || step.output_diff || step.error_diff || step.input_diff;
  const missing = step.match_kind === "missing";
  const isFallback = step.match_kind === "fallback_type_index";
  const isLlm = !!step.llm_a || !!step.llm_b;

  const absentA = !step.exists_in_a;
  const absentB = !step.exists_in_b;

  const cardStyle = missing
    ? "bg-[var(--tint-diff-strong)] shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
    : hasDiff
      ? "bg-[var(--tint-diff)] shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
      : "bg-white shadow-[0_1px_4px_rgba(0,0,0,0.05)]";

  return (
    <div className={`rounded-lg p-5 ${cardStyle}`}>
      <StepDiffHeader step={step} isLlm={isLlm} missing={missing} isFallback={isFallback} />

      <div className="space-y-5">
        {/* LLM metadata diff */}
        {isLlm && <LlmMetaDiff a={step.llm_a} b={step.llm_b} />}

        {/* Status — always shown */}
        <DiffRow label="Status" diff={step.status_diff}>
          <DiffCellText side="A" value={step.status_a} absent={absentA} />
          <DiffCellText side="B" value={step.status_b} absent={absentB} />
        </DiffRow>

        {/* Input — LLM-aware or generic */}
        {isLlm ? (
          <LlmInputDiff a={step.llm_a} b={step.llm_b} />
        ) : (
          (step.input_summary_a || step.input_summary_b) && (
            <DataDiffRow
              label="Input"
              diff={step.input_diff}
              dataA={step.input_summary_a}
              dataB={step.input_summary_b}
              absentA={absentA}
              absentB={absentB}
            />
          )
        )}

        {/* Output — LLM-aware or generic */}
        {isLlm ? (
          <LlmOutputDiff a={step.llm_a} b={step.llm_b} diff={step.output_diff} />
        ) : (
          <DataDiffRow
            label="Output"
            diff={step.output_diff}
            dataA={step.output_summary_a}
            dataB={step.output_summary_b}
            absentA={absentA}
            absentB={absentB}
          />
        )}

        {/* Error — always shown when present */}
        {(step.error_summary_a || step.error_summary_b) && (
          <DiffRow label="Error" diff={step.error_diff} isError>
            <DiffCellText side="A" value={errorHeadline(step.error_summary_a) || null} isError absent={absentA} />
            <DiffCellText side="B" value={errorHeadline(step.error_summary_b) || null} isError absent={absentB} />
          </DiffRow>
        )}

        {/* Usage — only for LLM steps */}
        {isLlm && <LlmUsageDiff a={step.llm_a} b={step.llm_b} />}
      </div>
    </div>
  );
}

// ===========================================================================
// Step header — name, type, match labels, sequence indexes
// ===========================================================================

function StepDiffHeader({
  step,
  isLlm,
  missing,
  isFallback,
}: {
  step: CompareStepDiff;
  isLlm: boolean;
  missing: boolean;
  isFallback: boolean;
}) {
  const nameA = step.name_a;
  const nameB = step.name_b;
  const bothExist = step.exists_in_a && step.exists_in_b;
  const namesMatch = bothExist && nameA === nameB;

  const stepType = step.step_type_a ?? step.step_type_b ?? "—";

  const idxA = step.sequence_index_a;
  const idxB = step.sequence_index_b;
  const idxLabel =
    idxA != null && idxB != null
      ? idxA === idxB ? `#${idxA}` : `#${idxA}→#${idxB}`
      : idxA != null ? `#${idxA}`
      : idxB != null ? `#${idxB}`
      : null;

  const hasDuration = bothExist && (step.duration_ms_a != null || step.duration_ms_b != null);

  return (
    <div className="mb-5 flex flex-wrap items-center gap-2">
      {idxLabel && (
        <span className="font-mono text-xs text-neutral-400">{idxLabel}</span>
      )}

      {namesMatch ? (
        <span className="text-[13px] font-semibold tracking-tight text-neutral-900">
          {nameA}
        </span>
      ) : isFallback && nameA && nameB ? (
        <span className="text-[13px] tracking-tight text-neutral-900">
          <span className="font-semibold">{nameA}</span>
          <span className="mx-1 text-[11px] text-neutral-400">↔</span>
          <span className="font-semibold">{nameB}</span>
        </span>
      ) : (
        <span className="text-[13px] font-semibold tracking-tight text-neutral-900">
          {nameA ?? nameB ?? "—"}
        </span>
      )}

      <span
        className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
          isLlm
            ? "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400"
            : "bg-neutral-100 text-neutral-400"
        }`}
      >
        {stepType}
      </span>

      {hasDuration && (
        <span className="text-[11px] text-neutral-400">
          {formatDuration(step.duration_ms_a)} → {formatDuration(step.duration_ms_b)}
        </span>
      )}

      {missing && (
        <span className="rounded-full bg-[var(--diff-badge-bg)] px-2.5 py-0.5 text-[10px] font-medium text-[var(--diff-badge-text)]">
          {!step.exists_in_a ? "missing in A" : "missing in B"}
        </span>
      )}
      {isFallback && (
        <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:border-amber-800/40 dark:bg-amber-950/30 dark:text-amber-400">
          approx match
        </span>
      )}
    </div>
  );
}

// ===========================================================================
// LLM-aware diff components
// ===========================================================================

function LlmMetaDiff({ a, b }: { a: LLMShape | null; b: LLMShape | null }) {
  const provDiff = (a?.provider ?? null) !== (b?.provider ?? null);
  const modelDiff = (a?.model ?? null) !== (b?.model ?? null);
  const anyDiff = provDiff || modelDiff;

  const bg = anyDiff ? "bg-[var(--tint-diff-row)]" : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Metadata
        {anyDiff && <ChangedBadge />}
      </div>
      <div className="grid grid-cols-2 gap-0">
        <div className="pr-4">
          <SideLabel side="A" />
          <MetaPills llm={a} />
        </div>
        <div className="border-l border-neutral-200 pl-4">
          <SideLabel side="B" />
          <MetaPills llm={b} />
        </div>
      </div>
    </div>
  );
}

function MetaPills({ llm }: { llm: LLMShape | null }) {
  if (!llm) return <p className="text-xs italic text-neutral-400">—</p>;

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
      {llm.provider && (
        <span className="text-neutral-400">
          provider <span className="font-medium text-neutral-700">{llm.provider}</span>
        </span>
      )}
      {llm.model && (
        <span className="text-neutral-400">
          model <span className="font-medium text-neutral-700">{llm.model}</span>
        </span>
      )}
      {llm.meta.latency_ms != null && (
        <span className="text-neutral-400">
          latency <span className="font-medium text-neutral-700">{formatDuration(llm.meta.latency_ms)}</span>
        </span>
      )}
      {llm.meta.finish_reason && (
        <span className="text-neutral-400">
          finish <span className="font-medium text-neutral-700">{llm.meta.finish_reason}</span>
        </span>
      )}
      {llm.usage.total_tokens != null && (
        <span className="text-neutral-400">
          tokens <span className="font-medium tabular-nums text-neutral-700">{llm.usage.total_tokens.toLocaleString()}</span>
        </span>
      )}
    </div>
  );
}

function LlmInputDiff({ a, b }: { a: LLMShape | null; b: LLMShape | null }) {
  const hasA = !!(a && (a.input.system || a.input.messages.length > 0));
  const hasB = !!(b && (b.input.system || b.input.messages.length > 0));
  if (!hasA && !hasB) return null;

  const diff = JSON.stringify(a?.input) !== JSON.stringify(b?.input);
  const bg = diff ? "bg-[var(--tint-diff-row)]" : "bg-[var(--tint-input)]";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Input
        {diff && <ChangedBadge />}
      </div>
      <div className="grid grid-cols-2 gap-0">
        <div className="pr-4">
          <SideLabel side="A" />
          <InputMessages llm={a} />
        </div>
        <div className="border-l border-neutral-200 pl-4">
          <SideLabel side="B" />
          <InputMessages llm={b} />
        </div>
      </div>
    </div>
  );
}

function InputMessages({ llm }: { llm: LLMShape | null }) {
  if (!llm || (!llm.input.system && llm.input.messages.length === 0)) {
    return <p className="text-xs italic text-neutral-400">No prompt</p>;
  }

  return (
    <div className="space-y-2.5">
      {llm.input.system && (
        <div>
          <span className={`text-[10px] font-medium ${ROLE_STYLES.system}`}>system</span>
          <pre className="mt-0.5 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
            {llm.input.system}
          </pre>
        </div>
      )}
      {llm.input.messages.map((msg, i) => {
        const role = (msg.role as string) ?? "unknown";
        const content = extractMessageContent(msg);
        const color = ROLE_STYLES[role] ?? "text-neutral-400";
        return (
          <div key={i}>
            <span className={`text-[10px] font-medium ${color}`}>{role}</span>
            <pre className="mt-0.5 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
              {content || "(empty)"}
            </pre>
          </div>
        );
      })}
      {llm.input.tools.length > 0 && (
        <div>
          <span className="text-[10px] font-medium text-neutral-400">tools</span>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {llm.input.tools.map((t, i) => (
              <span key={i} className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-500">
                {(t.name as string) ?? (t.function as Dict)?.name ?? "tool"}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function LlmOutputDiff({ a, b, diff }: { a: LLMShape | null; b: LLMShape | null; diff: boolean }) {
  const bg = diff ? "bg-[var(--tint-diff-row)]" : "bg-[var(--tint-output)]";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Output
        {diff && <ChangedBadge />}
      </div>
      <div className="grid grid-cols-2 gap-0">
        <div className="pr-4">
          <SideLabel side="A" />
          <OutputContent llm={a} />
        </div>
        <div className="border-l border-neutral-200 pl-4">
          <SideLabel side="B" />
          <OutputContent llm={b} />
        </div>
      </div>
    </div>
  );
}

function OutputContent({ llm }: { llm: LLMShape | null }) {
  if (!llm || (!llm.output.text && llm.output.tool_calls.length === 0)) {
    return <p className="text-xs italic text-neutral-400">No output</p>;
  }

  return (
    <div className="space-y-2">
      {llm.output.text && (
        <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
          {llm.output.text}
        </pre>
      )}
      {llm.output.tool_calls.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[10px] font-medium text-neutral-400">Tool calls</span>
          {llm.output.tool_calls.map((tc, i) => (
            <div key={i} className="rounded bg-neutral-50 px-2 py-1.5">
              <span className="font-mono text-[11px] font-medium text-neutral-700">
                {(tc.name as string) ?? "call"}
              </span>
              {tc.arguments != null && (
                <pre className="mt-0.5 whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-neutral-500">
                  {typeof tc.arguments === "string"
                    ? tc.arguments
                    : JSON.stringify(tc.arguments, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LlmUsageDiff({ a, b }: { a: LLMShape | null; b: LLMShape | null }) {
  const uA = a?.usage;
  const uB = b?.usage;
  const hasAny =
    (uA?.prompt_tokens ?? uA?.completion_tokens ?? uA?.total_tokens) != null ||
    (uB?.prompt_tokens ?? uB?.completion_tokens ?? uB?.total_tokens) != null;
  if (!hasAny) return null;

  const diff =
    uA?.prompt_tokens !== uB?.prompt_tokens ||
    uA?.completion_tokens !== uB?.completion_tokens ||
    uA?.total_tokens !== uB?.total_tokens;
  const bg = diff ? "bg-[var(--tint-diff-row)]" : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Tokens
        {diff && <ChangedBadge />}
      </div>
      <div className="grid grid-cols-2 gap-0">
        <div className="pr-4">
          <SideLabel side="A" />
          <UsagePills usage={uA} />
        </div>
        <div className="border-l border-neutral-200 pl-4">
          <SideLabel side="B" />
          <UsagePills usage={uB} />
        </div>
      </div>
    </div>
  );
}

function UsagePills({ usage }: { usage?: LLMShape["usage"] | null }) {
  if (!usage) return <p className="text-xs italic text-neutral-400">—</p>;
  const items: { label: string; value: number }[] = [];
  if (usage.prompt_tokens != null) items.push({ label: "prompt", value: usage.prompt_tokens });
  if (usage.completion_tokens != null) items.push({ label: "completion", value: usage.completion_tokens });
  if (usage.total_tokens != null) items.push({ label: "total", value: usage.total_tokens });
  if (items.length === 0) return <p className="text-xs italic text-neutral-400">—</p>;

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
      {items.map((item) => (
        <span key={item.label} className="text-neutral-400">
          {item.label}{" "}
          <span className="font-medium tabular-nums text-neutral-700">
            {item.value.toLocaleString()}
          </span>
        </span>
      ))}
    </div>
  );
}

// ===========================================================================
// Shared primitives
// ===========================================================================

function SideLabel({ side }: { side: string }) {
  return (
    <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
      {side}
    </div>
  );
}

function ChangedBadge() {
  return (
    <span className="rounded bg-[var(--diff-badge-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--diff-badge-text)]">
      changed
    </span>
  );
}

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
        {diff && <ChangedBadge />}
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
  absent,
}: {
  side: string;
  value: string | null;
  isError?: boolean;
  absent?: boolean;
}) {
  const textColor = isError ? "text-[var(--error-text)]" : "text-neutral-700";

  return (
    <div>
      <SideLabel side={side} />
      {absent ? (
        <p className="text-[11px] italic text-neutral-300">Not present</p>
      ) : value ? (
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
  absentA,
  absentB,
}: {
  label: string;
  diff: boolean;
  dataA: Dict | null;
  dataB: Dict | null;
  absentA?: boolean;
  absentB?: boolean;
}) {
  const [raw, setRaw] = useState(false);
  const hasAny = dataA != null || dataB != null;
  const bg = diff ? "bg-[var(--tint-diff-row)]" : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span className="flex items-center gap-2">
          {label}
          {diff && <ChangedBadge />}
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
          <DataCell side="A" data={dataA} raw={raw} absent={absentA} />
        </div>
        <div className="border-l border-neutral-200 pl-4">
          <DataCell side="B" data={dataB} raw={raw} absent={absentB} />
        </div>
      </div>
    </div>
  );
}

function DataCell({ side, data, raw, absent }: { side: string; data: Dict | null; raw: boolean; absent?: boolean }) {
  const resolved = resolveData(data);
  const rawText = rawJson(data);

  return (
    <div>
      <SideLabel side={side} />
      {absent ? (
        <p className="text-[11px] italic text-neutral-300">Not present</p>
      ) : resolved == null ? (
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
