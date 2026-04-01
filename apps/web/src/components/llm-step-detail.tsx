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
function tryParseJson(text: string): unknown | null {
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
function resolveArgs(args: unknown): unknown {
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
}: {
  llm: LLMShape;
  errorSummary?: Dict | null;
  toolCallLinks?: Map<string, ToolCallLinkInfo>;
  onJumpToStep?: (stepId: string) => void;
}) {
  const [raw, setRaw] = useState(false);
  const rawText = JSON.stringify(llm, null, 2);

  const hasInput = !!llm.input.system || llm.input.messages.length > 0 || llm.input.tools.length > 0 || Object.keys(llm.input.params).length > 0;
  const hasOutputText = !!llm.output.text;
  const hasToolCalls = llm.output.tool_calls.length > 0;
  const hasOutput = hasOutputText || hasToolCalls;
  const hasError = errorSummary && Object.keys(errorSummary).length > 0;

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
