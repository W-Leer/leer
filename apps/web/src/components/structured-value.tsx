"use client";

import { useState } from "react";

export function StructuredValue({ value }: { value: unknown }): React.ReactNode {
  if (value == null) return null;

  if (typeof value === "string") {
    return (
      <p className="whitespace-pre-wrap break-words font-mono text-xs leading-6 text-neutral-700">
        {value}
      </p>
    );
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return (
      <span className="font-mono text-xs text-neutral-700">{String(value)}</span>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return null;

    if (value.every((v) => typeof v === "string")) {
      return (
        <ul className="space-y-1">
          {value.map((item, i) => (
            <li key={i} className="flex gap-2 font-mono text-xs leading-6 text-neutral-700">
              <span className="select-none text-neutral-300">•</span>
              <span className="whitespace-pre-wrap break-words">{item}</span>
            </li>
          ))}
        </ul>
      );
    }

    if (value.every((v) => v && typeof v === "object" && !Array.isArray(v))) {
      return <DataTable rows={value as Record<string, unknown>[]} />;
    }

    return (
      <ul className="space-y-1.5">
        {value.map((item, i) => (
          <li key={i} className="border-l-2 border-neutral-200 pl-3">
            <StructuredValue value={item} />
          </li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return null;

    const isFlat = entries.every(([, v]) => v === null || typeof v !== "object");
    if (isFlat) return <KeyValuePairs entries={entries} />;

    return <ObjectTree entries={entries} defaultOpen={entries.length <= 4} />;
  }

  return (
    <span className="font-mono text-xs text-neutral-700">{String(value)}</span>
  );
}

function KeyValuePairs({ entries }: { entries: [string, unknown][] }) {
  return (
    <div className="space-y-1">
      {entries.map(([key, val]) => (
        <div key={key} className="flex gap-2 font-mono text-xs leading-6">
          <span className="shrink-0 text-neutral-400">{key}</span>
          <span className="text-neutral-700">{val === null ? "null" : String(val)}</span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));

  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse font-mono text-xs">
        <thead>
          <tr>
            {cols.map((col) => (
              <th key={col} className="border-b border-neutral-200 px-3 py-1.5 text-left font-medium text-neutral-400">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-neutral-100 last:border-0">
              {cols.map((col) => (
                <td key={col} className="px-3 py-1.5 text-neutral-700">
                  {row[col] === null || row[col] === undefined ? "—" : String(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ObjectTree({
  entries,
  defaultOpen = false,
}: {
  entries: [string, unknown][];
  defaultOpen?: boolean;
}) {
  return (
    <div className="space-y-1">
      {entries.map(([key, val]) => (
        <TreeNode key={key} label={key} value={val} defaultOpen={defaultOpen} />
      ))}
    </div>
  );
}

function TreeNode({
  label,
  value,
  defaultOpen,
}: {
  label: string;
  value: unknown;
  defaultOpen: boolean;
}) {
  const isComplex = value !== null && typeof value === "object";
  const [open, setOpen] = useState(defaultOpen);

  if (!isComplex) {
    return (
      <div className="flex gap-2 font-mono text-xs leading-6">
        <span className="shrink-0 text-neutral-400">{label}</span>
        <span className="text-neutral-700">{value === null ? "null" : String(value)}</span>
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 font-mono text-xs leading-6 text-neutral-400 hover:text-neutral-600"
      >
        <span className={`text-[9px] transition-transform duration-100 ${open ? "rotate-90" : ""}`}>▶</span>
        <span>{label}</span>
        <span className="text-neutral-300">
          {Array.isArray(value) ? `[${value.length}]` : `{${Object.keys(value as object).length}}`}
        </span>
      </button>
      {open && (
        <div className="ml-4 mt-1 border-l border-neutral-200 pl-3">
          <StructuredValue value={value} />
        </div>
      )}
    </div>
  );
}
