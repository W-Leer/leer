export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-800",
  running: "bg-blue-100 text-blue-800",
  failed: "bg-red-100 text-red-800",
  pending: "bg-neutral-100 text-neutral-600",
};

export function statusClass(status: string): string {
  return STATUS_COLORS[status] ?? "bg-neutral-100 text-neutral-600";
}
