"use client";

import { useState } from "react";

// ---------------------------------------------------------------------------
// Public API — canonical structured-value renderer
//
// Single reusable primitive for rendering arbitrary structured data in a
// devtool-style block layout.  Accepts any JSON-safe value.
//
// Call sites pass only `value`; `defaultExpanded` is an optional override.
// ---------------------------------------------------------------------------

export function StructuredValue({
  value,
  defaultExpanded,
}: {
  value: unknown;
  defaultExpanded?: boolean;
}): React.ReactNode {
  if (value === undefined || value === null) return <NullToken />;
  if (typeof value === "boolean") return <BooleanToken value={value} />;
  if (typeof value === "number") return <NumberToken value={value} />;
  if (typeof value === "string") return <StringBlock value={value} />;
  if (Array.isArray(value)) return <ArrayBlock items={value} expand={defaultExpanded} />;
  if (typeof value === "object") {
    return <ObjectBlock obj={value as Record<string, unknown>} expand={defaultExpanded} />;
  }
  return <span className="font-mono text-xs text-neutral-500">{String(value)}</span>;
}

// ---------------------------------------------------------------------------
// Scalar tokens — self-contained (include font-mono text-xs)
// ---------------------------------------------------------------------------

function NullToken() {
  return <span className="font-mono text-xs italic text-neutral-400">null</span>;
}

function BooleanToken({ value }: { value: boolean }) {
  return (
    <span
      className={`font-mono text-xs font-medium ${
        value
          ? "text-emerald-600 dark:text-emerald-400"
          : "text-neutral-500 dark:text-neutral-400"
      }`}
    >
      {String(value)}
    </span>
  );
}

function NumberToken({ value }: { value: number }) {
  return (
    <span className="font-mono text-xs tabular-nums text-sky-700 dark:text-sky-400">
      {String(value)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Inline scalar — inherits font-mono/text-xs from parent row context
// ---------------------------------------------------------------------------

function Scalar({ value }: { value: unknown }): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="italic text-neutral-400">null</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span
        className={`font-medium ${
          value
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-neutral-500 dark:text-neutral-400"
        }`}
      >
        {String(value)}
      </span>
    );
  }
  if (typeof value === "number") {
    return (
      <span className="tabular-nums text-sky-700 dark:text-sky-400">
        {String(value)}
      </span>
    );
  }
  if (typeof value === "string") {
    if (!value) return <span className="italic text-neutral-400">&quot;&quot;</span>;
    if (value.length > 100) {
      return (
        <span className="text-neutral-700 dark:text-neutral-300" title={value}>
          {value.slice(0, 100)}…
        </span>
      );
    }
    return <span className="text-neutral-700 dark:text-neutral-300">{value}</span>;
  }
  return <span className="text-neutral-500">{String(value)}</span>;
}

// ---------------------------------------------------------------------------
// Strings
// ---------------------------------------------------------------------------

