"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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
const SCROLL_KEY = "leer-runs-scroll";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "", label: "All" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
];

// ---------------------------------------------------------------------------
// URL helpers
// ---------------------------------------------------------------------------

function parseUrlParams(): { q: string; status: StatusFilter; sort: SortOrder; limit: number } {
  if (typeof window === "undefined") return { q: "", status: "", sort: "newest", limit: PAGE_SIZE };
  const p = new URLSearchParams(window.location.search);
  const st = p.get("status");
  const so = p.get("sort");
  return {
    q: p.get("q") ?? "",
    status: st === "completed" || st === "failed" ? st : "",
    sort: so === "newest" || so === "oldest" ? so : "newest",
    limit: Math.min(100, Math.max(PAGE_SIZE, parseInt(p.get("limit") ?? "", 10) || PAGE_SIZE)),
  };
}

function buildUrl(q: string, status: StatusFilter, sort: SortOrder, limit: number): string {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (status) p.set("status", status);
  if (sort !== "newest") p.set("sort", sort);
  if (limit > PAGE_SIZE) p.set("limit", String(limit));
  const qs = p.toString();
  return qs ? `/?${qs}` : "/";
}

// ---------------------------------------------------------------------------
// Scroll helpers — targets <main> in Shell
// ---------------------------------------------------------------------------

function saveScrollPosition() {
  const main = document.querySelector("main");
  if (main) sessionStorage.setItem(SCROLL_KEY, String(main.scrollTop));
}

