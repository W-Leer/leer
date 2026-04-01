"use client";

import { useState, useCallback } from "react";
import type { LLMShape } from "@/lib/types";
import { formatDuration, errorHeadline, errorDetail, rawJson } from "@/lib/format";
import { StructuredValue } from "@/components/structured-value";

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
      className="rounded px-1.5 py-0.5 text-[10px] text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-600"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function RawToggle({ raw, onToggle }: { raw: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-600"
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

export function LlmStepDetail({
  llm,
  errorSummary,
  toolCallLinks,
  onJumpToStep,
  streamMeta,
  streamEvents,
}: {
  llm: LLMShape;
  errorSummary?: Dict | null;
  toolCallLinks?: Map<string, ToolCallLinkInfo>;
  onJumpToStep?: (stepId: string) => void;
  streamMeta?: Dict | null;
  streamEvents?: Dict[];
}) {
  const [raw, setRaw] = useState(false);
  const rawText = JSON.stringify(llm, null, 2);

  const hasInput = !!llm.input.system || llm.input.messages.length > 0 || llm.input.tools.length > 0 || Object.keys(llm.input.params).length > 0;
  const hasOutputText = !!llm.output.text;
  const hasToolCalls = llm.output.tool_calls.length > 0;
  const hasOutput = hasOutputText || hasToolCalls;
  const hasError = errorSummary && Object.keys(errorSummary).length > 0;
  const isStream = streamMeta?.is_stream === true;

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
          {isStream && <StreamStatsRow meta={streamMeta!} />}
          {isStream && <StreamSection meta={streamMeta!} events={streamEvents} />}
          {hasError && <ErrorSection data={errorSummary!} />}
          <UsageRow usage={llm.usage} />
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
            className="rounded-md bg-amber-50/40 px-3 py-1.5 dark:bg-amber-950/10"
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
/* Stream stats row (compact inline metrics)                           */
/* ------------------------------------------------------------------ */

function StreamStatsRow({ meta }: { meta: Dict }) {
  const items: { label: string; value: string; mono?: boolean }[] = [];

  const chunks = meta.chunk_count;
  if (typeof chunks === "number") items.push({ label: "chunks", value: String(chunks), mono: true });

  const ttfc = meta.time_to_first_chunk_ms;
  if (typeof ttfc === "number") items.push({ label: "TTFC", value: formatDuration(ttfc) });

  const dur = meta.stream_duration_ms;
  if (typeof dur === "number") items.push({ label: "duration", value: formatDuration(dur) });

  const term = meta.termination;
  if (typeof term === "string") items.push({ label: "termination", value: term });

  if (meta.truncated_chunks === true) items.push({ label: "truncated", value: "yes" });

  if (items.length === 0) return null;

  return (
    <div className="flex items-center gap-3 rounded-md bg-violet-50/50 px-4 py-2 text-[11px] dark:bg-violet-950/10">
      <span className="text-[10px] font-medium uppercase tracking-wider text-violet-400 dark:text-violet-500">
        Stream
      </span>
      <span className="text-violet-200 dark:text-violet-800">·</span>
      {items.map((item) => (
        <span key={item.label} className="text-neutral-400">
          {item.label}{" "}
          <span className={`font-medium text-neutral-700 ${item.mono ? "tabular-nums" : ""}`}>
            {item.value}
          </span>
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stream section (collapsible event viewer)                           */
/* ------------------------------------------------------------------ */

const STREAM_HEAD = 200;
const STREAM_TAIL = 200;

function StreamSection({ meta, events }: { meta: Dict; events?: Dict[] }) {
  const [expanded, setExpanded] = useState(false);
  const [raw, setRaw] = useState(false);

  const totalEvents = events?.length ?? (typeof meta.chunk_count === "number" ? meta.chunk_count : 0);
  const hasEvents = events && events.length > 0;
  const isTruncatedList = hasEvents && events.length > STREAM_HEAD + STREAM_TAIL;
  const skipped = isTruncatedList ? events.length - STREAM_HEAD - STREAM_TAIL : 0;

  const rawPayload = hasEvents ? { provider: meta.provider, model: meta.model, events } : meta;
  const rawText = JSON.stringify(rawPayload, null, 2);

  return (
    <div className="rounded-md border border-neutral-100 dark:border-neutral-800">
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
        <div className="border-t border-neutral-100 dark:border-neutral-800">
          <div className="flex justify-end gap-1 px-4 pt-2 pb-1">
            <CopyBtn text={rawText} />
            <RawToggle raw={raw} onToggle={() => setRaw(!raw)} />
          </div>
          {raw ? (
            <pre className="mx-4 mb-3 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 px-3 py-2 font-mono text-xs leading-6 text-neutral-600 dark:bg-neutral-900">
              {rawText}
            </pre>
          ) : hasEvents ? (
            <div className="max-h-80 overflow-auto pb-2">
              {events.slice(0, STREAM_HEAD).map((ev, i) => (
                <StreamEventRow key={i} event={ev} idx={i} />
              ))}
              {isTruncatedList && (
                <div className="px-4 py-1.5 text-center text-[10px] italic text-neutral-400">
                  … {skipped} events omitted …
                </div>
              )}
              {isTruncatedList && events.slice(-STREAM_TAIL).map((ev, i) => (
                <StreamEventRow key={`tail-${i}`} event={ev} idx={events.length - STREAM_TAIL + i} />
              ))}
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
/* Stream event row                                                    */
/* ------------------------------------------------------------------ */

const EVENT_TYPE_STYLES: Record<string, string> = {
  text_delta: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400",
  tool_call_delta: "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400",
  message_start: "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400",
  message_stop: "bg-blue-50 text-blue-500 dark:bg-blue-950/30 dark:text-blue-400",
  usage: "bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400",
  unknown: "bg-neutral-100 text-neutral-400",
};

function StreamEventRow({ event, idx }: { event: Dict; idx: number }) {
  const type = String(event.type ?? "");
  const offset = typeof event.timestamp_offset_ms === "number" ? event.timestamp_offset_ms : null;
  const badgeStyle = EVENT_TYPE_STYLES[type] ?? EVENT_TYPE_STYLES.unknown;

  return (
    <div className="flex items-baseline gap-2 px-4 py-[3px] font-mono text-[11px] transition-colors hover:bg-neutral-50 dark:hover:bg-neutral-800/30">
      <span className="w-5 shrink-0 text-right tabular-nums text-neutral-300">{idx}</span>
      <span className={`shrink-0 rounded px-1 py-px text-[9px] font-medium ${badgeStyle}`}>
        {type.replace(/_/g, " ")}
      </span>
      {offset != null && (
        <span className="shrink-0 tabular-nums text-neutral-300">+{offset}ms</span>
      )}
      <span className="min-w-0 flex-1 truncate text-neutral-600 dark:text-neutral-400">
        {eventPreview(type, event)}
      </span>
    </div>
  );
}

function compactJsonFragment(fragment: string, max: number): string {
  try {
    const parsed = JSON.parse(fragment);
    const compact = JSON.stringify(parsed)
      .replace(/"(\w+)":/g, "$1: ")
      .replace(/"/g, '"');
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