function StringBlock({ value }: { value: string }) {
  if (!value) {
    return <span className="font-mono text-xs italic text-neutral-400">&quot;&quot;</span>;
  }

  if (value.includes("\n") || value.length > 140) {
    return (
      <pre className="whitespace-pre-wrap break-words rounded bg-neutral-50 px-2.5 py-1.5 font-mono text-xs leading-relaxed text-neutral-700 dark:bg-neutral-900/50 dark:text-neutral-300">
        {value}
      </pre>
    );
  }

  return (
    <span className="whitespace-pre-wrap break-words font-mono text-xs text-neutral-700 dark:text-neutral-300">
      {value}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Arrays
// ---------------------------------------------------------------------------

function ArrayBlock({
  items,
  expand,
}: {
  items: unknown[];
  expand?: boolean;
}) {
  if (items.length === 0) {
    return <span className="font-mono text-xs italic text-neutral-400">[] empty</span>;
  }

  const allScalar = items.every((v) => v === null || typeof v !== "object");

  if (allScalar) {
    if (items.every((v) => typeof v === "string")) {
      return (
        <ul className="space-y-0.5">
          {(items as string[]).map((s, i) => (
            <li
              key={i}
              className="flex gap-2 font-mono text-xs leading-relaxed text-neutral-700 dark:text-neutral-300"
            >
              <span className="select-none text-neutral-300 dark:text-neutral-600">•</span>
              <span className="whitespace-pre-wrap break-words">{s}</span>
            </li>
          ))}
        </ul>
      );
    }

    if (items.length <= 10) {
      return (
        <div className="flex flex-wrap gap-1.5 font-mono text-xs">
          {items.map((item, i) => (
            <span
              key={i}
              className="rounded bg-neutral-50 px-1.5 py-0.5 dark:bg-neutral-800/60"
            >
              <Scalar value={item} />
            </span>
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-0.5">
        {items.map((item, i) => (
          <div key={i} className="flex gap-2 font-mono text-xs leading-6">
            <span className="w-5 shrink-0 select-none text-right tabular-nums text-neutral-300 dark:text-neutral-600">
              {i}
            </span>
            <Scalar value={item} />
          </div>
        ))}
      </div>
    );
  }

  const allObjects = items.every(
    (v) => v && typeof v === "object" && !Array.isArray(v),
  );

  if (allObjects) {
    const objs = items as Record<string, unknown>[];
    if (shouldRenderAsTable(objs)) {
      return <DataTable rows={objs} />;
    }
    return (
      <div className="space-y-2">
        {objs.map((obj, i) => (
          <div
            key={i}
            className="border-l-2 border-neutral-200 pl-3 dark:border-neutral-700"
          >
            <ObjectBlock obj={obj} expand={expand} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {items.map((item, i) => (
        <div key={i} className="flex gap-2">
          <span className="shrink-0 select-none pt-px font-mono text-[10px] tabular-nums text-neutral-300 dark:text-neutral-600">
            {i}
          </span>
          <div className="min-w-0 flex-1">
            <StructuredValue value={item} defaultExpanded={expand} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Objects
// ---------------------------------------------------------------------------

function ObjectBlock({
  obj,
  expand,
}: {
  obj: Record<string, unknown>;
  expand?: boolean;
}) {
  const entries = Object.entries(obj);

  if (entries.length === 0) {
    return (
      <span className="font-mono text-xs italic text-neutral-400">
        {"{}"} empty
      </span>
    );
  }

  const isFlat = entries.every(([, v]) => v === null || typeof v !== "object");

  if (isFlat) {
    return (
      <div className="space-y-0.5">
        {entries.map(([key, val]) => (
          <div key={key} className="flex gap-2 font-mono text-xs leading-6">
            <span className="shrink-0 text-neutral-400 dark:text-neutral-500">
              {key}
            </span>
            <span className="min-w-0">
              <Scalar value={val} />
            </span>
          </div>
        ))}
      </div>
    );
  }

  const shouldExpand = expand ?? entries.length <= 5;

  return (
    <div className="space-y-0.5">
      {entries.map(([key, val]) => {
        const isNested = val !== null && typeof val === "object";
        if (!isNested) {
          return (
            <div key={key} className="flex gap-2 font-mono text-xs leading-6">
              <span className="shrink-0 text-neutral-400 dark:text-neutral-500">
                {key}
              </span>
              <span className="min-w-0">
                <Scalar value={val} />
              </span>
            </div>
          );
        }
        return (
          <Collapsible
            key={key}
            label={key}
            value={val}
            defaultOpen={shouldExpand}
          />
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collapsible node
// ---------------------------------------------------------------------------

function Collapsible({
  label,
  value,
  defaultOpen,
}: {
  label: string;
  value: unknown;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const badge = Array.isArray(value)
    ? `[${value.length}]`
    : value && typeof value === "object"
      ? `{${Object.keys(value as object).length}}`
      : "";

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 font-mono text-xs leading-6 text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300"
      >
        <span
          className={`inline-block text-[9px] transition-transform duration-100 ${open ? "rotate-90" : ""}`}
        >
          ▶
        </span>
        <span>{label}</span>
        {badge && (
          <span className="text-neutral-300 dark:text-neutral-600">
            {badge}
          </span>
        )}
      </button>
      {open && (
        <div className="ml-3.5 mt-0.5 border-l border-neutral-200 pl-3 dark:border-neutral-700">
          <StructuredValue value={value} defaultExpanded={defaultOpen} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data table — used only for uniform scalar-valued object arrays
// ---------------------------------------------------------------------------

function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = stableColumns(rows);

  return (
    <div className="overflow-auto rounded">
      <table className="w-full border-collapse font-mono text-xs">
        <thead>
          <tr>
            {cols.map((col) => (
              <th
                key={col}
                className="border-b border-neutral-200 px-3 py-1.5 text-left font-medium text-neutral-400 dark:border-neutral-700 dark:text-neutral-500"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-neutral-100 last:border-0 dark:border-neutral-800"
            >
              {cols.map((col) => (
                <td key={col} className="px-3 py-1.5">
                  <CellValue value={row[col]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CellValue({ value }: { value: unknown }): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-neutral-300 dark:text-neutral-600">—</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span
        className={
          value
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-neutral-500 dark:text-neutral-400"
        }
      >
        {String(value)}
      </span>
    );
  }
  if (typeof value === "number") {
    return (
      <span className="tabular-nums text-sky-700 dark:text-sky-400">
        {String(value)}
      </span>
    );
  }
  if (typeof value === "string") {
    if (value.length > 60) {
      return (
        <span
          className="text-neutral-700 dark:text-neutral-300"
          title={value}
        >
          {value.slice(0, 60)}…
        </span>
      );
    }
    return (
      <span className="text-neutral-700 dark:text-neutral-300">{value}</span>
    );
  }
  const compact = JSON.stringify(value);
  if (compact.length > 50) {
    return (
      <span
        className="text-neutral-500 dark:text-neutral-400"
        title={JSON.stringify(value, null, 2)}
      >
        {compact.slice(0, 50)}…
      </span>
    );
  }
  return (
    <span className="text-neutral-500 dark:text-neutral-400">{compact}</span>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shouldRenderAsTable(objects: Record<string, unknown>[]): boolean {
  if (objects.length < 2) return false;
  if (
    objects.some((o) =>
      Object.values(o).some((v) => v !== null && typeof v === "object"),
    )
  ) {
    return false;
  }
  const keySets = objects.map((o) => new Set(Object.keys(o)));
  const union = new Set(keySets.flatMap((s) => [...s]));
  if (union.size > 10) return false;
  return keySets.every((ks) => {
    const overlap = [...union].filter((k) => ks.has(k)).length;
    return overlap / union.size >= 0.5;
  });
}

function stableColumns(rows: Record<string, unknown>[]): string[] {
  const seen = new Set<string>();
  const order: string[] = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        seen.add(key);
        order.push(key);
      }
    }
  }
  return order;
}
