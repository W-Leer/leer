"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import {
  formatDuration,
  formatSummary,
  statusClass,
  timeAgo,
} from "@/lib/format";
import type { ProjectRunsResponse, RunListItem } from "@/lib/types";

type StatusFilter = "all" | "completed" | "failed";
type SortOrder = "newest" | "oldest";

export default function HomePage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortOrder>("newest");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    apiFetch<ProjectRunsResponse>("/v1/projects/demo-project/runs")
      .then((data) => setRuns(data.runs))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    let result = runs;

    if (statusFilter !== "all") {
      result = result.filter((r) => r.status === statusFilter);
    }

    if (q) {
      result = result.filter((r) => {
        const preview = formatSummary(r.output_summary, 200).toLowerCase();
        return (
          r.workflow_name.toLowerCase().includes(q) ||
          r.status.toLowerCase().includes(q) ||
          r.id.toLowerCase().includes(q) ||
          preview.includes(q)
        );
      });
    }

    if (sort === "oldest") {
      result = [...result].reverse();
    }

    return result;
  }, [runs, query, statusFilter, sort]);

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

      {/* Controls */}
      <div className="mb-4 flex items-center gap-2">
        <div className="relative flex-1">
          <input
            ref={searchRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search runs…"
            className="w-full rounded-md bg-neutral-50 py-1.5 pl-3 pr-8 text-sm text-neutral-800 placeholder:text-neutral-400 focus:bg-white focus:shadow-[0_1px_4px_rgba(0,0,0,0.05)] focus:outline-none"
          />
          <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded bg-neutral-200/70 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400">
            /
          </kbd>
        </div>

        <Select value={statusFilter} onChange={(v) => setStatusFilter(v as StatusFilter)}>
          <option value="all">All</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </Select>

        <Select value={sort} onChange={(v) => setSort(v as SortOrder)}>
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
        </Select>
      </div>

      {/* Results */}
      {runs.length === 0 ? (
        <p className="text-sm text-neutral-400">No runs yet. Run the demo agent to create one.</p>
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-neutral-400">No runs match your filters.</p>
      ) : (
        <div className="space-y-2">
          {filtered.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}
    </div>
  );
}

function Select({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="appearance-none rounded-md bg-neutral-50 px-3 py-1.5 text-xs font-medium text-neutral-600 hover:bg-neutral-100 focus:outline-none"
    >
      {children}
    </select>
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
