"use client";

import { Suspense, useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, fetchArtifactContent } from "@/lib/api";
import { formatDate, formatDuration, rawJson, resolveData, statusClass, timeAgo } from "@/lib/format";
import { computeLatencyBreakdown, type LatencyBreakdown } from "@/lib/latency";
import { StructuredValue } from "@/components/structured-value";
import { ROLE_STYLES, extractMessageContent, tryParseJson, resolveArgs, StreamSection } from "@/components/llm-step-detail";
import { CompareMediaBadge } from "@/components/media-artifact";
import { ExpandableTextBlock } from "@/components/expandable-text-block";
import { RunSelector, type SelectedRun } from "@/components/run-selector";
import { useProject } from "@/components/project-provider";
import { GitCompareArrows, Lightbulb } from "lucide-react";
import {
  isMcpMeta,
  getCapabilityKindFromMeta,
  isRetrievalMeta,
  getRetrievalStageFromMeta,
  CAPABILITY_BADGE,
  MCP_BADGE,
  RETRIEVAL_STAGE_BADGE,
} from "@/lib/step-metadata";
import {
  isPartialCapture,
  refusalCompareState,
  getCachedTokens,
  cachedTokensDiverges,
  isJsonOutput,
  jsonOutputDiverges,
  PARTIAL_CAPTURE_TOOLTIP,
  toolCallLabel,
} from "@/lib/provider-hardening";
import type {
  CompareResponse,
  CompareRunDiff,
  CompareRunSummary,
  CompareStepDiff,
  LLMShape,
  ProjectRunsResponse,
  RunListItem,
  TimelineResponse,
  TimelineRun,
  TimelineStep,
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
  const { current: project } = useProject();

  const paramA = searchParams.get("a");
  const paramB = searchParams.get("b");

  const [runA, setRunA] = useState<SelectedRun | null>(null);
  const [runB, setRunB] = useState<SelectedRun | null>(null);
  const [compareData, setCompareData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quickPicks, setQuickPicks] = useState<RunListItem[]>([]);

  const didAutoLoad = useRef(false);

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

  const syncRunsFromParams = useEffectEvent(() => {
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
  });

  useEffect(() => {
    syncRunsFromParams();
  }, [paramA, paramB]);

  useEffect(() => {
    if (paramA && paramB && !didAutoLoad.current) {
      didAutoLoad.current = true;
      fetchComparison(paramA, paramB);
    }
  }, [paramA, paramB, fetchComparison]);

  useEffect(() => {
    if (!project) return;
    apiFetch<ProjectRunsResponse>(`/v1/projects/${encodeURIComponent(project)}/runs?limit=6&sort=newest`)
      .then((d) => setQuickPicks(d.runs))
      .catch(() => setQuickPicks([]));
  }, [project]);

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
        <RunSelector key={`a-${project}`} label="Run A" value={runA} onChange={handleChangeA} excludeId={runB?.id} />
        <RunSelector key={`b-${project}`} label="Run B" value={runB} onChange={handleChangeB} excludeId={runA?.id} autoFocus={!!runA && !runB} />
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

      <InsightBlock data={data} />

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
              <StepDiffCard key={stepDiffKey(step)} step={step} allSteps={data.steps} runIdA={data.run_a.id} runIdB={data.run_b.id} />
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
          <DataDiffRow
            label="Error"
            diff={diff.error_diff}
            dataA={diff.error_summary_a}
            dataB={diff.error_summary_b}
            isError
          />
        )}
      </div>
    </section>
  );
}

// ===========================================================================
// Step diff card — switches between generic and LLM-aware rendering
// ===========================================================================

