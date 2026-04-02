import type { ArtifactContentResponse } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let message = `API ${res.status}: ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) message = String(body.detail);
    } catch {
      /* no JSON body */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export function fetchArtifactContent(artifactId: string): Promise<ArtifactContentResponse> {
  return apiFetch<ArtifactContentResponse>(`/v1/artifacts/${artifactId}`);
}
