"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import {
  formatDuration,
  formatSummary,
  statusClass,
  timeAgo,
} from "@/lib/format";
import type { ProjectRunsResponse, RunListItem } from "@/lib/types";

export default function HomePage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<ProjectRunsResponse>("/v1/projects/demo-project/runs")
      .then((data) => setRuns(data.runs))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p className="py-12 text-center text-sm text-neutral-400">Loading runs…</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Failed to load runs: {error}
      </div>
    );
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-lg font-semibold tracking-tight text-neutral-900">Runs</h1>
        <p className="mt-0.5 text-xs text-neutral-400">Recent agent executions</p>
      </div>

      {runs.length === 0 ? (
        <p className="text-sm text-neutral-400">No runs yet. Run the demo agent to create one.</p>
      ) : (
        <div className="space-y-2">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}
    </div>
  );
}

function RunCard({ run }: { run: RunListItem }) {
  const failed = run.status === "failed";
  const preview = formatSummary(run.output_summary, 120);
  const accent = failed ? "bg-red-300 group-hover:bg-red-600" : "bg-neutral-300 group-hover:bg-neutral-900";

  return (
    <Link
      href={`/runs/${run.id}`}
      className="group flex cursor-pointer items-stretch rounded-lg transition-all duration-100 hover:bg-neutral-50 hover:shadow-[0_1px_4px_rgba(0,0,0,0.04)]"
    >
      {/* Left accent bar */}
      <div className={`w-[3px] shrink-0 rounded-l-lg transition-colors duration-100 ${accent}`} />

      <div className="flex-1 px-4 py-3.5">
        {/* Line 1: name + status + time */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <span className="truncate text-[13px] font-semibold text-neutral-900">
              {run.workflow_name}
            </span>
            <span
              className={`shrink-0 rounded-full px-2 py-[1px] text-[10px] font-medium leading-4 ${statusClass(run.status)}`}
            >
              {run.status}
            </span>
          </div>
          <span className="shrink-0 text-[11px] text-neutral-400">
            {timeAgo(run.created_at)}
          </span>
        </div>

        {/* Line 2: metadata */}
        <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-neutral-400">
          <span>{run.total_steps} steps</span>
          <span className="text-neutral-300">·</span>
          <span>{formatDuration(run.total_duration_ms)}</span>
          <span className="text-neutral-300">·</span>
          <span className="font-mono text-[10px]">{run.id.slice(0, 8)}</span>
        </div>

        {/* Line 3: preview (max 2 lines via CSS clamp) */}
        {preview && (
          <p className="mt-2 line-clamp-2 font-mono text-[11px] leading-[18px] text-neutral-500">
            {preview}
          </p>
        )}
      </div>
    </Link>
  );
}
