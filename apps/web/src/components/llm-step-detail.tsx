"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import type { LLMShape, StepArtifactRef } from "@/lib/types";
import { formatDuration, errorHeadline, errorDetail, rawJson } from "@/lib/format";
import { StructuredValue } from "@/components/structured-value";
import { ArtifactViewer } from "@/components/artifact-viewer";
import { computeLatencyBreakdown, type LatencyBreakdown } from "@/lib/latency";

type Dict = Record<string, unknown>;

/* ------------------------------------------------------------------ */
/* Shared micro-components                                             */
/* ------------------------------------------------------------------ */

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);

  return (
    <button
      onClick={copy}
      className="rounded px-1.5 py-0.5 text-[10px] text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function RawToggle({ raw, onToggle }: { raw: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-400 transition-colors hover:bg-neutral-200 hover:text-neutral-600"
    >
      {raw ? "Formatted" : "Raw"}
    </button>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <p className="py-0.5 text-xs italic text-neutral-400">{text}</p>;
}

export const ROLE_STYLES: Record<string, string> = {
  system: "text-violet-500/80 dark:text-violet-400/70",
  developer: "text-violet-500/80 dark:text-violet-400/70",
  user: "text-blue-500/80 dark:text-blue-400/70",
  assistant: "text-emerald-500/80 dark:text-emerald-400/70",
  tool: "text-amber-500/80 dark:text-amber-400/70",
};

/* ------------------------------------------------------------------ */
/* Structured-output helpers                                           */
/* ------------------------------------------------------------------ */

/** Safely parse a string as JSON, returning the value only for objects/arrays. */
export function tryParseJson(text: string): unknown | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed === "object" && parsed !== null) return parsed;
    return null;
  } catch {
    return null;
  }
}

/** Resolve tool-call arguments into a structured value for rendering. */
export function resolveArgs(args: unknown): unknown {
  if (args == null) return null;
  if (typeof args === "string") {
    if (!args) return null;
    try {
      return resolveArgs(JSON.parse(args));
    } catch {
      return args;
    }
  }
  if (Array.isArray(args)) return args.length > 0 ? args : null;
  if (typeof args === "object") {
    return Object.keys(args as Record<string, unknown>).length > 0 ? args : null;
  }
  return null;
}

/* ------------------------------------------------------------------ */
/* Main export                                                         */
/* ------------------------------------------------------------------ */

export interface ToolCallLinkInfo {
  toolStepId: string;
  toolStepName: string;
  toolStepIndex: number;
  toolStepStatus: string;
}

export interface BlobStreamState {
  loading: boolean;
  error: string | null;
  loaded: boolean;
  onLoad: () => void;
}

