"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatDuration, statusClass, timeAgo } from "@/lib/format";
import type { ProjectRunsResponse, RunListItem } from "@/lib/types";
import { X, Search, ChevronDown } from "lucide-react";

export interface SelectedRun {
  id: string;
  workflow_name: string;
  status: string;
  created_at: string;
}

interface RunSelectorProps {
  label: string;
  value: SelectedRun | null;
  onChange: (run: SelectedRun | null) => void;
  excludeId?: string;
  autoFocus?: boolean;
}

export function RunSelector({ label, value, onChange, excludeId, autoFocus }: RunSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const fetchRuns = useCallback(
    async (q: string) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ limit: "8", sort: "newest" });
        if (q) params.set("q", q);
        const data = await apiFetch<ProjectRunsResponse>(
          `/v1/projects/demo-project/runs?${params}`,
        );
        setRuns(excludeId ? data.runs.filter((r) => r.id !== excludeId) : data.runs);
      } catch {
        setRuns([]);
      } finally {
        setLoading(false);
      }
    },
    [excludeId],
  );

  useEffect(() => {
    if (!open) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchRuns(query), 180);
    return () => clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, open]);

  useEffect(() => {
    if (open && runs.length === 0 && !loading) fetchRuns(query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (autoFocus && !value) inputRef.current?.focus();
  }, [autoFocus, value]);

  function selectRun(run: RunListItem) {
    onChange({
      id: run.id,
      workflow_name: run.workflow_name,
      status: run.status,
      created_at: run.created_at,
    });
    setOpen(false);
    setQuery("");
  }

  if (value) {
    const failed = value.status === "failed";
    return (
      <div>
        <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
          {label}
        </div>
        <div
          className={`flex items-stretch rounded-lg border shadow-[0_1px_3px_rgba(0,0,0,0.04)] ${
            failed
              ? "border-[var(--accent-fail)]/40 bg-[var(--tint-error)]"
              : "border-neutral-200 bg-white"
          }`}
        >
          <div
            className={`w-[3px] shrink-0 rounded-l-lg ${
              failed ? "bg-[var(--accent-fail-hover)]" : "bg-neutral-900"
            }`}
          />
          <div className="flex flex-1 items-center justify-between px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-semibold text-neutral-900">
                  {value.workflow_name}
                </span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(value.status)}`}
                >
                  {value.status}
                </span>
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-neutral-400">
                <span>{timeAgo(value.created_at)}</span>
                <span className="text-neutral-300">·</span>
                <span className="font-mono">{value.id.slice(0, 8)}</span>
              </div>
            </div>
            <button
              onClick={() => onChange(null)}
              className="ml-3 shrink-0 rounded p-1 text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-600"
              title="Clear selection"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
        {label}
      </div>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className={`flex h-[50px] w-full items-center rounded-lg border border-dashed border-neutral-300 bg-neutral-50/50 px-4 text-sm text-neutral-400 transition-colors hover:border-neutral-400 hover:bg-neutral-50 ${
          open ? "hidden" : ""
        }`}
      >
        <Search size={14} className="mr-2 text-neutral-300" />
        <span>Select a run…</span>
        <ChevronDown size={14} className="ml-auto text-neutral-300" />
      </button>

      <div className={`relative ${open ? "" : "hidden"}`}>
        <Search
          size={14}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400"
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!open) setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              setQuery("");
            }
          }}
          placeholder="Search by name, ID, or output…"
          className="h-[50px] w-full rounded-lg border border-neutral-200 bg-white pl-9 pr-3 text-sm text-neutral-800 placeholder:text-neutral-400 transition-colors focus:border-neutral-400 focus:outline-none"
        />
      </div>

      {open && (
        <div className="absolute z-50 mt-1.5 max-h-80 w-full overflow-auto rounded-lg border border-neutral-200 bg-white shadow-lg">
          {loading && runs.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-neutral-400">Searching…</div>
          ) : runs.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-neutral-400">
              {query ? "No matching runs" : "No runs available"}
            </div>
          ) : (
            runs.map((run) => {
              const failed = run.status === "failed";
              return (
                <button
                  key={run.id}
                  onClick={() => selectRun(run)}
                  className="group w-full border-b border-neutral-100 px-4 py-3 text-left transition-colors last:border-0 hover:bg-neutral-50"
                >
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-neutral-800 group-hover:text-neutral-900">
                      {run.workflow_name}
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(run.status)}`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-neutral-400">
                    <span>{timeAgo(run.created_at)}</span>
                    <span className="text-neutral-300">·</span>
                    <span>{formatDuration(run.total_duration_ms)}</span>
                    <span className="text-neutral-300">·</span>
                    <span className="font-mono">{run.id.slice(0, 8)}</span>
                    {failed && (
                      <>
                        <span className="text-neutral-300">·</span>
                        <span className="text-[var(--error-accent)]">{run.failed_steps} failed</span>
                      </>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
