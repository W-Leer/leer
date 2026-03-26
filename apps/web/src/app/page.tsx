"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import {
  formatDuration,
  formatSummary,
  statusClass,
  timeAgo,
} from "@/lib/format";
import type { ProjectRunsResponse, RunListItem } from "@/lib/types";

type StatusFilter = "" | "completed" | "failed";
type SortOrder = "newest" | "oldest";
const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "", label: "All" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
];

export default function HomePage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [sort, setSort] = useState<SortOrder>("newest");
  const searchRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const fetchRuns = useCallback(
    async (q: string, status: StatusFilter, sortOrder: SortOrder, offset: number, append: boolean) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (status) params.set("status", status);
      params.set("sort", sortOrder);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));

      const data = await apiFetch<ProjectRunsResponse>(
        `/v1/projects/demo-project/runs?${params}`,
      );

      setRuns((prev) => (append ? [...prev, ...data.runs] : data.runs));
      setTotalCount(data.total_count);
      setHasMore(data.has_more);
    },
    [],
  );

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchRuns(query, statusFilter, sort, 0, false)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, sort]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      setError(null);
      fetchRuns(query, statusFilter, sort, 0, false)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(debounceRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

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

  function loadMore() {
    setLoadingMore(true);
    fetchRuns(query, statusFilter, sort, runs.length, true)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingMore(false));
  }

  return (
    <div className="mx-auto max-w-2xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-[17px] font-semibold tracking-tight text-neutral-900">Runs</h1>
        <p className="mt-1 text-[12px] text-neutral-400">Recent agent executions</p>
      </div>

      {/* Control bar */}
      <div className="mb-6 flex items-center gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <svg className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <input
            ref={searchRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search runs…"
            className="w-full rounded-lg bg-neutral-50/80 py-2 pl-9 pr-9 text-[13px] text-neutral-800 placeholder:text-neutral-400 transition-all focus:bg-white focus:shadow-[0_0_0_1px_rgba(0,0,0,0.08),0_2px_6px_rgba(0,0,0,0.04)] focus:outline-none"
          />
          <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-neutral-200 bg-white px-1.5 py-0.5 font-mono text-[10px] leading-none text-neutral-400">
            /
          </kbd>
        </div>

        {/* Divider */}
        <div className="h-5 w-px bg-neutral-200" />

        {/* Status pills */}
        <div className="flex rounded-lg bg-neutral-100/70 p-0.5">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStatusFilter(opt.value)}
              className={`rounded-md px-3 py-1 text-[11px] font-medium transition-all ${
                statusFilter === opt.value
                  ? "bg-white text-neutral-900 shadow-[0_1px_2px_rgba(0,0,0,0.06)]"
                  : "text-neutral-500 hover:text-neutral-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Sort pills */}
        <div className="flex rounded-lg bg-neutral-100/70 p-0.5">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setSort(opt.value)}
              className={`rounded-md px-3 py-1 text-[11px] font-medium transition-all ${
                sort === opt.value
                  ? "bg-white text-neutral-900 shadow-[0_1px_2px_rgba(0,0,0,0.06)]"
                  : "text-neutral-500 hover:text-neutral-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Count bar */}
      {!loading && !error && (
        <div className="mb-4 flex items-center justify-between">
          <p className="text-[11px] text-neutral-400">
            {totalCount} {totalCount === 1 ? "run" : "runs"}
            {(query || statusFilter) ? " matched" : ""}
          </p>
        </div>
      )}

      {/* Results */}
      {loading ? (
        <div className="space-y-2 py-4">
          {[...Array(4)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg bg-red-50 p-5 text-center text-sm text-red-600">
          Failed to load runs: {error}
        </div>
      ) : runs.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm font-medium text-neutral-500">No runs found</p>
          <p className="mt-1 text-xs text-neutral-400">
            {query || statusFilter
              ? "Try adjusting your search or filters"
              : "Run the demo agent to create your first run"}
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-1.5">
            {runs.map((run) => (
              <RunCard key={run.id} run={run} />
            ))}
          </div>

          {hasMore && (
            <div className="mt-6 text-center">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="rounded-lg bg-neutral-900 px-5 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-80 disabled:opacity-40"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg bg-neutral-50/60 px-5 py-4">
      <div className="flex items-center gap-3">
        <div className="h-3.5 w-28 rounded bg-neutral-200/60" />
        <div className="h-3.5 w-16 rounded-full bg-neutral-200/40" />
      </div>
      <div className="mt-2.5 flex gap-3">
        <div className="h-2.5 w-14 rounded bg-neutral-200/40" />
        <div className="h-2.5 w-10 rounded bg-neutral-200/40" />
        <div className="h-2.5 w-16 rounded bg-neutral-200/40" />
      </div>
      <div className="mt-3 h-2.5 w-3/4 rounded bg-neutral-200/30" />
    </div>
  );
}

function RunCard({ run }: { run: RunListItem }) {
  const failed = run.status === "failed";
  const preview = formatSummary(run.output_summary, 140);
  const accent = failed
    ? "bg-red-200 group-hover:bg-red-500"
    : "bg-neutral-200 group-hover:bg-neutral-800";

  return (
    <Link
      href={`/runs/${run.id}`}
      className="group flex items-stretch rounded-lg transition-all duration-100 hover:bg-neutral-50/80 hover:shadow-[0_1px_4px_rgba(0,0,0,0.04)]"
    >
      <div className={`w-[3px] shrink-0 rounded-l-lg transition-colors duration-150 ${accent}`} />

      <div className="flex-1 px-5 py-4">
        {/* Title row */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <span className="truncate text-[13px] font-semibold leading-5 text-neutral-900 group-hover:text-neutral-950">
              {run.workflow_name}
            </span>
            <span
              className={`shrink-0 rounded-full px-2 py-[2px] text-[10px] font-medium leading-3 ${statusClass(run.status)}`}
            >
              {run.status}
            </span>
          </div>
          <span className="shrink-0 text-[11px] tabular-nums text-neutral-400">
            {timeAgo(run.created_at)}
          </span>
        </div>

        {/* Metadata row */}
        <div className="mt-2 flex items-center gap-1.5 text-[11px] leading-4 text-neutral-400">
          <span>{run.total_steps} steps</span>
          <span className="text-neutral-250">·</span>
          <span>{formatDuration(run.total_duration_ms)}</span>
          <span className="text-neutral-250">·</span>
          <span className="font-mono text-[10px] text-neutral-350">{run.id.slice(0, 8)}</span>
        </div>

        {/* Preview row */}
        {preview && (
          <p className="mt-2.5 line-clamp-2 font-mono text-[11px] leading-[18px] text-neutral-400">
            {preview}
          </p>
        )}
      </div>
    </Link>
  );
}