export function LlmStepDetail({
  llm,
  errorSummary,
  toolCallLinks,
  onJumpToStep,
  durationMs,
  streamMeta,
  streamEvents,
  blobStreamState,
  artifacts,
}: {
  llm: LLMShape;
  errorSummary?: Dict | null;
  toolCallLinks?: Map<string, ToolCallLinkInfo>;
  onJumpToStep?: (stepId: string) => void;
  durationMs?: number | null;
  streamMeta?: Dict | null;
  streamEvents?: Dict[];
  blobStreamState?: BlobStreamState;
  artifacts?: StepArtifactRef[];
}) {
  const [raw, setRaw] = useState(false);
  const rawText = JSON.stringify(llm, null, 2);

  const hasInput = !!llm.input.system || llm.input.messages.length > 0 || llm.input.tools.length > 0 || Object.keys(llm.input.params).length > 0;
  const hasOutputText = !!llm.output.text;
  const hasToolCalls = llm.output.tool_calls.length > 0;
  const hasOutput = hasOutputText || hasToolCalls;
  const hasError = errorSummary && Object.keys(errorSummary).length > 0;
  const isStream = streamMeta?.is_stream === true;

  const breakdown = useMemo(
    () => computeLatencyBreakdown({
      durationMs: durationMs ?? llm.meta.latency_ms,
      streamMeta,
      usage: llm.usage,
    }),
    [durationMs, llm.meta.latency_ms, streamMeta, llm.usage],
  );

  return (
    <div className="space-y-3 border-t border-neutral-100 px-5 pb-5 pt-4">
      {/* Top bar: metadata + controls */}
      <div className="flex items-start justify-between gap-4">
        <MetadataRow llm={llm} />
        <div className="flex shrink-0 items-center gap-1">
          <CopyBtn text={rawText} />
          <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
        </div>
      </div>

      {raw ? (
        <pre className="max-h-96 overflow-auto rounded-md bg-neutral-50 px-4 py-3 font-mono text-xs leading-6 text-neutral-600">
          {rawText}
        </pre>
      ) : (
        <>
          {hasInput && <InputSection llm={llm} />}
          {!hasInput && !hasError && <EmptyHint text="No prompt captured" />}
          {hasOutput && <OutputSection llm={llm} hideToolCalls={hasToolCalls} />}
          {!hasOutput && !hasError && <EmptyHint text="No response captured" />}
          {hasToolCalls && (
            <ToolCallsSection
              calls={llm.output.tool_calls}
              toolCallLinks={toolCallLinks}
              onJumpToStep={onJumpToStep}
            />
          )}
          {breakdown.is_available && <LatencyBreakdownRow breakdown={breakdown} />}
          {isStream && <StreamSection meta={streamMeta!} events={streamEvents} breakdown={breakdown} blobStreamState={blobStreamState} />}
          {hasError && <ErrorSection data={errorSummary!} />}
          <UsageRow usage={llm.usage} />
          {artifacts && artifacts.length > 0 && (
            <LlmArtifactList artifacts={artifacts} />
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Metadata row                                                        */
/* ------------------------------------------------------------------ */

function MetadataRow({ llm }: { llm: LLMShape }) {
  const primary: { label: string; value: string; mono?: boolean }[] = [];
  const secondary: { label: string; value: string }[] = [];

  if (llm.provider) primary.push({ label: "provider", value: llm.provider });
  if (llm.meta.latency_ms != null)
    primary.push({ label: "latency", value: formatDuration(llm.meta.latency_ms) });
  if (llm.meta.finish_reason)
    primary.push({ label: "finish", value: llm.meta.finish_reason });
  if (llm.usage.total_tokens != null)
    primary.push({ label: "tokens", value: llm.usage.total_tokens.toLocaleString(), mono: true });

  if (llm.meta.request_id) secondary.push({ label: "id", value: llm.meta.request_id });

  if (primary.length === 0 && secondary.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
      {primary.map((p) => (
        <span key={p.label} className="text-neutral-400">
          {p.label}{" "}
          <span className={`font-medium text-neutral-700 ${p.mono ? "tabular-nums" : ""}`}>
            {p.value}
          </span>
        </span>
      ))}
      {secondary.length > 0 && primary.length > 0 && (
        <span className="text-neutral-200">·</span>
      )}
      {secondary.map((s) => (
        <span key={s.label} className="text-neutral-300">
          {s.label}{" "}
          <span className="font-mono text-[10px] text-neutral-400">{s.value}</span>
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Input section                                                       */
/* ------------------------------------------------------------------ */

function InputSection({ llm }: { llm: LLMShape }) {
  const input = llm.input;

  return (
    <div className="rounded-md bg-[var(--tint-input)] px-4 py-3">
      <div className="mb-2.5 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Input
      </div>
      <div className="space-y-4">
        {input.system && <MessageBlock role="system" content={input.system} />}
        {input.messages.map((msg, i) => {
          const role = (msg.role as string) ?? "unknown";
          const content = extractMessageContent(msg);
          return <MessageBlock key={i} role={role} content={content} />;
        })}
        {input.tools.length > 0 && <ToolsList tools={input.tools} />}
        {Object.keys(input.params).length > 0 && <ParamsBlock params={input.params} />}
      </div>
    </div>
  );
}

function MessageBlock({ role, content }: { role: string; content: string }) {
  const color = ROLE_STYLES[role] ?? "text-neutral-400";
  return (
    <div>
      <span className={`mb-1 inline-block text-[10px] font-medium ${color}`}>{role}</span>
      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
        {content || "(empty)"}
      </pre>
    </div>
  );
}

export function extractMessageContent(msg: Record<string, unknown>): string {
  const c = msg.content;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    return c
      .map((block) => {
        if (typeof block === "string") return block;
        if (block && typeof block === "object") {
          const b = block as Record<string, unknown>;
          if (typeof b.text === "string") return b.text;
          return JSON.stringify(b);
        }
        return String(block);
      })
      .join("\n");
  }
  if (c != null) return JSON.stringify(c, null, 2);
  return "";
}

function ToolsList({ tools }: { tools: Record<string, unknown>[] }) {
  const names = tools.map(
    (t) => (t.name as string) ?? (t.function as Record<string, unknown>)?.name ?? "tool",
  );
  return (
    <div>
      <span className="mb-1 inline-block text-[10px] font-medium text-neutral-400">tools</span>
      <div className="flex flex-wrap gap-1.5">
        {names.map((n, i) => (
          <span key={i} className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-500">
            {n}
          </span>
        ))}
      </div>
    </div>
  );
}

function ParamsBlock({ params }: { params: Record<string, unknown> }) {
  const entries = Object.entries(params).filter(([, v]) => v != null);
  if (entries.length === 0) return null;
  return (
    <div>
      <span className="mb-1 inline-block text-[10px] font-medium text-neutral-400">params</span>
      <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px]">
        {entries.map(([k, v]) => (
          <span key={k} className="text-neutral-500">
            {k}=<span className="text-neutral-700">{String(v)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Output section                                                      */
/* ------------------------------------------------------------------ */

function OutputSection({ llm, hideToolCalls }: { llm: LLMShape; hideToolCalls?: boolean }) {
  const output = llm.output;
  const structuredText = output.text ? tryParseJson(output.text) : null;

  return (
    <div className="rounded-md bg-[var(--tint-output)] px-4 py-3">
      <div className="mb-2.5 text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Output
      </div>
      <div className="space-y-3">
        {output.text &&
          (structuredText != null ? (
            <StructuredValue value={structuredText} />
          ) : (
            <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
              {output.text}
            </pre>
          ))}
        {!hideToolCalls && output.tool_calls.length > 0 && <ToolCallsList calls={output.tool_calls} />}
      </div>
    </div>
  );
}

function ToolCallsList({ calls }: { calls: Record<string, unknown>[] }) {
  return (
    <div className="space-y-2">
      <span className="text-[10px] font-medium text-neutral-400">Tool calls</span>
      {calls.map((tc, i) => (
        <div key={i} className="rounded bg-neutral-50 px-3 py-2">
          <span className="font-mono text-[11px] font-medium text-neutral-700">
            {(tc.name as string) ?? "call"}
          </span>
          {tc.arguments != null && (
            <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-neutral-500">
              {typeof tc.arguments === "string"
                ? tc.arguments
                : JSON.stringify(tc.arguments, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Tool calls section (dedicated, between Output and Tokens)           */
/* ------------------------------------------------------------------ */

function truncateId(id: string, max = 20): string {
  return id.length > max ? id.slice(0, max) + "…" : id;
}

function ToolCallsSection({
  calls,
  toolCallLinks,
  onJumpToStep,
}: {
  calls: Dict[];
  toolCallLinks?: Map<string, ToolCallLinkInfo>;
  onJumpToStep?: (stepId: string) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-medium text-neutral-400">Tool calls</div>
      {calls.map((tc, i) => {
        const callId = (tc.id as string) ?? null;
        const name = (tc.name as string) ?? "call";
        const link = callId ? toolCallLinks?.get(callId) : undefined;
        const args = resolveArgs(tc.arguments);

        return (
          <div
            key={i}
            className="rounded-md bg-amber-50/40 px-3 py-1.5 dark:bg-amber-950/20"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-x-3 gap-y-1">
                <span className="text-[12px] font-semibold text-neutral-800 dark:text-neutral-200">{name}</span>
                {callId && (
                  <span className="font-mono text-[10px] text-neutral-400" title={callId}>
                    {truncateId(callId)}
                  </span>
                )}
                {link ? (
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    #{link.toolStepIndex}
                  </span>
                ) : (
                  <span className="text-[10px] italic text-neutral-400">untraced</span>
                )}
              </div>
              {link && onJumpToStep && (
                <button
                  onClick={() => onJumpToStep(link.toolStepId)}
                  className="shrink-0 whitespace-nowrap text-[10px] font-medium text-amber-700 transition-colors hover:text-amber-900 dark:text-amber-400 dark:hover:text-amber-300"
                >
                  →
                </button>
              )}
            </div>
            {args != null && (
              <div className="mt-1.5">
                <StructuredValue value={args} defaultExpanded={false} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Local formatting helpers                                            */
/* ------------------------------------------------------------------ */

function fmtRate(v: number | null, unit: string): string | null {
  if (v === null) return null;
  return v >= 100 ? `${Math.round(v)} ${unit}` : `${v.toFixed(1)} ${unit}`;
}

function fmtPct(v: number | null): string | null {
  if (v === null) return null;
  return `${Math.round(v * 100)}%`;
}

/* ------------------------------------------------------------------ */
/* Latency breakdown row (compact, replaces old StreamStatsRow)        */
/* ------------------------------------------------------------------ */

function LatencyBreakdownRow({ breakdown }: { breakdown: LatencyBreakdown }) {
  const items: { label: string; value: string }[] = [];

  if (breakdown.total_ms !== null)
    items.push({ label: "Total", value: formatDuration(breakdown.total_ms) });
  if (breakdown.ttfc_ms !== null)
    items.push({ label: "TTFC", value: formatDuration(breakdown.ttfc_ms) });
  if (breakdown.generation_ms !== null)
    items.push({ label: "Generation", value: formatDuration(breakdown.generation_ms) });

  const cps = fmtRate(breakdown.chars_per_sec, "chars/s");
  if (cps) items.push({ label: "", value: cps });

  const tps = fmtRate(breakdown.tokens_per_sec, "tok/s");
  if (tps) items.push({ label: "", value: tps });

  if (breakdown.termination && breakdown.termination !== "completed")
    items.push({ label: "", value: breakdown.termination });
  if (breakdown.truncated_chunks)
    items.push({ label: "", value: "truncated" });

  if (items.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md bg-violet-50/50 px-4 py-2 text-[11px] dark:bg-violet-950/30">
      <span className="text-[10px] font-medium uppercase tracking-wider text-violet-400 dark:text-violet-500">
        Latency
      </span>
      <span className="text-violet-200 dark:text-violet-700">·</span>
      {items.map((item, i) => (
        <span key={i} className="text-neutral-400">
          {item.label && <>{item.label}{" "}</>}
          <span className="font-medium tabular-nums text-neutral-700">{item.value}</span>
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stream latency summary (inside expanded stream section)             */
/* ------------------------------------------------------------------ */

function StreamLatencySummary({ breakdown }: { breakdown: LatencyBreakdown }) {
  if (!breakdown.is_available) return null;

  const rows: { id: string; label: string; value: string | null }[] = [
    { id: "total_ms", label: "Total latency", value: breakdown.total_ms !== null ? formatDuration(breakdown.total_ms) : null },
    { id: "ttfc_ms", label: "TTFC", value: breakdown.ttfc_ms !== null ? formatDuration(breakdown.ttfc_ms) : null },
    { id: "generation_ms", label: "Generation time", value: breakdown.generation_ms !== null ? formatDuration(breakdown.generation_ms) : null },
    { id: "overhead_ms", label: "Overhead", value: breakdown.overhead_ms != null && breakdown.overhead_ms > 0 ? formatDuration(breakdown.overhead_ms) : null },
    { id: "chunk_count", label: "Chunks", value: breakdown.chunk_count !== null ? String(breakdown.chunk_count) : null },
    { id: "text_chars", label: "Output chars", value: breakdown.text_chars !== null ? String(breakdown.text_chars) : null },
    { id: "chars_per_sec", label: "Chars/s", value: breakdown.chars_per_sec !== null ? (breakdown.chars_per_sec >= 100 ? String(Math.round(breakdown.chars_per_sec)) : breakdown.chars_per_sec.toFixed(1)) : null },
    { id: "tokens_per_sec", label: "Tok/s", value: breakdown.tokens_per_sec !== null ? (breakdown.tokens_per_sec >= 100 ? String(Math.round(breakdown.tokens_per_sec)) : breakdown.tokens_per_sec.toFixed(1)) : null },
    { id: "startup_pct", label: "Startup share", value: fmtPct(breakdown.startup_pct) },
    { id: "generation_pct", label: "Generation share", value: fmtPct(breakdown.generation_pct) },
  ];

  const visible = rows.filter((r) => r.value !== null);
  if (visible.length === 0) return null;

  return (
    <div className="mx-4 mb-2 grid grid-cols-2 gap-x-6 gap-y-0.5 rounded-md bg-violet-50/40 px-3 py-2 text-[11px] dark:bg-violet-950/20 sm:grid-cols-3">
      {visible.map((r) => (
        <div key={r.id} className="flex items-baseline gap-1.5">
          <span className="text-neutral-400">{r.label}</span>
          <span className="font-medium tabular-nums text-neutral-700">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stream display item types + grouping                                */
/* ------------------------------------------------------------------ */

type DisplayItem =
  | { kind: "event"; event: Dict; idx: number; offset: number | null }
  | { kind: "text_group"; text: string; startIdx: number; count: number; firstOffset: number | null; lastOffset: number | null }
  | { kind: "tool_call_group"; toolIndex: number; name: string; args: string; startIdx: number; count: number; firstOffset: number | null; lastOffset: number | null };

function getOffset(ev: Dict): number | null {
  return typeof ev.timestamp_offset_ms === "number" ? ev.timestamp_offset_ms : null;
}

function groupStreamEvents(events: Dict[]): DisplayItem[] {
  const items: DisplayItem[] = [];
  let i = 0;

  while (i < events.length) {
    const ev = events[i];
    const type = String(ev.type ?? "");

    if (type === "text_delta") {
      const start = i;
      let text = "";
      const firstOff = getOffset(ev);
      let lastOff = firstOff;
      while (i < events.length && String(events[i].type) === "text_delta") {
        const t = events[i];
        text += typeof t.text === "string" ? t.text : "";
        const o = getOffset(t);
        if (o != null) lastOff = o;
        i++;
      }
      if (i - start > 1) {
        items.push({ kind: "text_group", text, startIdx: start, count: i - start, firstOffset: firstOff, lastOffset: lastOff });
      } else {
        items.push({ kind: "event", event: ev, idx: start, offset: firstOff });
      }
    } else if (type === "tool_call_delta") {
      const start = i;
      const tIdx = typeof ev.tool_index === "number" ? ev.tool_index : 0;
      let name = "";
      let args = "";
      const firstOff = getOffset(ev);
      let lastOff = firstOff;
      while (i < events.length && String(events[i].type) === "tool_call_delta") {
        const t = events[i];
        const ti = typeof t.tool_index === "number" ? t.tool_index : 0;
        if (ti !== tIdx && i > start) break;
        if (typeof t.name === "string") name += t.name;
        if (typeof t.arguments === "string") args += t.arguments;
        const o = getOffset(t);
        if (o != null) lastOff = o;
        i++;
      }
      if (i - start > 1) {
        items.push({ kind: "tool_call_group", toolIndex: tIdx, name, args, startIdx: start, count: i - start, firstOffset: firstOff, lastOffset: lastOff });
      } else {
        items.push({ kind: "event", event: ev, idx: start, offset: firstOff });
      }
    } else {
      items.push({ kind: "event", event: ev, idx: i, offset: getOffset(ev) });
      i++;
    }
  }
  return items;
}

/* ------------------------------------------------------------------ */
/* Stream section (collapsible event viewer with playback + grouping)  */
/* ------------------------------------------------------------------ */

const STREAM_HEAD = 200;
const STREAM_TAIL = 200;
const PLAYBACK_MAX = 1000;
const SPEEDS = [1, 2, 4] as const;

export function StreamSection({ meta, events, breakdown, blobStreamState }: { meta: Dict; events?: Dict[]; breakdown?: LatencyBreakdown; blobStreamState?: BlobStreamState }) {
  const [expanded, setExpanded] = useState(false);
  const [raw, setRaw] = useState(false);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [visibleCount, setVisibleCount] = useState<number | null>(null);
  const [speedIdx, setSpeedIdx] = useState(0);
  const speed = SPEEDS[speedIdx];
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const effectiveEvents = useMemo(() => events ?? [], [events]);
  const hasEvents = effectiveEvents.length > 0;
  const totalEvents = hasEvents ? effectiveEvents.length : (typeof meta.chunk_count === "number" ? meta.chunk_count : 0);
  const tooLargeForPlayback = effectiveEvents.length > PLAYBACK_MAX;
  const inPlaybackMode = visibleCount !== null;

  const rawPayload = hasEvents ? { provider: meta.provider, model: meta.model, events: effectiveEvents } : meta;
  const rawText = JSON.stringify(rawPayload, null, 2);

  // Cleanup timers on unmount
  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  // Playback interval
  useEffect(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (!isPlaying || !hasEvents) return;

    const interval = Math.max(10, Math.round(40 / speed));
    timerRef.current = setInterval(() => {
      setVisibleCount((prev) => {
        const next = (prev ?? 0) + 1;
        if (next >= effectiveEvents.length) {
          setIsPlaying(false);
          return effectiveEvents.length;
        }
        return next;
      });
    }, interval);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isPlaying, speed, hasEvents, effectiveEvents.length]);

  // Auto-scroll during playback
  useEffect(() => {
    if (isPlaying && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [visibleCount, isPlaying]);

  const handlePlay = useCallback(() => {
    if (visibleCount === null || visibleCount >= effectiveEvents.length) setVisibleCount(0);
    setIsPlaying(true);
  }, [visibleCount, effectiveEvents.length]);

  const handlePause = useCallback(() => setIsPlaying(false), []);
  const handleReset = useCallback(() => { setIsPlaying(false); setVisibleCount(null); }, []);
  const handleSpeed = useCallback(() => setSpeedIdx((i) => (i + 1) % SPEEDS.length), []);

  // Compute visible events and grouped display items
  const showCount = inPlaybackMode ? (visibleCount ?? 0) : effectiveEvents.length;
  const visibleEvents = effectiveEvents.slice(0, showCount);

  const displayItems = useMemo(() => groupStreamEvents(visibleEvents), [visibleEvents]);

  // Truncation (normal mode only — not during playback)
  const useTruncation = !inPlaybackMode && effectiveEvents.length > STREAM_HEAD + STREAM_TAIL;
  const skipped = useTruncation ? effectiveEvents.length - STREAM_HEAD - STREAM_TAIL : 0;

  const headItems = useMemo(
    () => useTruncation ? groupStreamEvents(effectiveEvents.slice(0, STREAM_HEAD)) : null,
    [useTruncation, effectiveEvents],
  );
  const tailItems = useMemo(
    () => useTruncation ? groupStreamEvents(effectiveEvents.slice(-STREAM_TAIL)) : null,
    [useTruncation, effectiveEvents],
  );
  const tailBaseIdx = useTruncation ? effectiveEvents.length - STREAM_TAIL : 0;

  const playbackDone = inPlaybackMode && !isPlaying && visibleCount !== null && visibleCount >= effectiveEvents.length;

  return (
    <div className="rounded-md border border-neutral-200">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-2 text-left"
      >
        <div className="flex items-center gap-2">
          <span className={`text-[10px] transition-transform duration-150 ${expanded ? "rotate-90" : ""} text-neutral-400`}>▶</span>
          <span className="text-[11px] font-medium text-neutral-500">Stream</span>
          <span className="text-[10px] tabular-nums text-neutral-400">{totalEvents} events</span>
          {typeof meta.termination === "string" && (
            <span className={`text-[10px] ${meta.termination === "failed" ? "text-red-400" : "text-neutral-400"}`}>
              {meta.termination as string}
            </span>
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-neutral-200">
          {/* Toolbar */}
          <div className="flex items-center justify-between gap-2 px-4 pt-2 pb-1">
            <div className="flex items-center gap-1">
              {hasEvents && !tooLargeForPlayback && (
                <>
                  {isPlaying ? (
                    <CtrlBtn label="⏸" title="Pause" onClick={handlePause} />
                  ) : (
                    <CtrlBtn label="▶" title="Play" onClick={handlePlay} active />
                  )}
                  {inPlaybackMode && (
                    <CtrlBtn label="⟲" title="Reset" onClick={handleReset} />
                  )}
                  <CtrlBtn label={`${speed}x`} title="Speed" onClick={handleSpeed} />
                </>
              )}
              {tooLargeForPlayback && (
                <span className="text-[10px] italic text-neutral-400">Playback disabled for large streams</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <CopyBtn text={rawText} />
              <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
            </div>
          </div>

          {/* Latency summary */}
          {breakdown?.is_available && <StreamLatencySummary breakdown={breakdown} />}

          {/* Playback progress */}
          {inPlaybackMode && hasEvents && (
            <div className="mx-4 mb-1 h-[2px] rounded-full bg-neutral-200">
              <div
                className="h-full rounded-full bg-violet-400 transition-[width] duration-75"
                style={{ width: `${Math.min(100, (showCount / effectiveEvents.length) * 100)}%` }}
              />
            </div>
          )}

          {/* Content */}
          {raw ? (
            <pre className="mx-4 mb-3 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 px-3 py-2 font-mono text-xs leading-6 text-neutral-600">
              {rawText}
            </pre>
          ) : hasEvents ? (
            <div ref={scrollRef} className="max-h-80 overflow-auto pb-2">
              {inPlaybackMode ? (
                <>
                  {displayItems.map((item, i) => (
                    <DisplayItemRow key={i} item={item} isLast={i === displayItems.length - 1} isPlaying={isPlaying} />
                  ))}
                  {isPlaying && <BlinkingCursor />}
                  {playbackDone && (
                    <div className="px-4 py-1.5 text-center text-[10px] text-neutral-400">
                      Playback complete
                    </div>
                  )}
                </>
              ) : useTruncation && headItems && tailItems ? (
                <>
                  {headItems.map((item, i) => (
                    <DisplayItemRow key={`h-${i}`} item={item} />
                  ))}
                  <div className="px-4 py-1.5 text-center text-[10px] italic text-neutral-400">
                    … {skipped} events omitted …
                  </div>
                  {tailItems.map((item, i) => (
                    <DisplayItemRow key={`t-${i}`} item={item} baseIdx={tailBaseIdx} />
                  ))}
                </>
              ) : (
                displayItems.map((item, i) => (
                  <DisplayItemRow key={i} item={item} />
                ))
              )}
            </div>
          ) : blobStreamState && !blobStreamState.loaded ? (
            <div className="px-4 pb-3 space-y-2">
              {blobStreamState.loading ? (
                <p className="text-xs text-neutral-400">Loading stream events…</p>
              ) : blobStreamState.error ? (
                <>
                  <p className="text-xs text-red-500">{blobStreamState.error}</p>
                  <button
                    onClick={blobStreamState.onLoad}
                    className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50 hover:text-neutral-700"
                  >
                    Retry
                  </button>
                </>
              ) : (
                <>
                  <p className="text-xs text-neutral-400">Stream events stored as blob</p>
                  <button
                    onClick={blobStreamState.onLoad}
                    className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50 hover:text-neutral-700"
                  >
                    Load stream events
                  </button>
                </>
              )}
            </div>
          ) : (
            <p className="px-4 pb-3 text-xs italic text-neutral-400">
              Stream recorded but no events captured
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Playback control button                                             */
/* ------------------------------------------------------------------ */

function CtrlBtn({ label, title, onClick, active }: { label: string; title: string; onClick: () => void; active?: boolean }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title={title}
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
        active
          ? "bg-violet-100 text-violet-600 hover:bg-violet-200 dark:bg-violet-900/30 dark:text-violet-400 dark:hover:bg-violet-900/50"
          : "text-neutral-400 hover:bg-neutral-200 hover:text-neutral-600"
      }`}
    >
      {label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Blinking cursor (during playback)                                   */
/* ------------------------------------------------------------------ */

function BlinkingCursor() {
  return (
    <div className="flex items-center px-4 py-[3px]">
      <span className="inline-block h-3.5 w-[2px] animate-pulse bg-violet-400 dark:bg-violet-500" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Display item dispatcher                                             */
/* ------------------------------------------------------------------ */

function DisplayItemRow({ item, isLast, isPlaying, baseIdx = 0 }: { item: DisplayItem; isLast?: boolean; isPlaying?: boolean; baseIdx?: number }) {
  const highlight = isLast && isPlaying;

  switch (item.kind) {
    case "text_group":
      return <TextGroupRow item={item} highlight={highlight} baseIdx={baseIdx} />;
    case "tool_call_group":
      return <ToolCallGroupRow item={item} highlight={highlight} baseIdx={baseIdx} />;
    case "event":
      return <StreamEventRow event={item.event} idx={item.idx + baseIdx} offset={item.offset} highlight={highlight} />;
  }
}

/* ------------------------------------------------------------------ */
/* Text group row (merged consecutive text_deltas)                     */
/* ------------------------------------------------------------------ */

function TextGroupRow({ item, highlight, baseIdx = 0 }: { item: Extract<DisplayItem, { kind: "text_group" }>; highlight?: boolean; baseIdx?: number }) {
  const timeLabel = item.firstOffset != null && item.lastOffset != null
    ? `+${item.firstOffset}–${item.lastOffset}ms`
    : item.firstOffset != null ? `+${item.firstOffset}ms` : null;

  return (
    <div className={`mx-3 my-1 rounded-md px-3 py-2 transition-colors ${highlight ? "bg-emerald-50/80 dark:bg-emerald-950/30" : "bg-emerald-50/40 dark:bg-emerald-950/15"}`}>
      <div className="mb-1 flex items-center gap-2">
        <span className="rounded bg-emerald-100 px-1 py-px text-[9px] font-medium text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400">
          text
        </span>
        <span className="text-[10px] tabular-nums text-neutral-400">
          #{item.startIdx + baseIdx}–{item.startIdx + baseIdx + item.count - 1}
        </span>
        <span className="text-[10px] text-neutral-400">{item.count} chunks</span>
        {timeLabel && <span className="text-[10px] tabular-nums text-neutral-300">{timeLabel}</span>}
      </div>
      <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-neutral-700">
        {item.text || '""'}
      </pre>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Tool call group row (merged consecutive tool_call_deltas)           */
/* ------------------------------------------------------------------ */

function ToolCallGroupRow({ item, highlight, baseIdx = 0 }: { item: Extract<DisplayItem, { kind: "tool_call_group" }>; highlight?: boolean; baseIdx?: number }) {
  const [open, setOpen] = useState(false);
  const timeLabel = item.firstOffset != null && item.lastOffset != null
    ? `+${item.firstOffset}–${item.lastOffset}ms`
    : item.firstOffset != null ? `+${item.firstOffset}ms` : null;

  let prettyArgs: string | null = null;
  if (item.args) {
    try {
      prettyArgs = JSON.stringify(JSON.parse(item.args), null, 2);
    } catch {
      prettyArgs = item.args;
    }
  }

  return (
    <div className={`mx-3 my-1 rounded-md px-3 py-2 transition-colors ${highlight ? "bg-amber-50/80 dark:bg-amber-950/30" : "bg-amber-50/40 dark:bg-amber-950/15"}`}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
        <span className={`text-[9px] transition-transform duration-100 ${open ? "rotate-90" : ""} text-neutral-400`}>▶</span>
        <span className="rounded bg-amber-100 px-1 py-px text-[9px] font-medium text-amber-600 dark:bg-amber-900/40 dark:text-amber-400">
          tool call
        </span>
        {item.name && (
          <span className="text-[11px] font-semibold text-neutral-800 dark:text-neutral-200">{item.name}</span>
        )}
        <span className="text-[10px] tabular-nums text-neutral-400">
          #{item.startIdx + baseIdx}–{item.startIdx + baseIdx + item.count - 1}
        </span>
        <span className="text-[10px] text-neutral-400">{item.count} chunks</span>
        {timeLabel && <span className="text-[10px] tabular-nums text-neutral-300">{timeLabel}</span>}
      </button>
      {open && prettyArgs && (
        <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-white/60 px-2 py-1.5 font-mono text-[11px] leading-5 text-neutral-600">
          {prettyArgs}
        </pre>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stream event row (single ungrouped event)                           */
/* ------------------------------------------------------------------ */

const EVENT_TYPE_STYLES: Record<string, string> = {
  text_delta: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400",
  tool_call_delta: "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400",
  message_start: "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400",
  message_stop: "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400",
  usage: "bg-neutral-100 text-neutral-500",
  unknown: "bg-neutral-100 text-neutral-400",
};

function StreamEventRow({ event, idx, offset, highlight }: { event: Dict; idx: number; offset?: number | null; highlight?: boolean }) {
  const type = String(event.type ?? "");
  const off = offset ?? (typeof event.timestamp_offset_ms === "number" ? event.timestamp_offset_ms : null);
  const badgeStyle = EVENT_TYPE_STYLES[type] ?? EVENT_TYPE_STYLES.unknown;

  return (
    <div className={`flex items-baseline gap-2 px-4 py-[3px] font-mono text-[11px] transition-colors ${highlight ? "bg-violet-50/60 dark:bg-violet-950/25" : "hover:bg-neutral-100"}`}>
      <span className="w-5 shrink-0 text-right tabular-nums text-neutral-300">{idx}</span>
      <span className={`shrink-0 rounded px-1 py-px text-[9px] font-medium ${badgeStyle}`}>
        {type.replace(/_/g, " ")}
      </span>
      {off != null && (
        <span className="shrink-0 tabular-nums text-neutral-300">+{off}ms</span>
      )}
      <span className="min-w-0 flex-1 truncate text-neutral-600 dark:text-neutral-400">
        {eventPreview(type, event)}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Event preview helpers                                               */
/* ------------------------------------------------------------------ */

function compactJsonFragment(fragment: string, max: number): string {
  try {
    const parsed = JSON.parse(fragment);
    const compact = JSON.stringify(parsed)
      .replace(/"(\w+)":/g, "$1: ")
      .replace(/"/g, '\u201c');
    return compact.length > max ? compact.slice(0, max) + "…" : compact;
  } catch {
    return fragment.length > max ? fragment.slice(0, max) + "…" : fragment;
  }
}

function eventPreview(type: string, ev: Dict): string {
  switch (type) {
    case "text_delta": {
      const text = typeof ev.text === "string" ? ev.text : "";
      return text.length > 120 ? text.slice(0, 120) + "…" : text || '""';
    }
    case "tool_call_delta": {
      const parts: string[] = [];
      if (typeof ev.tool_index === "number") parts.push(`tool[${ev.tool_index}]`);
      if (typeof ev.name === "string" && ev.name) parts.push(`name=${ev.name}`);
      if (typeof ev.arguments === "string" && ev.arguments) {
        parts.push(`args=${compactJsonFragment(ev.arguments, 80)}`);
      }
      return parts.join(" ") || "delta";
    }
    case "message_start": {
      const parts: string[] = ["start"];
      if (typeof ev.request_id === "string") parts.push(`id=${ev.request_id}`);
      return parts.join(" ");
    }
    case "message_stop": {
      const parts: string[] = ["stop"];
      if (typeof ev.finish_reason === "string") parts.push(`(${ev.finish_reason})`);
      return parts.join(" ");
    }
    case "usage": {
      const parts: string[] = [];
      if (typeof ev.prompt_tokens === "number") parts.push(`in=${ev.prompt_tokens}`);
      if (typeof ev.completion_tokens === "number") parts.push(`out=${ev.completion_tokens}`);
      if (typeof ev.total_tokens === "number") parts.push(`total=${ev.total_tokens}`);
      return parts.length > 0 ? parts.join(" ") : "usage";
    }
    default: {
      const { index: _i, type: _t, timestamp_offset_ms: _ts, ...rest } = ev;
      const keys = Object.keys(rest);
      if (keys.length === 0) return type || "event";
      const preview = JSON.stringify(rest);
      return preview.length > 120 ? preview.slice(0, 120) + "…" : preview;
    }
  }
}

/* ------------------------------------------------------------------ */
/* Error section (for failed LLM steps)                                */
/* ------------------------------------------------------------------ */

function ErrorSection({ data }: { data: Dict }) {
  const [expanded, setExpanded] = useState(false);
  const headline = errorHeadline(data);
  const detail = errorDetail(data);
  const raw = rawJson(data);
  if (!headline && !raw) return null;

  return (
    <div className="rounded-md bg-[var(--tint-error)] px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--error-accent)]">
          Error
        </span>
        <CopyBtn text={detail ?? headline} />
      </div>
      <p className="font-mono text-[13px] font-medium leading-snug text-[var(--error-text-emphasis)]">
        {headline}
      </p>
      {detail && detail !== headline && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-2 text-[11px] font-medium text-[var(--error-accent)] hover:text-[var(--error-text)]"
          >
            {expanded ? "Hide full traceback" : "Show full traceback"}
          </button>
          {expanded && (
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-[var(--error-text-muted)]">
              {detail}
            </pre>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Usage row                                                           */
/* ------------------------------------------------------------------ */

function UsageRow({
  usage,
}: {
  usage: { prompt_tokens: number | null; completion_tokens: number | null; total_tokens: number | null };
}) {
  const items: { label: string; value: number }[] = [];
  if (usage.prompt_tokens != null) items.push({ label: "prompt", value: usage.prompt_tokens });
  if (usage.completion_tokens != null) items.push({ label: "completion", value: usage.completion_tokens });
  if (usage.total_tokens != null) items.push({ label: "total", value: usage.total_tokens });
  if (items.length === 0) return null;

  return (
    <div className="flex items-center gap-3 rounded-md bg-neutral-50/60 px-4 py-2 text-[11px]">
      <span className="text-[10px] font-medium uppercase tracking-wider text-neutral-400">
        Tokens
      </span>
      <span className="text-neutral-200">·</span>
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

/* ------------------------------------------------------------------ */
/* Artifact list for LLM steps (excludes llm_stream)                   */
/* ------------------------------------------------------------------ */

function LlmArtifactList({ artifacts }: { artifacts: StepArtifactRef[] }) {
  const filtered = useMemo(
    () => artifacts.filter((a) => a.kind !== "llm_stream"),
    [artifacts],
  );
  const [expanded, setExpanded] = useState(false);

  if (filtered.length === 0) return null;

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] text-neutral-400 transition-colors hover:text-neutral-600"
      >
        <span className={`text-[9px] transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}>▶</span>
        <span className="font-medium">Artifacts</span>
        <span className="tabular-nums">{filtered.length}</span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {filtered.map((a) => (
            <ArtifactViewer key={a.id} artifact={a} />
          ))}
        </div>
      )}
    </div>
  );
}
