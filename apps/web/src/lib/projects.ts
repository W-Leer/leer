import type { ProjectSummary } from "@/lib/types";

export const PROJECT_STORAGE_KEY = "leer-project";

/**
 * The project to show: the first preferred slug that exists, otherwise the
 * first project (the API orders projects by most recent run). `null` when
 * there are no projects yet.
 */
export function resolveProjectSlug(
  projects: ProjectSummary[],
  preferred: (string | null | undefined)[],
): string | null {
  const known = new Set(projects.map((p) => p.slug));
  const match = preferred.find((slug): slug is string => !!slug && known.has(slug));
  return match ?? projects[0]?.slug ?? null;
}

/** `path` with `?project=` set, keeping its other query params. */
export function withProjectParam(path: string, slug: string | null): string {
  const [base, query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  if (slug) params.set("project", slug);
  else params.delete("project");
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}