function StepDiffCard({ step, allSteps, runIdA, runIdB }: { step: CompareStepDiff; allSteps: CompareStepDiff[]; runIdA: string; runIdB: string }) {
  const hasDiff = step.status_diff || step.output_diff || step.error_diff || step.input_diff;
  const missing = step.match_kind === "missing";
  const isFallback = step.match_kind === "fallback_type_index";
  const isLlm = !!step.llm_a || !!step.llm_b;
  const isTool = (step.step_type_a ?? step.step_type_b) === "tool";

  const absentA = !step.exists_in_a;
  const absentB = !step.exists_in_b;

  const cardStyle = missing
    ? "bg-[var(--tint-diff-strong)] shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
    : hasDiff
      ? "bg-[var(--tint-diff)] shadow-[0_1px_4px_rgba(0,0,0,0.05)]"
      : "bg-white shadow-[0_1px_4px_rgba(0,0,0,0.05)]";

  return (
    <div className={`rounded-lg p-5 ${cardStyle}`}>
      <StepDiffHeader
        step={step}
        isLlm={isLlm}
        isTool={isTool}
        missing={missing}
        isFallback={isFallback}
        isStreamA={!!streamVal(step.metadata_a)}
        isStreamB={!!streamVal(step.metadata_b)}
      />

      <div className="space-y-5">
        {/* LLM metadata diff */}
        {isLlm && <LlmMetaDiff a={step.llm_a} b={step.llm_b} />}

        {/* LLM latency breakdown diff */}
        {isLlm && (
          <LlmLatencyDiff
            llmA={step.llm_a}
            llmB={step.llm_b}
            durationMsA={step.duration_ms_a}
            durationMsB={step.duration_ms_b}
            metaA={step.metadata_a}
            metaB={step.metadata_b}
          />
        )}

        {/* Tool linkage diff */}
        {isTool && <ToolLinkageDiff step={step} absentA={absentA} absentB={absentB} />}

        {/* MCP metadata diff */}
        <McpCompareDiff metaA={step.metadata_a} metaB={step.metadata_b} absentA={absentA} absentB={absentB} />

        {/* Capability / skill diff */}
        <CapabilityCompareDiff metaA={step.metadata_a} metaB={step.metadata_b} absentA={absentA} absentB={absentB} />

        {/* Retrieval metadata diff — identity-only when output section also renders */}
        <RetrievalCompareDiff
          metaA={step.metadata_a}
          metaB={step.metadata_b}
          absentA={absentA}
          absentB={absentB}
          identityOnly={_isRetrievalOutput(step.output_summary_a) || _isRetrievalOutput(step.output_summary_b)}
        />

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

        {/* Output — LLM-aware, retrieval-aware, or generic */}
        {isLlm ? (
          <LlmOutputDiff a={step.llm_a} b={step.llm_b} diff={step.output_diff} />
        ) : _isRetrievalOutput(step.output_summary_a) || _isRetrievalOutput(step.output_summary_b) ? (
          <RetrievalOutputDiff
            dataA={step.output_summary_a}
            dataB={step.output_summary_b}
            diff={step.output_diff}
            absentA={absentA}
            absentB={absentB}
          />
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
          <DataDiffRow
            label="Error"
            diff={step.error_diff}
            dataA={step.error_summary_a}
            dataB={step.error_summary_b}
            absentA={absentA}
            absentB={absentB}
            isError
          />
        )}

        {/* Tool calls diff — only for LLM steps with tool calls */}
        {isLlm && (
          <ToolCallsDiff
            summaryA={step.output_summary_a}
            summaryB={step.output_summary_b}
            allSteps={allSteps}
          />
        )}

        {/* Usage — only for LLM steps */}
        {isLlm && <LlmUsageDiff a={step.llm_a} b={step.llm_b} />}

        {/* Stream diff — only for LLM steps with stream metadata */}
        {isLlm && (
          <LlmStreamDiff
            metaA={step.metadata_a}
            metaB={step.metadata_b}
            runIdA={runIdA}
            runIdB={runIdB}
            seqIdxA={step.sequence_index_a}
            seqIdxB={step.sequence_index_b}
            stepNameA={step.name_a}
            stepNameB={step.name_b}
          />
        )}
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
  isTool,
  missing,
  isFallback,
  isStreamA,
  isStreamB,
}: {
  step: CompareStepDiff;
  isLlm: boolean;
  isTool: boolean;
  missing: boolean;
  isFallback: boolean;
  isStreamA: boolean;
  isStreamB: boolean;
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
  const toolProvider = isTool ? (step.model_provider_a ?? step.model_provider_b) : null;
  const toolModel = isTool ? (step.model_name_a ?? step.model_name_b) : null;

  const isChild = !!(step.parent_step_id_a || step.parent_step_id_b);
  const parentDiff = isChild && step.parent_step_id_a !== step.parent_step_id_b;

  return (
    <div className="mb-5">
      <div className="flex flex-wrap items-center gap-2">
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
              : isTool
                ? "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400"
                : "bg-neutral-100 text-neutral-400"
          }`}
        >
          {stepType}
        </span>

        {(isStreamA || isStreamB) && (
          <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-500 dark:bg-violet-950/30 dark:text-violet-400">
            {isStreamA && isStreamB ? "stream" : isStreamA ? "stream A only" : "stream B only"}
          </span>
        )}

        {(() => {
          const r = refusalCompareState(step.llm_a, step.llm_b);
          if (!r.a && !r.b) return null;
          const label = r.a && r.b ? "refusal" : r.a ? "refusal A only" : "refusal B only";
          const cls = r.diverges
            ? "bg-[var(--diff-badge-bg)] text-[var(--diff-badge-text)]"
            : "bg-rose-50 text-rose-600 dark:bg-rose-950/30 dark:text-rose-400";
          return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>;
        })()}

        {(() => {
          const pa = isPartialCapture(step.metadata_a);
          const pb = isPartialCapture(step.metadata_b);
          if (!pa && !pb) return null;
          const label = pa && pb ? "partial" : pa ? "partial A only" : "partial B only";
          const cls = pa !== pb
            ? "bg-[var(--diff-badge-bg)] text-[var(--diff-badge-text)]"
            : "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400";
          return (
            <span title={PARTIAL_CAPTURE_TOOLTIP} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
              {label}
            </span>
          );
        })()}

        {(() => {
          const ja = isJsonOutput(step.llm_a);
          const jb = isJsonOutput(step.llm_b);
          if (!ja && !jb) return null;
          const label = ja && jb ? "JSON" : ja ? "JSON A only" : "JSON B only";
          const cls = ja !== jb
            ? "bg-[var(--diff-badge-bg)] text-[var(--diff-badge-text)]"
            : "bg-sky-50 text-sky-600 dark:bg-sky-950/30 dark:text-sky-400";
          return <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${cls}`}>{label}</span>;
        })()}

        {(() => {
          const mcpA = isMcpMeta(step.metadata_a);
          const mcpB = isMcpMeta(step.metadata_b);
          if (!mcpA && !mcpB) return null;
          const differs = mcpA !== mcpB;
          return (
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${differs ? "bg-[var(--diff-badge-bg)] text-[var(--diff-badge-text)]" : MCP_BADGE}`}>
              {mcpA && mcpB ? "MCP" : mcpA ? "MCP A only" : "MCP B only"}
            </span>
          );
        })()}

        {(() => {
          const capA = getCapabilityKindFromMeta(step.metadata_a);
          const capB = getCapabilityKindFromMeta(step.metadata_b);
          if (!capA && !capB) return null;
          if (capA === "unknown" && capB === "unknown") return null;
          const differs = capA !== capB;
          const label = capA && capB && capA === capB
            ? capA
            : capA && capB
              ? `${capA} → ${capB}`
              : capA ? `${capA} A only` : `${capB} B only`;
          const cls = differs
            ? "bg-[var(--diff-badge-bg)] text-[var(--diff-badge-text)]"
            : (CAPABILITY_BADGE[capA ?? capB ?? "unknown"] ?? CAPABILITY_BADGE.unknown);
          return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>;
        })()}

        {(() => {
          const stA = getRetrievalStageFromMeta(step.metadata_a);
          const stB = getRetrievalStageFromMeta(step.metadata_b);
          if (!stA && !stB) return null;
          const differs = stA !== stB;
          const label = stA && stB && stA === stB
            ? stA
            : stA && stB
              ? `${stA} → ${stB}`
              : stA ? `${stA} A only` : `${stB} B only`;
          const cls = differs
            ? "bg-[var(--diff-badge-bg)] text-[var(--diff-badge-text)]"
            : RETRIEVAL_STAGE_BADGE;
          return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>;
        })()}

        {isChild && (
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
            parentDiff
              ? "bg-[var(--diff-badge-bg)] text-[var(--diff-badge-text)]"
              : "bg-neutral-100 text-neutral-400"
          }`}>
            {parentDiff ? "parent changed" : "child"}
          </span>
        )}

        {toolProvider && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:bg-amber-950/30 dark:text-amber-400">
            {toolProvider}
          </span>
        )}
        {toolModel && (
          <span className="font-mono text-[11px] text-neutral-500">{toolModel}</span>
        )}

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
    </div>
  );
}

// ===========================================================================
// Tool linkage diff
// ===========================================================================

function truncateId(id: string, max = 20): string {
  return id.length > max ? id.slice(0, max) + "…" : id;
}

type ToolStepConfidence = "exact" | "heuristic" | "unlinked";

function deriveToolStepConfidence(meta: Record<string, unknown> | null): ToolStepConfidence {
  if (!meta) return "unlinked";
  if (meta.tool_call_id) return "exact";
  if (meta.tool_name) return "heuristic";
  return "unlinked";
}

const CONFIDENCE_BADGE_COMPARE: Record<ToolStepConfidence, { label: string; className: string }> = {
  exact: { label: "exact", className: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400" },
  heuristic: { label: "heuristic", className: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400" },
  unlinked: { label: "unlinked", className: "bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500" },
};

function ToolLinkageDiff({
  step,
  absentA,
  absentB,
}: {
  step: CompareStepDiff;
  absentA: boolean;
  absentB: boolean;
}) {
  const metaA = step.metadata_a;
  const metaB = step.metadata_b;

  const provA = (metaA?.provider as string) ?? step.model_provider_a ?? null;
  const provB = (metaB?.provider as string) ?? step.model_provider_b ?? null;
  const modelA = (metaA?.model as string) ?? step.model_name_a ?? null;
  const modelB = (metaB?.model as string) ?? step.model_name_b ?? null;
  const callIdA = (metaA?.tool_call_id as string) ?? null;
  const callIdB = (metaB?.tool_call_id as string) ?? null;

  const toolNameA = (metaA?.tool_name as string) ?? null;
  const toolNameB = (metaB?.tool_name as string) ?? null;

  const confA = absentA ? "unlinked" as ToolStepConfidence : deriveToolStepConfidence(metaA);
  const confB = absentB ? "unlinked" as ToolStepConfidence : deriveToolStepConfidence(metaB);

  const hasAny =
    provA || provB ||
    modelA || modelB ||
    callIdA || callIdB ||
    toolNameA || toolNameB ||
    confA !== "unlinked" || confB !== "unlinked";
  if (!hasAny) return null;

  const provDiff = provA !== provB;
  const modelDiff = modelA !== modelB;
  const callIdDiff = callIdA !== callIdB;
  const confDiff = confA !== confB;
  const hasDiff = provDiff || modelDiff || callIdDiff || confDiff;

  const bg = hasDiff ? "bg-[var(--tint-diff-row)]" : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Linkage
        {hasDiff && <ChangedBadge />}
      </div>
      <div className="grid grid-cols-2 gap-0">
        <div className="pr-4">
          <SideLabel side="A" />
          <LinkagePills provider={provA} model={modelA} callId={callIdA} confidence={confA} absent={absentA} />
        </div>
        <div className="border-l border-neutral-200 pl-4">
          <SideLabel side="B" />
          <LinkagePills provider={provB} model={modelB} callId={callIdB} confidence={confB} absent={absentB} />
        </div>
      </div>
    </div>
  );
}

function LinkagePills({
  provider,
  model,
  callId,
  confidence,
  absent,
}: {
  provider: string | null;
  model: string | null;
  callId: string | null;
  confidence: ToolStepConfidence;
  absent?: boolean;
}) {
  if (absent) return <p className="text-[11px] italic text-neutral-300">Not present</p>;

  const confCfg = CONFIDENCE_BADGE_COMPARE[confidence];

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
      {provider && (
        <span className="rounded bg-amber-50 px-1.5 py-0.5 font-medium text-amber-600 dark:bg-amber-950/30 dark:text-amber-400">
          {provider}
        </span>
      )}
      {model && (
        <span className="font-mono text-neutral-500">{model}</span>
      )}
      {callId && (
        <span className="font-mono text-neutral-400" title={callId}>{truncateId(callId)}</span>
      )}
      <span className={`rounded px-1.5 py-px text-[9px] font-medium ${confCfg.className}`}>
        {confCfg.label}
      </span>
    </div>
  );
}