function restoreScrollPosition() {
  const main = document.querySelector("main");
  const saved = sessionStorage.getItem(SCROLL_KEY);
  if (main && saved) {
    main.scrollTop = parseInt(saved, 10);
    sessionStorage.removeItem(SCROLL_KEY);
  }
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function HomePage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialLoad, setInitialLoad] = useState(true);
  const [searching, setSearching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [compareTray, setCompareTray] = useState<RunListItem[]>([]);

  const toggleCompare = useCallback((run: RunListItem) => {
    setCompareTray((prev) => {
      const already = prev.find((r) => r.id === run.id);
      if (already) return prev.filter((r) => r.id !== run.id);
      if (prev.length >= 2) return [prev[1], run];
      return [...prev, run];
    });
  }, []);

  const initParams = useRef(parseUrlParams());
  const [query, setQuery] = useState(initParams.current.q);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(initParams.current.status);
  const [sort, setSort] = useState<SortOrder>(initParams.current.sort);

  const searchRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const fetchIdRef = useRef(0);
  const loadedCountRef = useRef(0);
  const isPopstateRef = useRef(false);
  const nextLimitRef = useRef(initParams.current.limit);

  const fetchRuns = useCallback(
    async (q: string, status: StatusFilter, sortOrder: SortOrder, offset: number, limit: number, append: boolean) => {
      const id = ++fetchIdRef.current;
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (status) params.set("status", status);
      params.set("sort", sortOrder);
      params.set("limit", String(limit));
      params.set("offset", String(offset));

      const data = await apiFetch<ProjectRunsResponse>(
        `/v1/projects/demo-project/runs?${params}`,
      );

      if (fetchIdRef.current !== id) return;

      if (append) {
        setRuns((prev) => {
          const existing = new Set(prev.map((r) => r.id));
          const merged = [...prev, ...data.runs.filter((r) => !existing.has(r.id))];
          loadedCountRef.current = merged.length;
          return merged;
        });
      } else {
        setRuns(data.runs);
        loadedCountRef.current = data.runs.length;
      }
      setTotalCount(data.total_count);
      setHasMore(data.has_more);
    },
    [],
  );

  // Main data effect — handles mount, filter/sort changes, debounced search, popstate
  const prevRef = useRef({ query, statusFilter, sort });
  const didMountRef = useRef(false);
  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = { query, statusFilter, sort };
    clearTimeout(debounceRef.current);

    const isMount = !didMountRef.current;
    didMountRef.current = true;

    const popstate = isPopstateRef.current;
    isPopstateRef.current = false;

    const searchChanged = query !== prev.query;
    const filtersChanged = statusFilter !== prev.statusFilter || sort !== prev.sort;

    function execute() {
      setError(null);
      const limit = isMount || popstate ? nextLimitRef.current : PAGE_SIZE;
      nextLimitRef.current = PAGE_SIZE;

      if (loadedCountRef.current === 0) setInitialLoad(true);
      else setSearching(true);

      fetchRuns(query, statusFilter, sort, 0, limit, false)
        .catch((err) => setError(err.message))
        .finally(() => {
          setInitialLoad(false);
          setSearching(false);

          if (!popstate && !isMount) {
            const url = buildUrl(query, statusFilter, sort, PAGE_SIZE);
            if (filtersChanged) {
              window.history.pushState(null, "", url);
            } else {
              window.history.replaceState(null, "", url);
            }
          }

          if (isMount) {
            requestAnimationFrame(restoreScrollPosition);
          }
        });
    }

    if (isMount || popstate || filtersChanged) {
      execute();
    } else if (searchChanged) {
      debounceRef.current = setTimeout(execute, 250);
    }

    return () => clearTimeout(debounceRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, statusFilter, sort]);

  // Popstate: sync URL → state
  useEffect(() => {
    function onPopstate() {
      const p = parseUrlParams();
      isPopstateRef.current = true;
      nextLimitRef.current = p.limit;
      setQuery(p.q);
      setStatusFilter(p.status);
      setSort(p.sort);
    }
    window.addEventListener("popstate", onPopstate);
    return () => window.removeEventListener("popstate", onPopstate);
  }, []);

  // "/" keyboard shortcut
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
    const offset = loadedCountRef.current;
    fetchRuns(query, statusFilter, sort, offset, PAGE_SIZE, true)
      .catch((err) => setError(err.message))
      .finally(() => {
        setLoadingMore(false);
        const url = buildUrl(query, statusFilter, sort, loadedCountRef.current);
        window.history.replaceState(null, "", url);
      });
  }

  const loading = initialLoad;

  return (
    <div className="-mx-10 -mt-8">
      {/* ── Sticky header ── */}
      <div className="sticky top-0 z-10 border-b border-neutral-100 bg-[var(--background)]/80 backdrop-blur-sm">
        <div className="max-w-6xl px-10 pb-4 pt-8">
          {/* Title */}
          <div className="mb-5">
            <h1 className="text-[17px] font-semibold tracking-tight text-neutral-900">Runs</h1>
            <p className="mt-0.5 text-[12px] text-neutral-400">Recent agent executions</p>
          </div>

          {/* Control bar */}
          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative flex-1 max-w-lg">
              <svg className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search runs…"
                className="h-8 w-full rounded-lg bg-neutral-100/60 pl-9 pr-9 text-[13px] text-neutral-800 placeholder:text-neutral-400 transition-all focus:bg-white focus:shadow-[0_0_0_1px_rgba(0,0,0,0.08),0_2px_6px_rgba(0,0,0,0.04)] focus:outline-none"
              />
              <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-neutral-200/80 bg-white px-1.5 py-0.5 font-mono text-[10px] leading-none text-neutral-400">
                /
              </kbd>
            </div>

            {/* Divider */}
            <div className="h-5 w-px bg-neutral-200/60" />

            {/* Status pills */}
            <div className="flex rounded-lg bg-neutral-100/60 p-0.5">
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
            <div className="flex rounded-lg bg-neutral-100/60 p-0.5">
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

          {/* Count / searching indicator */}
          {!loading && !error && (
            <div className="mt-4 flex items-center justify-between">
              <p className={`text-[11px] text-neutral-400 transition-opacity ${searching ? "opacity-50" : ""}`}>
                {totalCount} {totalCount === 1 ? "run" : "runs"}
                {(query || statusFilter) ? " matched" : ""}
              </p>
              {searching && (
                <span className="text-[10px] text-neutral-400">Searching…</span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Run list ── */}
      <div className="max-w-6xl px-10 pb-12 pt-4">
        {loading ? (
          <div className="space-y-1">
            {[...Array(5)].map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : error ? (
          <div className="rounded-lg bg-[var(--tint-error-block)] p-5 text-center text-sm text-[var(--error-text)]">
            Failed to load runs: {error}
          </div>
        ) : runs.length === 0 ? (
          <div className="py-20 text-center">
            <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-neutral-100">
              <svg className="h-5 w-5 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-neutral-600">No runs found</p>
            <p className="mt-1 text-[12px] text-neutral-400">
              {query || statusFilter
                ? "Try adjusting your search or filters"
                : "Run the demo agent to create your first run"}
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-1">
              {runs.map((run) => (
                <RunCard
                  key={run.id}
                  run={run}
                  inTray={compareTray.some((r) => r.id === run.id)}
                  onToggleCompare={toggleCompare}
                />
              ))}
            </div>

            {hasMore && (
              <div className="mt-8 text-center">
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

      {/* ── Sticky compare tray ── */}
      {compareTray.length > 0 && (
        <div className="sticky bottom-0 z-20 border-t border-neutral-200 bg-white/95 backdrop-blur-sm">
          <div className="mx-auto flex max-w-6xl items-center gap-3 px-10 py-3">
            <span className="text-[11px] font-medium text-neutral-500">Comparing:</span>
            {compareTray.map((r) => (
              <button
                key={r.id}
                onClick={() => toggleCompare(r)}
                className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1 text-[11px] font-medium text-neutral-700 transition-colors hover:bg-neutral-100"
              >
                <span className="max-w-[140px] truncate">{r.workflow_name}</span>
                <span className="text-neutral-400">&times;</span>
              </button>
            ))}
            <button
              onClick={() => {
                if (compareTray.length === 2) {
                  router.push(`/compare?a=${compareTray[0].id}&b=${compareTray[1].id}`);
                }
              }}
              disabled={compareTray.length < 2}
              className="ml-auto rounded-lg bg-neutral-900 px-4 py-1.5 text-[11px] font-medium text-white transition-opacity hover:opacity-80 disabled:opacity-30"
            >
              Compare
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg px-4 py-4">
      <div className="flex items-center gap-3">
        <div className="h-3.5 w-32 rounded bg-neutral-200/50" />
        <div className="h-4 w-16 rounded-full bg-neutral-100" />
      </div>
      <div className="mt-2.5 flex gap-2">
        <div className="h-2.5 w-14 rounded bg-neutral-100" />
        <div className="h-2.5 w-10 rounded bg-neutral-100" />
        <div className="h-2.5 w-16 rounded bg-neutral-100" />
      </div>
      <div className="mt-3 h-2.5 w-2/3 rounded bg-neutral-100/70" />
    </div>
  );
}

function RunCard({
  run,
  inTray,
  onToggleCompare,
}: {
  run: RunListItem;
  inTray: boolean;
  onToggleCompare: (run: RunListItem) => void;
}) {
  const failed = run.status === "failed";
  const preview = formatSummary(run.output_summary, 160);
  const accent = failed
    ? "bg-[var(--accent-fail)] group-hover:bg-[var(--accent-fail-hover)]"
    : "bg-transparent group-hover:bg-neutral-800";

  return (
    <div className="group relative flex items-stretch rounded-lg transition-all duration-100 hover:bg-neutral-50 hover:shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <Link
        href={`/runs/${run.id}`}
        onClick={saveScrollPosition}
        className="flex flex-1 items-stretch"
      >
        <div className={`w-[2px] shrink-0 rounded-l-lg transition-colors duration-150 ${accent}`} />

        <div className="flex-1 px-4 py-3.5">
          {/* Title row */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5 overflow-hidden">
              <span className="truncate text-[13px] font-semibold leading-5 text-neutral-900">
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
          <div className="mt-1.5 flex items-center gap-1.5 text-[11px] leading-4 text-neutral-400">
            <span>{run.total_steps} steps</span>
            <span className="text-neutral-300">·</span>
            <span>{formatDuration(run.total_duration_ms)}</span>
            <span className="text-neutral-300">·</span>
            <span className="font-mono text-[10px]">{run.id.slice(0, 8)}</span>
          </div>

          {/* Preview row */}
          {preview && (
            <p className="mt-2 line-clamp-2 text-[11px] leading-[17px] text-neutral-400">
              {preview}
            </p>
          )}
        </div>
      </Link>

      {/* Compare toggle — visible on hover or when active */}
      <button
        onClick={(e) => { e.stopPropagation(); onToggleCompare(run); }}
        className={`absolute right-3 top-1/2 -translate-y-1/2 rounded-md border px-2.5 py-1 text-[10px] font-medium transition-all ${
          inTray
            ? "border-neutral-300 bg-neutral-900 text-white opacity-100"
            : "border-neutral-200 bg-white text-neutral-500 opacity-0 hover:border-neutral-300 hover:bg-neutral-50 group-hover:opacity-100"
        }`}
      >
        {inTray ? "Selected" : "Compare"}
      </button>
    </div>
  );
}
