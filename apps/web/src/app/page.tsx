"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatDate, formatDuration, previewLines, statusClass } from "@/lib/format";
import type { ProjectRunsResponse, RunListItem } from "@/lib/types";

export default function HomePage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [projectName, setProjectName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<ProjectRunsResponse>("/v1/projects/demo-project/runs")
      .then((data) => {
        setProjectName(data.project.name);
        setRuns(data.runs);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p className="text-neutral-500">Loading runs…</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Failed to load runs: {error}
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-8 text-2xl font-semibold">{projectName}</h1>

      {runs.length === 0 ? (
        <p className="text-neutral-500">No runs yet. Run the demo agent to create one.</p>
      ) : (
        <div className="space-y-4">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}
    </div>
  );
}

function RunCard({ run }: { run: RunListItem }) {
  const lines = previewLines(run.output_summary, 3);

  return (
    <Link
      href={`/runs/${run.id}`}
      className="block rounded-lg border border-neutral-200 px-5 py-4 transition-all hover:border-neutral-400 hover:bg-white hover:shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-base font-semibold">{run.workflow_name}</span>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusClass(run.status)}`}
          >
            {run.status}
          </span>
        </div>
        <span className="text-sm text-neutral-500">
          {formatDate(run.created_at)}
        </span>
      </div>

      <div className="mt-2 flex items-center gap-5 text-sm text-neutral-500">
        <span>{run.total_steps} steps</span>
        <span>{formatDuration(run.total_duration_ms)}</span>
        <span className="font-mono text-xs text-neutral-400">
          {run.id.slice(0, 8)}
        </span>
      </div>

      {lines.length > 0 && (
        <div className="mt-3 rounded bg-neutral-100 px-3 py-2">
          {lines.map((line, i) => (
            <p key={i} className="font-mono text-xs leading-relaxed text-neutral-600">
              {line}
            </p>
          ))}
        </div>
      )}
    </Link>
  );
}