// ===========================================================================
// Tool calls diff (enriched summary comparison with id-based alignment)
// ===========================================================================

interface ToolCallSummary {
  name: string;
  id?: string;
  arguments_hash?: string;
}

function extractToolCallSummariesFromOutputSummary(
  summary: Record<string, unknown> | null | undefined,
): ToolCallSummary[] {
  if (!summary) return [];
  const calls = summary.tool_calls;
  if (!Array.isArray(calls)) return [];
  return calls.map((tc: Record<string, unknown>) => ({
    // Qualified label, so alignment and diffs treat `github.search` and
    // `jira.search` as different tools.
    name: toolCallLabel(tc, "?"),
    id: (tc.id as string) ?? undefined,
    arguments_hash: (tc.arguments_hash as string) ?? undefined,
  }));
}

type AlignedCallPair = {
  a: ToolCallSummary | null;
  b: ToolCallSummary | null;
};

/**
 * Align tool calls between two sides using:
 *   1. Exact id match (strongest)
 *   2. Same name at same position (fallback)
 *   3. Unmatched remainder
 */
function alignToolCalls(callsA: ToolCallSummary[], callsB: ToolCallSummary[]): AlignedCallPair[] {
  const pairs: AlignedCallPair[] = [];
  const usedB = new Set<number>();

  // Phase 1: exact id match
  const idToB = new Map<string, number>();
  for (let bi = 0; bi < callsB.length; bi++) {
    if (callsB[bi].id) idToB.set(callsB[bi].id!, bi);
  }

  const resolvedA = new Array<number | null>(callsA.length).fill(null);
  for (let ai = 0; ai < callsA.length; ai++) {
    if (callsA[ai].id) {
      const bi = idToB.get(callsA[ai].id!);
      if (bi !== undefined && !usedB.has(bi)) {
        resolvedA[ai] = bi;
        usedB.add(bi);
      }
    }
  }

  // Phase 2: positional name match for unresolved
  for (let ai = 0; ai < callsA.length; ai++) {
    if (resolvedA[ai] !== null) continue;
    if (ai < callsB.length && !usedB.has(ai) && callsA[ai].name === callsB[ai].name) {
      resolvedA[ai] = ai;
      usedB.add(ai);
    }
  }

  // Build pairs: matched A entries
  for (let ai = 0; ai < callsA.length; ai++) {
    const bi = resolvedA[ai];
    pairs.push({ a: callsA[ai], b: bi !== null ? callsB[bi] : null });
  }

  // Unmatched B entries
  for (let bi = 0; bi < callsB.length; bi++) {
    if (!usedB.has(bi)) {
      pairs.push({ a: null, b: callsB[bi] });
    }
  }

  return pairs;
}

function toolCallsAreDifferent(a: ToolCallSummary[], b: ToolCallSummary[]): boolean {
  if (a.length !== b.length) return true;
  const pairs = alignToolCalls(a, b);
  return pairs.some((p) => {
    if (!p.a || !p.b) return true;
    return p.a.name !== p.b.name || p.a.id !== p.b.id || p.a.arguments_hash !== p.b.arguments_hash;
  });
}

type CompareCallLifecycle = "completed" | "failed" | "unmatched";

interface CompareCallMeta {
  lifecycle: CompareCallLifecycle;
  toolStepStatus: string | null;
}

/**
 * Derive lifecycle for a tool call on a single side of compare by scanning
 * the compare steps for a matching tool step (via tool_call_id or tool_name).
 */
function deriveCompareCallLifecycle(
  tc: ToolCallSummary,
  side: "a" | "b",
  allSteps: CompareStepDiff[],
): CompareCallMeta {
  for (const s of allSteps) {
    const stepType = side === "a" ? s.step_type_a : s.step_type_b;
    if (stepType !== "tool") continue;
    const exists = side === "a" ? s.exists_in_a : s.exists_in_b;
    if (!exists) continue;

    const meta = side === "a" ? s.metadata_a : s.metadata_b;
    const callId = (meta?.tool_call_id as string) ?? null;

    if (tc.id && callId && tc.id === callId) {
      const status = (side === "a" ? s.status_a : s.status_b) ?? "";
      if (status === "completed") return { lifecycle: "completed", toolStepStatus: status };
      if (status === "failed") return { lifecycle: "failed", toolStepStatus: status };
      return { lifecycle: "unmatched", toolStepStatus: status };
    }

    const toolName = (meta?.tool_name as string) ?? (side === "a" ? s.name_a : s.name_b) ?? null;
    if (!tc.id && !callId && toolName && toolName === tc.name) {
      const status = (side === "a" ? s.status_a : s.status_b) ?? "";
      if (status === "completed") return { lifecycle: "completed", toolStepStatus: status };
      if (status === "failed") return { lifecycle: "failed", toolStepStatus: status };
      return { lifecycle: "unmatched", toolStepStatus: status };
    }
  }
  return { lifecycle: "unmatched", toolStepStatus: null };
}

const LIFECYCLE_BADGE_COMPARE: Record<CompareCallLifecycle, { label: string; className: string }> = {
  completed: { label: "completed", className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400" },
  failed: { label: "failed", className: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400" },
  unmatched: { label: "unmatched", className: "bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500" },
};

function ToolCallsDiff({
  summaryA,
  summaryB,
  allSteps,
}: {
  summaryA: Record<string, unknown> | null;
  summaryB: Record<string, unknown> | null;
  allSteps: CompareStepDiff[];
}) {
  const callsA = extractToolCallSummariesFromOutputSummary(summaryA);
  const callsB = extractToolCallSummariesFromOutputSummary(summaryB);
  if (callsA.length === 0 && callsB.length === 0) return null;

  const hasDiff = toolCallsAreDifferent(callsA, callsB);
  const countDiff = callsA.length !== callsB.length;
  const pairs = alignToolCalls(callsA, callsB);
  const bg = hasDiff ? "bg-[var(--tint-diff-row)]" : "bg-amber-50/30 dark:bg-amber-950/10";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Tool calls
        {countDiff && (
          <span className="rounded-full bg-amber-100 px-1.5 py-px text-[9px] font-medium text-amber-600 dark:bg-amber-900/40 dark:text-amber-400">
            {callsA.length} → {callsB.length}
          </span>
        )}
        {hasDiff && <ChangedBadge />}
      </div>
      <div className="space-y-1.5">
        {pairs.map((pair, i) => (
          <AlignedCallRow key={i} pair={pair} allSteps={allSteps} />
        ))}
      </div>
    </div>
  );
}

function AlignedCallRow({ pair, allSteps }: { pair: AlignedCallPair; allSteps: CompareStepDiff[] }) {
  const { a, b } = pair;
  const nameDiff = (a?.name ?? null) !== (b?.name ?? null);
  const idDiff = (a?.id ?? null) !== (b?.id ?? null);
  const argsDiff = a && b && a.arguments_hash !== b.arguments_hash;
  const oneSided = !a || !b;

  const lcA = a ? deriveCompareCallLifecycle(a, "a", allSteps) : null;
  const lcB = b ? deriveCompareCallLifecycle(b, "b", allSteps) : null;
  const lcDiff = (lcA?.lifecycle ?? null) !== (lcB?.lifecycle ?? null);

  return (
    <div className="grid grid-cols-2 gap-0 rounded bg-white/60 px-2 py-1.5 dark:bg-neutral-900/30">
      <div className="pr-4">
        {a ? (
          <CallPill tc={a} diff={nameDiff} idDiff={idDiff} argsDiff={!!argsDiff} lifecycle={lcA?.lifecycle} lcDiff={lcDiff} />
        ) : (
          <span className="text-[10px] italic text-neutral-300">—</span>
        )}
      </div>
      <div className="border-l border-neutral-200 pl-4">
        {b ? (
          <CallPill tc={b} diff={nameDiff} idDiff={idDiff} argsDiff={!!argsDiff} lifecycle={lcB?.lifecycle} lcDiff={lcDiff} />
        ) : (
          <span className="text-[10px] italic text-neutral-300">—</span>
        )}
      </div>
      {oneSided && (
        <div className="col-span-2 mt-0.5">
          <span className="rounded bg-amber-100 px-1 py-px text-[8px] font-medium text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">
            {!a ? "only in B" : "only in A"}
          </span>
        </div>
      )}
    </div>
  );
}

function CallPill({ tc, diff, idDiff, argsDiff, lifecycle, lcDiff }: {
  tc: ToolCallSummary;
  diff: boolean;
  idDiff: boolean;
  argsDiff: boolean;
  lifecycle?: CompareCallLifecycle;
  lcDiff?: boolean;
}) {
  const lcCfg = lifecycle ? LIFECYCLE_BADGE_COMPARE[lifecycle] : null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={`font-mono text-[11px] font-medium ${diff ? "text-amber-600" : "text-neutral-700 dark:text-neutral-300"}`}>
        {tc.name}
      </span>
      {tc.id && (
        <span className={`font-mono text-[9px] ${idDiff ? "text-amber-500" : "text-neutral-400"}`} title={tc.id}>
          {truncateId(tc.id, 16)}
        </span>
      )}
      {argsDiff && (
        <span className="rounded bg-amber-100 px-1 py-px text-[8px] font-medium text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">
          args changed
        </span>
      )}
      {lcCfg && (
        <span className={`rounded px-1 py-px text-[8px] font-medium ${lcDiff ? "ring-1 ring-amber-400/50 " : ""}${lcCfg.className}`}>
          {lcCfg.label}
        </span>
      )}
    </div>
  );
}

// ===========================================================================
// MCP / Capability / Retrieval compare sections
// ===========================================================================

function _metaStr(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}

function _metaNum(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function _isRetrievalOutput(data: Dict | null): boolean {
  return data?.kind === "retrieval";
}

function CompareFieldGrid({
  fields,
  absentA,
  absentB,
}: {
  fields: [string, string | number | null, string | number | null][];
  absentA?: boolean;
  absentB?: boolean;
}) {
  return (
    <div className="space-y-0.5">
      <div className="grid grid-cols-[90px_1fr_1fr] text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span />
        <span>A</span>
        <span>B</span>
      </div>
      {fields.map(([label, a, b]) => {
        const diff = String(a ?? "") !== String(b ?? "");
        return (
          <div key={label} className="grid grid-cols-[90px_1fr_1fr] items-baseline gap-0 text-[11px]">
            <span className="text-neutral-400">{label}</span>
            <span className={`${absentA ? "italic text-neutral-300" : diff ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
              {absentA ? "—" : a != null ? String(a) : "—"}
            </span>
            <span className={`${absentB ? "italic text-neutral-300" : diff ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
              {absentB ? "—" : b != null ? String(b) : "—"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function McpCompareDiff({
  metaA,
  metaB,
  absentA,
  absentB,
}: {
  metaA: Dict | null;
  metaB: Dict | null;
  absentA: boolean;
  absentB: boolean;
}) {
  const isMcpA = !absentA && isMcpMeta(metaA);
  const isMcpB = !absentB && isMcpMeta(metaB);
  if (!isMcpA && !isMcpB) return null;

  const fields: [string, string | null, string | null][] = [
    ["operation", _metaStr(metaA?.operation_kind), _metaStr(metaB?.operation_kind)],
    ["target", _metaStr(metaA?.target_name), _metaStr(metaB?.target_name)],
    ["server", _metaStr(metaA?.server_name), _metaStr(metaB?.server_name)],
    ["server_id", _metaStr(metaA?.server_id), _metaStr(metaB?.server_id)],
    ["transport", _metaStr(metaA?.transport_kind), _metaStr(metaB?.transport_kind)],
  ];

  const visible = fields.filter(([, a, b]) => a != null || b != null);
  if (visible.length === 0 && isMcpA === isMcpB) return null;

  const anyDiff = visible.some(([, a, b]) => a !== b) || isMcpA !== isMcpB;
  const bg = anyDiff ? "bg-[var(--tint-diff-row)]" : "bg-violet-50/30 dark:bg-violet-950/25";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span className={`rounded px-1.5 py-0.5 font-medium ${MCP_BADGE}`}>MCP</span>
        {isMcpA !== isMcpB && (
          <span className="text-[9px] text-neutral-400">{isMcpA ? "A only" : "B only"}</span>
        )}
        {anyDiff && <ChangedBadge />}
      </div>
      {visible.length > 0 && (
        <CompareFieldGrid fields={visible} absentA={absentA} absentB={absentB} />
      )}
    </div>
  );
}

function CapabilityCompareDiff({
  metaA,
  metaB,
  absentA,
  absentB,
}: {
  metaA: Dict | null;
  metaB: Dict | null;
  absentA: boolean;
  absentB: boolean;
}) {
  const capA = absentA ? null : getCapabilityKindFromMeta(metaA);
  const capB = absentB ? null : getCapabilityKindFromMeta(metaB);
  if (!capA && !capB) return null;

  const fields: [string, string | null, string | null][] = [
    ["kind", capA, capB],
    ["name", _metaStr(metaA?.capability_name), _metaStr(metaB?.capability_name)],
    ["label", _metaStr(metaA?.capability_label), _metaStr(metaB?.capability_label)],
    ["namespace", _metaStr(metaA?.capability_namespace), _metaStr(metaB?.capability_namespace)],
    ["skill", _metaStr(metaA?.skill_name), _metaStr(metaB?.skill_name)],
    ["skill_label", _metaStr(metaA?.skill_label), _metaStr(metaB?.skill_label)],
    ["server", _metaStr(metaA?.server_name), _metaStr(metaB?.server_name)],
    ["server_id", _metaStr(metaA?.server_id), _metaStr(metaB?.server_id)],
  ];

  const visible = fields.filter(([, a, b]) => a != null || b != null);
  if (visible.length === 0) return null;

  const anyDiff = visible.some(([, a, b]) => a !== b);
  const badgeCls = CAPABILITY_BADGE[capA ?? capB ?? "unknown"] ?? CAPABILITY_BADGE.unknown;
  const bg = anyDiff ? "bg-[var(--tint-diff-row)]" : "bg-neutral-50/50";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span className={`rounded px-1.5 py-0.5 font-medium ${badgeCls}`}>{capA ?? capB}</span>
        Capability
        {anyDiff && <ChangedBadge />}
      </div>
      <CompareFieldGrid fields={visible} absentA={absentA} absentB={absentB} />
    </div>
  );
}

function RetrievalCompareDiff({
  metaA,
  metaB,
  absentA,
  absentB,
  identityOnly,
}: {
  metaA: Dict | null;
  metaB: Dict | null;
  absentA: boolean;
  absentB: boolean;
  identityOnly?: boolean;
}) {
  const isRetA = !absentA && isRetrievalMeta(metaA);
  const isRetB = !absentB && isRetrievalMeta(metaB);
  if (!isRetA && !isRetB) return null;

  const identity: [string, string | number | null, string | number | null][] = [
    ["stage", _metaStr(metaA?.retrieval_stage), _metaStr(metaB?.retrieval_stage)],
    ["backend", _metaStr(metaA?.retrieval_backend), _metaStr(metaB?.retrieval_backend)],
    ["index", _metaStr(metaA?.index_name), _metaStr(metaB?.index_name)],
    ["query", _metaStr(metaA?.query_text), _metaStr(metaB?.query_text)],
    ["queries", _metaNum(metaA?.query_count), _metaNum(metaB?.query_count)],
  ];

  const counts: [string, string | number | null, string | number | null][] = [
    ["candidates", _metaNum(metaA?.candidate_count), _metaNum(metaB?.candidate_count)],
    ["selected", _metaNum(metaA?.selected_count), _metaNum(metaB?.selected_count)],
    ["tokens", _metaNum(metaA?.context_token_estimate), _metaNum(metaB?.context_token_estimate)],
    ["latency", _metaNum(metaA?.latency_ms), _metaNum(metaB?.latency_ms)],
  ];

  const fields = identityOnly ? identity : [...identity, ...counts];

  const visible = fields.filter(([, a, b]) => a != null || b != null);
  if (visible.length === 0 && isRetA === isRetB) return null;

  const anyDiff = visible.some(([, a, b]) => String(a ?? "") !== String(b ?? "")) || isRetA !== isRetB;
  const bg = anyDiff ? "bg-[var(--tint-diff-row)]" : "bg-teal-50/30 dark:bg-teal-950/25";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span className={`rounded px-1.5 py-0.5 font-medium ${RETRIEVAL_STAGE_BADGE}`}>
          {_metaStr(metaA?.retrieval_stage) ?? _metaStr(metaB?.retrieval_stage) ?? "retrieval"}
        </span>
        Retrieval
        {isRetA !== isRetB && (
          <span className="text-[9px] text-neutral-400">{isRetA ? "A only" : "B only"}</span>
        )}
        {anyDiff && <ChangedBadge />}
      </div>
      {visible.length > 0 && (
        <CompareFieldGrid fields={visible} absentA={absentA} absentB={absentB} />
      )}
    </div>
  );
}

function RetrievalOutputDiff({
  dataA,
  dataB,
  diff,
  absentA,
  absentB,
}: {
  dataA: Dict | null;
  dataB: Dict | null;
  diff: boolean;
  absentA?: boolean;
  absentB?: boolean;
}) {
  const [raw, setRaw] = useState(false);

  const fields: [string, string | number | null, string | number | null][] = [
    ["candidates", _metaNum(dataA?.candidate_count), _metaNum(dataB?.candidate_count)],
    ["selected", _metaNum(dataA?.selected_count), _metaNum(dataB?.selected_count)],
    ["tokens", _metaNum(dataA?.context_token_estimate), _metaNum(dataB?.context_token_estimate)],
    ["latency", _metaNum(dataA?.latency_ms), _metaNum(dataB?.latency_ms)],
    ["query", _metaStr(dataA?.query_text), _metaStr(dataB?.query_text)],
  ];

  const visible = fields.filter(([, a, b]) => a != null || b != null);
  const bg = diff ? "bg-[var(--tint-diff-row)]" : "bg-[var(--tint-output)]";

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span className="flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 font-medium ${RETRIEVAL_STAGE_BADGE}`}>retrieval</span>
          Output
          {diff && <ChangedBadge />}
        </span>
        <button
          onClick={() => setRaw(!raw)}
          className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600"
        >
          {raw ? "Structured" : "Raw"}
        </button>
      </div>
      {raw ? (
        <div className="grid grid-cols-2 gap-0">
          <div className="pr-4">
            <DataCell side="A" data={dataA} raw absent={absentA} />
          </div>
          <div className="border-l border-neutral-200 pl-4">
            <DataCell side="B" data={dataB} raw absent={absentB} />
          </div>
        </div>
      ) : visible.length > 0 ? (
        <CompareFieldGrid fields={visible} absentA={absentA} absentB={absentB} />
      ) : (
        <div className="grid grid-cols-2 gap-0">
          <div className="pr-4">
            <DataCell side="A" data={dataA} raw={false} absent={absentA} />
          </div>
          <div className="border-l border-neutral-200 pl-4">
            <DataCell side="B" data={dataB} raw={false} absent={absentB} />
          </div>
        </div>
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
      {llm.meta?.latency_ms != null && (
        <span className="text-neutral-400">
          latency <span className="font-medium text-neutral-700">{formatDuration(llm.meta.latency_ms)}</span>
        </span>
      )}
      {llm.meta?.finish_reason && (
        <span className="text-neutral-400">
          finish <span className="font-medium text-neutral-700">{llm.meta.finish_reason}</span>
        </span>
      )}
      {llm.usage?.total_tokens != null && (
        <span className="text-neutral-400">
          tokens <span className="font-medium tabular-nums text-neutral-700">{llm.usage.total_tokens.toLocaleString()}</span>
        </span>
      )}
    </div>
  );
}

function LlmInputDiff({ a, b }: { a: LLMShape | null; b: LLMShape | null }) {
  const hasA = !!(a && (a.input?.system || (a.input?.messages?.length ?? 0) > 0));
  const hasB = !!(b && (b.input?.system || (b.input?.messages?.length ?? 0) > 0));
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

function extractMediaBlocks(msg: Record<string, unknown>): Record<string, unknown>[] {
  const c = msg.content;
  if (!Array.isArray(c)) return [];
  return c.filter((block) => {
    if (!block || typeof block !== "object") return false;
    const b = block as Record<string, unknown>;
    const t = b.type as string | undefined;
    return t && t !== "text" && t !== "input_text";
  }) as Record<string, unknown>[];
}

function InputMessages({ llm }: { llm: LLMShape | null }) {
  const messages = llm?.input?.messages ?? [];
  const tools = llm?.input?.tools ?? [];
  if (!llm || (!llm.input?.system && messages.length === 0)) {
    return <p className="text-xs italic text-neutral-400">No prompt</p>;
  }

  return (
    <div className="space-y-2.5">
      {llm.input?.system && (
        <div>
          <span className={`text-[10px] font-medium ${ROLE_STYLES.system}`}>system</span>
          <pre className="mt-0.5 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
            {llm.input.system}
          </pre>
        </div>
      )}
      {messages.map((msg, i) => {
        const role = (msg.role as string) ?? "unknown";
        const content = extractMessageContent(msg);
        const media = extractMediaBlocks(msg);
        const color = ROLE_STYLES[role] ?? "text-neutral-400";
        return (
          <div key={i}>
            <span className={`text-[10px] font-medium ${color}`}>{role}</span>
            {media.length > 0 && (
              <div className="mt-0.5 flex flex-wrap gap-1">
                {media.map((b, j) => (
                  <CompareMediaBadge key={j} block={b} />
                ))}
              </div>
            )}
            <pre className="mt-0.5 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
              {content || "(empty)"}
            </pre>
          </div>
        );
      })}
      {tools.length > 0 && (
        <div>
          <span className="text-[10px] font-medium text-neutral-400">tools</span>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {tools.map((t, i) => (
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

function isMediaBlock(b: Record<string, unknown>): boolean {
  const t = b.type as string | undefined;
  return !!t && t !== "text" && t !== "thinking" && t !== "redacted_thinking" && t !== "tool_call";
}

function OutputContent({ llm }: { llm: LLMShape | null }) {
  const contentBlocks = llm?.output?.content_blocks ?? [];
  const toolCalls = llm?.output?.tool_calls ?? [];
  const hasMedia = contentBlocks.some(isMediaBlock);
  if (!llm || (!llm.output?.text && toolCalls.length === 0 && !hasMedia)) {
    return <p className="text-xs italic text-neutral-400">No output</p>;
  }

  const structuredText = llm.output?.text ? tryParseJson(llm.output.text) : null;

  const mediaBlocks = contentBlocks.filter(isMediaBlock);

  return (
    <div className="space-y-2">
      {llm.output?.text &&
        (structuredText != null ? (
          <StructuredValue value={structuredText} />
        ) : (
          <ExpandableTextBlock text={llm.output.text} />
        ))}
      {mediaBlocks.length > 0 && (
        <div className="space-y-1">
          {mediaBlocks.map((b, i) => (
            <CompareMediaBadge key={i} block={b} />
          ))}
        </div>
      )}
      {toolCalls.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[10px] font-medium text-neutral-400">Tool calls</span>
          {toolCalls.map((tc, i) => {
            const args = resolveArgs(tc.arguments);
            return (
              <div key={i} className="rounded bg-neutral-50 px-2 py-1.5">
                <span className="font-mono text-[11px] font-medium text-neutral-700">
                  {toolCallLabel(tc)}
                </span>
                {args != null && (
                  <div className="mt-1">
                    <StructuredValue value={args} defaultExpanded={false} />
                  </div>
                )}
              </div>
            );
          })}
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
    (uB?.prompt_tokens ?? uB?.completion_tokens ?? uB?.total_tokens) != null ||
    getCachedTokens(uA) != null ||
    getCachedTokens(uB) != null;
  if (!hasAny) return null;

  const diff =
    uA?.prompt_tokens !== uB?.prompt_tokens ||
    uA?.completion_tokens !== uB?.completion_tokens ||
    uA?.total_tokens !== uB?.total_tokens ||
    getCachedTokens(uA) !== getCachedTokens(uB);
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
  const cached = getCachedTokens(usage);
  if (cached != null) items.push({ label: "cached", value: cached });
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
// Latency breakdown diff
// ===========================================================================

function latencyFmtRate(v: number | null, unit: string): string | null {
  if (v === null) return null;
  return v >= 100 ? `${Math.round(v)} ${unit}` : `${v.toFixed(1)} ${unit}`;
}

type LatencyMetricRow = {
  id: string;
  label: string;
  valueA: string | null;
  valueB: string | null;
  diff: boolean;
};

function latencyMetricDiff(a: number | null, b: number | null): boolean {
  if (a === null && b === null) return false;
  if (a === null || b === null) return true;
  return Math.round(a) !== Math.round(b);
}

function buildLatencyRows(a: LatencyBreakdown, b: LatencyBreakdown): LatencyMetricRow[] {
  const rows: LatencyMetricRow[] = [];

  const pushMs = (id: string, label: string, vA: number | null, vB: number | null) => {
    if (vA === null && vB === null) return;
    rows.push({
      id,
      label,
      valueA: vA !== null ? formatDuration(vA) : null,
      valueB: vB !== null ? formatDuration(vB) : null,
      diff: latencyMetricDiff(vA, vB),
    });
  };

  pushMs("total", "Total", a.total_ms, b.total_ms);
  pushMs("ttfc", "TTFC", a.ttfc_ms, b.ttfc_ms);
  pushMs("gen", "Generation", a.generation_ms, b.generation_ms);

  const cpsA = latencyFmtRate(a.chars_per_sec, "chars/s");
  const cpsB = latencyFmtRate(b.chars_per_sec, "chars/s");
  if (cpsA || cpsB) {
    rows.push({
      id: "cps",
      label: "Chars/s",
      valueA: cpsA,
      valueB: cpsB,
      diff: cpsA !== cpsB,
    });
  }

  const tpsA = latencyFmtRate(a.tokens_per_sec, "tok/s");
  const tpsB = latencyFmtRate(b.tokens_per_sec, "tok/s");
  if (tpsA || tpsB) {
    rows.push({
      id: "tps",
      label: "Tok/s",
      valueA: tpsA,
      valueB: tpsB,
      diff: tpsA !== tpsB,
    });
  }

  if ((a.overhead_ms != null && a.overhead_ms > 0) || (b.overhead_ms != null && b.overhead_ms > 0)) {
    pushMs("overhead", "Overhead", a.overhead_ms, b.overhead_ms);
  }

  if (a.termination || b.termination) {
    const termDiff = a.termination !== b.termination;
    rows.push({
      id: "term",
      label: "Termination",
      valueA: a.termination,
      valueB: b.termination,
      diff: termDiff,
    });
  }

  if (a.truncated_chunks || b.truncated_chunks) {
    const truncDiff = a.truncated_chunks !== b.truncated_chunks;
    rows.push({
      id: "trunc",
      label: "Truncated",
      valueA: a.truncated_chunks ? "yes" : "no",
      valueB: b.truncated_chunks ? "yes" : "no",
      diff: truncDiff,
    });
  }

  return rows;
}

function LlmLatencyDiff({
  llmA,
  llmB,
  durationMsA,
  durationMsB,
  metaA,
  metaB,
}: {
  llmA: LLMShape | null;
  llmB: LLMShape | null;
  durationMsA: number | null;
  durationMsB: number | null;
  metaA: Dict | null;
  metaB: Dict | null;
}) {
  const streamMetaA = streamVal(metaA);
  const streamMetaB = streamVal(metaB);

  const breakdownA = useMemo(
    () => computeLatencyBreakdown({
      durationMs: durationMsA ?? llmA?.meta?.latency_ms,
      streamMeta: streamMetaA,
      usage: llmA?.usage,
    }),
    [durationMsA, llmA, streamMetaA],
  );

  const breakdownB = useMemo(
    () => computeLatencyBreakdown({
      durationMs: durationMsB ?? llmB?.meta?.latency_ms,
      streamMeta: streamMetaB,
      usage: llmB?.usage,
    }),
    [durationMsB, llmB, streamMetaB],
  );

  if (!breakdownA.is_available && !breakdownB.is_available) return null;

  const rows = buildLatencyRows(breakdownA, breakdownB);
  const anyDiff = breakdownA.is_available !== breakdownB.is_available || rows.some((r) => r.diff);
  const bg = anyDiff ? "bg-[var(--tint-diff-row)]" : "bg-violet-50/30 dark:bg-violet-950/25";

  const oneSided = breakdownA.is_available !== breakdownB.is_available;

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Latency
        {anyDiff && <ChangedBadge />}
      </div>

      {oneSided && (
        <div className="mb-2.5 flex items-center gap-2 rounded bg-violet-50 px-3 py-1.5 text-[11px] text-violet-600 dark:bg-violet-950/20 dark:text-violet-400">
          <span className="font-medium">{breakdownA.is_available ? "A only" : "B only"}</span>
          <span className="text-violet-400">·</span>
          <span>{breakdownA.is_available ? "B is non-streaming" : "A is non-streaming"}</span>
        </div>
      )}

      {rows.length > 0 && (
        <div className="space-y-0.5">
          <div className="grid grid-cols-[90px_1fr_1fr] text-[10px] font-medium uppercase tracking-wider text-neutral-400">
            <span />
            <span>A</span>
            <span>B</span>
          </div>
          {rows.map((r) => (
            <div key={r.id} className="grid grid-cols-[90px_1fr_1fr] items-baseline gap-0 text-[11px]">
              <span className="text-neutral-400">{r.label}</span>
              <span className={`tabular-nums ${r.diff ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
                {r.valueA ?? "—"}
              </span>
              <span className={`tabular-nums ${r.diff ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
                {r.valueB ?? "—"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// Stream diff
// ===========================================================================

function streamVal(meta: Dict | null | undefined): Dict | null {
  if (!meta) return null;
  const s = meta.stream;
  if (typeof s === "object" && s != null && (s as Dict).is_stream === true) return s as Dict;
  return null;
}

function pctDiff(a: number, b: number): number {
  const avg = (a + b) / 2;
  return avg === 0 ? 0 : Math.abs(a - b) / avg;
}

function StreamStatLine({ label, a, b, format, threshold = 0.2 }: {
  label: string;
  a: number | null;
  b: number | null;
  format: (v: number) => string;
  threshold?: number;
}) {
  const bothPresent = a != null && b != null;
  const diff = bothPresent && pctDiff(a, b) > threshold;

  return (
    <div className="grid grid-cols-[80px_1fr_1fr] items-baseline gap-0 text-[11px]">
      <span className="text-neutral-400">{label}</span>
      <span className={`tabular-nums ${diff ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
        {a != null ? format(a) : "—"}
      </span>
      <span className={`tabular-nums ${diff ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
        {b != null ? format(b) : "—"}
      </span>
    </div>
  );
}

interface StreamExtract {
  events: Dict[] | undefined;
  blobArtifactId: string | undefined;
}

function extractStreamEvents(steps: TimelineStep[], seqIdx: number | null, stepName: string | null): StreamExtract {
  const match = steps.find((s) => {
    if (seqIdx != null && s.sequence_index === seqIdx) return true;
    if (stepName && s.name === stepName && s.step_type === "llm") return true;
    return false;
  });
  if (!match) return { events: undefined, blobArtifactId: undefined };
  const art = match.artifacts.find((a) => a.kind === "llm_stream");
  if (!art) return { events: undefined, blobArtifactId: undefined };

  if (art.inline_data) {
    const evts = art.inline_data.events;
    return {
      events: Array.isArray(evts) ? (evts as Dict[]) : undefined,
      blobArtifactId: undefined,
    };
  }

  if (art.storage_kind === "blob") {
    return { events: undefined, blobArtifactId: art.id };
  }

  return { events: undefined, blobArtifactId: undefined };
}

function LlmStreamDiff({
  metaA,
  metaB,
  runIdA,
  runIdB,
  seqIdxA,
  seqIdxB,
  stepNameA,
  stepNameB,
}: {
  metaA: Dict | null;
  metaB: Dict | null;
  runIdA: string;
  runIdB: string;
  seqIdxA: number | null;
  seqIdxB: number | null;
  stepNameA: string | null;
  stepNameB: string | null;
}) {
  const [playbackSide, setPlaybackSide] = useState<"a" | "b" | null>(null);
  const [eventsA, setEventsA] = useState<Dict[] | undefined>(undefined);
  const [eventsB, setEventsB] = useState<Dict[] | undefined>(undefined);
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [fetchErrorA, setFetchErrorA] = useState<string | null>(null);
  const [fetchErrorB, setFetchErrorB] = useState<string | null>(null);
  const fetchedRef = useRef<{ a?: boolean; b?: boolean }>({});

  const fetchEvents = useCallback(
    async (side: "a" | "b") => {
      if (fetchedRef.current[side]) return;
      fetchedRef.current[side] = true;
      const setLoading = side === "a" ? setLoadingA : setLoadingB;
      const setError = side === "a" ? setFetchErrorA : setFetchErrorB;
      setLoading(true);
      setError(null);
      try {
        const runId = side === "a" ? runIdA : runIdB;
        const data = await apiFetch<TimelineResponse>(`/v1/runs/${runId}/timeline`);
        const seqIdx = side === "a" ? seqIdxA : seqIdxB;
        const name = side === "a" ? stepNameA : stepNameB;
        const extract = extractStreamEvents(data.steps, seqIdx, name);

        let evts = extract.events;

        if (!evts && extract.blobArtifactId) {
          const artResp = await fetchArtifactContent(extract.blobArtifactId);
          const blobEvts = artResp.data?.events;
          evts = Array.isArray(blobEvts) ? (blobEvts as Dict[]) : [];
        }

        if (side === "a") setEventsA(evts);
        else setEventsB(evts);
      } catch (err) {
        fetchedRef.current[side] = false;
        setError(err instanceof Error ? err.message : "Failed to load stream events");
      } finally {
        setLoading(false);
      }
    },
    [runIdA, runIdB, seqIdxA, seqIdxB, stepNameA, stepNameB],
  );

  const handlePlayback = useCallback(
    (side: "a" | "b") => {
      setPlaybackSide(side);
      fetchEvents(side);
    },
    [fetchEvents],
  );

  const sA = streamVal(metaA);
  const sB = streamVal(metaB);
  if (!sA && !sB) return null;

  const chunkA = typeof sA?.chunk_count === "number" ? sA.chunk_count as number : null;
  const chunkB = typeof sB?.chunk_count === "number" ? sB.chunk_count as number : null;
  const durA = typeof sA?.stream_duration_ms === "number" ? sA.stream_duration_ms as number : null;
  const durB = typeof sB?.stream_duration_ms === "number" ? sB.stream_duration_ms as number : null;
  const ttfcA = typeof sA?.time_to_first_chunk_ms === "number" ? sA.time_to_first_chunk_ms as number : null;
  const ttfcB = typeof sB?.time_to_first_chunk_ms === "number" ? sB.time_to_first_chunk_ms as number : null;
  const termA = typeof sA?.termination === "string" ? sA.termination as string : null;
  const termB = typeof sB?.termination === "string" ? sB.termination as string : null;

  const anyDiff =
    (chunkA != null && chunkB != null && pctDiff(chunkA, chunkB) > 0.2) ||
    (durA != null && durB != null && pctDiff(durA, durB) > 0.2) ||
    (ttfcA != null && ttfcB != null && pctDiff(ttfcA, ttfcB) > 0.2) ||
    termA !== termB;

  const bg = anyDiff ? "bg-[var(--tint-diff-row)]" : "bg-violet-50/30 dark:bg-violet-950/25";
  const bothStream = !!sA && !!sB;
  const oneSided = (!!sA) !== (!!sB);

  const fmtN = (v: number) => String(v);
  const fmtMs = (v: number) => formatDuration(v);

  const activeEvents = playbackSide === "a" ? eventsA : playbackSide === "b" ? eventsB : undefined;
  const activeMeta = (playbackSide === "a" ? sA : sB) ?? {};
  const activeLoading = playbackSide === "a" ? loadingA : loadingB;
  const activeError = playbackSide === "a" ? fetchErrorA : fetchErrorB;

  // Compact delta summary (only when both sides stream)
  const deltaHints: string[] = [];
  if (bothStream) {
    if (ttfcA != null && ttfcB != null) {
      const d = ttfcB - ttfcA;
      deltaHints.push(d === 0 ? "same TTFC" : `TTFC ${d > 0 ? "+" : ""}${d}ms`);
    }
    if (durA != null && durB != null) {
      const d = durB - durA;
      deltaHints.push(d === 0 ? "same duration" : `duration ${d > 0 ? "+" : ""}${d}ms`);
    }
    if (chunkA != null && chunkB != null) {
      deltaHints.push(chunkA === chunkB ? "same chunks" : `chunks ${chunkB - chunkA > 0 ? "+" : ""}${chunkB - chunkA}`);
    }
  }

  return (
    <div className={`rounded-md px-4 py-3 ${bg}`}>
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        <span className="flex items-center gap-2">
          Stream
          {anyDiff && <ChangedBadge />}
        </span>
        {bothStream && (
          <button
            onClick={() => {
              if (playbackSide) {
                setPlaybackSide(null);
              } else {
                handlePlayback("a");
              }
            }}
            className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium text-violet-500 transition-colors hover:bg-violet-100 dark:text-violet-400 dark:hover:bg-violet-950/30"
          >
            {playbackSide ? "Hide playback" : "Compare playback"}
          </button>
        )}
      </div>

      {/* One-sided streaming callout */}
      {oneSided && (
        <div className="mb-2.5 flex items-center gap-2 rounded bg-violet-50 px-3 py-1.5 text-[11px] text-violet-600 dark:bg-violet-950/20 dark:text-violet-400">
          <span className="font-medium">{sA ? "A streams" : "B streams"}</span>
          <span className="text-violet-400">·</span>
          <span>{sA ? "B is non-streaming" : "A is non-streaming"}</span>
        </div>
      )}

      {/* Stats comparison */}
      {bothStream && (
        <div className="space-y-1">
          <div className="grid grid-cols-[80px_1fr_1fr] text-[10px] font-medium uppercase tracking-wider text-neutral-400">
            <span />
            <span>A</span>
            <span>B</span>
          </div>
          <StreamStatLine label="chunks" a={chunkA} b={chunkB} format={fmtN} />
          <StreamStatLine label="duration" a={durA} b={durB} format={fmtMs} />
          <StreamStatLine label="TTFC" a={ttfcA} b={ttfcB} format={fmtMs} />
          {(termA || termB) && (
            <div className="grid grid-cols-[80px_1fr_1fr] items-baseline gap-0 text-[11px]">
              <span className="text-neutral-400">termination</span>
              <span className={`${termA !== termB ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
                {termA ?? "—"}
              </span>
              <span className={`${termA !== termB ? "font-medium text-[var(--diff-badge-text)]" : "text-neutral-700"}`}>
                {termB ?? "—"}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Compact delta summary */}
      {deltaHints.length > 0 && (
        <div className="mt-1.5 text-[10px] text-neutral-400">
          {deltaHints.join(" · ")}
        </div>
      )}

      {/* Playback toggle */}
      {playbackSide && (
        <div className="mt-3 border-t border-neutral-100 pt-3">
          <div className="mb-2 flex items-center gap-2">
            <button
              onClick={() => handlePlayback("a")}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                playbackSide === "a" ? "bg-neutral-900 text-white" : "text-neutral-500 hover:bg-neutral-100"
              }`}
            >
              Run A
            </button>
            <button
              onClick={() => handlePlayback("b")}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                playbackSide === "b" ? "bg-neutral-900 text-white" : "text-neutral-500 hover:bg-neutral-100"
              }`}
            >
              Run B
            </button>
            {activeLoading && (
              <span className="text-[10px] italic text-neutral-400">Loading events…</span>
            )}
          </div>
          {activeError ? (
            <div className="space-y-2 px-1 py-2">
              <p className="text-xs text-red-500">{activeError}</p>
              <button
                onClick={() => {
                  if (!playbackSide) return;
                  fetchedRef.current[playbackSide] = false;
                  fetchEvents(playbackSide);
                }}
                className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50 hover:text-neutral-700"
              >
                Retry
              </button>
            </div>
          ) : (
            <StreamSection
              meta={activeMeta}
              events={activeEvents}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// Insight block
// ===========================================================================

function computeInsight(data: CompareResponse): string | null {
  const { run_diff, steps } = data;

  const outputSame = !run_diff.output_diff;
  const durA = data.run_a.total_duration_ms;
  const durB = data.run_b.total_duration_ms;
  const hasDurationDiff = durA != null && durB != null && pctDiff(durA, durB) > 0.2;

  if (outputSame && hasDurationDiff) {
    return "Same output but different latency — the runs produced identical results at different speeds.";
  }

  let streamDiffFound = false;
  let tokenDiffFound = false;
  let cachedTokenDiffFound = false;
  let refusalDiffFound = false;
  let jsonOutputDiffFound = false;
  let toolCallCountDiff = false;
  let toolFailureDiff = false;
  let retrievalCountDiff = false;
  let retrievalBackendDiff = false;
  let mcpServerDiff = false;

  for (const step of steps) {
    if (refusalCompareState(step.llm_a, step.llm_b).diverges) refusalDiffFound = true;
    if (cachedTokensDiverges(step.llm_a?.usage, step.llm_b?.usage)) cachedTokenDiffFound = true;
    if (jsonOutputDiverges(step.llm_a, step.llm_b)) jsonOutputDiffFound = true;

    const sA = streamVal(step.metadata_a);
    const sB = streamVal(step.metadata_b);
    if (sA && sB) {
      const cA = typeof sA.chunk_count === "number" ? sA.chunk_count : 0;
      const cB = typeof sB.chunk_count === "number" ? sB.chunk_count : 0;
      if (pctDiff(cA, cB) > 0.2) streamDiffFound = true;
    }

    const uA = step.llm_a?.usage;
    const uB = step.llm_b?.usage;
    if (uA?.total_tokens != null && uB?.total_tokens != null && uA.total_tokens !== uB.total_tokens) {
      tokenDiffFound = true;
    }

    const tcA = extractToolCallSummariesFromOutputSummary(step.output_summary_a);
    const tcB = extractToolCallSummariesFromOutputSummary(step.output_summary_b);
    if (tcA.length !== tcB.length && (tcA.length > 0 || tcB.length > 0)) {
      toolCallCountDiff = true;
    }

    const isTool = (step.step_type_a ?? step.step_type_b) === "tool";
    if (isTool) {
      const stA = step.status_a ?? "";
      const stB = step.status_b ?? "";
      if ((stA === "failed") !== (stB === "failed")) toolFailureDiff = true;
    }

    const mA = step.metadata_a;
    const mB = step.metadata_b;

    if (isRetrievalMeta(mA) && isRetrievalMeta(mB)) {
      const candA = _metaNum(mA?.candidate_count);
      const candB = _metaNum(mB?.candidate_count);
      const selA = _metaNum(mA?.selected_count);
      const selB = _metaNum(mB?.selected_count);
      if ((candA != null && candB != null && candA !== candB) || (selA != null && selB != null && selA !== selB)) {
        retrievalCountDiff = true;
      }
      const beA = _metaStr(mA?.retrieval_backend);
      const beB = _metaStr(mB?.retrieval_backend);
      const ixA = _metaStr(mA?.index_name);
      const ixB = _metaStr(mB?.index_name);
      if ((beA && beB && beA !== beB) || (ixA && ixB && ixA !== ixB)) {
        retrievalBackendDiff = true;
      }
    }

    if (isMcpMeta(mA) && isMcpMeta(mB)) {
      const srvA = _metaStr(mA?.server_name);
      const srvB = _metaStr(mB?.server_name);
      const opA = _metaStr(mA?.operation_kind);
      const opB = _metaStr(mB?.operation_kind);
      if ((srvA && srvB && srvA !== srvB) || (opA && opB && opA !== opB)) {
        mcpServerDiff = true;
      }
    }
  }

  if (refusalDiffFound) {
    return "Refusal divergence — the model refused in one run but not the other.";
  }

  if (toolFailureDiff) {
    return "Tool execution divergence — a tool step failed in one run but not the other.";
  }

  if (mcpServerDiff) {
    return "MCP server divergence — an MCP step targeted a different server or operation across runs.";
  }

  if (retrievalBackendDiff) {
    return "Retrieval backend divergence — retrieval used a different backend or index across runs.";
  }

  if (retrievalCountDiff) {
    return "Retrieval count divergence — candidate or selected counts differ between the runs.";
  }

  if (toolCallCountDiff) {
    return "Different tool call count — the LLM emitted a different number of tool calls across runs.";
  }

  if (jsonOutputDiffFound) {
    return "Structured-output divergence — one run returned a JSON object/array while the other did not.";
  }

  if (streamDiffFound) {
    return "Different streaming behavior — chunk counts diverge significantly between the runs.";
  }

  if (tokenDiffFound) {
    return "Different token usage — the runs consumed different amounts of tokens.";
  }

  if (cachedTokenDiffFound) {
    return "Different prompt-cache usage — cache-read token counts diverge between the runs.";
  }

  return null;
}

function InsightBlock({ data }: { data: CompareResponse }) {
  const insight = useMemo(() => computeInsight(data), [data]);
  if (!insight) return null;

  return (
    <div className="mb-6 flex items-start gap-2.5 rounded-lg bg-violet-50/60 px-4 py-3 dark:bg-violet-950/20">
      <Lightbulb size={13} className="mt-0.5 shrink-0 text-violet-400" />
      <div>
        <span className="text-[10px] font-medium uppercase tracking-wider text-violet-400">Insight</span>
        <p className="mt-0.5 text-[11px] leading-relaxed text-neutral-600 dark:text-neutral-400">{insight}</p>
      </div>
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
  children,
}: {
  label: string;
  diff: boolean;
  children: [React.ReactNode, React.ReactNode];
}) {
  const bg = diff ? "bg-[var(--tint-diff-row)]" : "bg-neutral-50/50";

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
  isError,
}: {
  label: string;
  diff: boolean;
  dataA: Dict | null;
  dataB: Dict | null;
  absentA?: boolean;
  absentB?: boolean;
  isError?: boolean;
}) {
  const [raw, setRaw] = useState(false);
  const hasAny = dataA != null || dataB != null;
  const bg = diff
    ? isError
      ? "bg-[var(--tint-diff-error-row)]"
      : "bg-[var(--tint-diff-row)]"
    : "bg-neutral-50/50";

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
        <p className="text-xs italic text-neutral-400">—</p>
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
