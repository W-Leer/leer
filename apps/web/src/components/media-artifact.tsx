"use client";

import { useState } from "react";
import { artifactContentUrl } from "@/lib/api";
import type { StepArtifactRef } from "@/lib/types";

// ---------------------------------------------------------------------------
// Classification helpers
// ---------------------------------------------------------------------------

const IMAGE_MIMES = new Set([
  "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
  "image/bmp", "image/tiff",
]);

const DOC_MIMES = new Set(["application/pdf"]);

export function isImageArtifact(a: StepArtifactRef): boolean {
  if (a.mime_type && IMAGE_MIMES.has(a.mime_type)) return true;
  if (a.mime_type?.startsWith("image/")) return true;
  if (a.kind === "output_image") return true;
  return false;
}

export function isDocumentArtifact(a: StepArtifactRef): boolean {
  if (a.mime_type && DOC_MIMES.has(a.mime_type)) return true;
  if (a.kind === "output_document") return true;
  return false;
}

export function isMediaArtifact(a: StepArtifactRef): boolean {
  return isImageArtifact(a) || isDocumentArtifact(a) ||
    (a.format === "binary" && a.mime_type != null);
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function mimeLabel(mime: string | null): string {
  if (!mime) return "FILE";
  const sub = mime.split("/")[1] ?? mime;
  return sub.toUpperCase();
}

// ---------------------------------------------------------------------------
// Shared artifact header
// ---------------------------------------------------------------------------

function ArtifactHeader({
  badge,
  badgeColor,
  artifact,
}: {
  badge: string;
  badgeColor: string;
  artifact: StepArtifactRef;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 px-3 py-2 text-[11px]">
      <span className={`shrink-0 rounded px-1.5 py-px text-[9px] font-medium ${badgeColor}`}>
        {badge}
      </span>
      <span className="min-w-0 truncate font-mono font-medium text-neutral-600">
        {artifact.filename ?? artifact.kind}
      </span>
      {artifact.mime_type && (
        <span className="shrink-0 text-[10px] text-neutral-400">{artifact.mime_type}</span>
      )}
      {artifact.size_bytes != null && (
        <span className="shrink-0 text-[10px] tabular-nums text-neutral-400">
          {formatBytes(artifact.size_bytes)}
        </span>
      )}
      {artifact.storage_kind === "blob" && (
        <span className="shrink-0 rounded bg-indigo-50 px-1.5 py-px text-[9px] font-medium text-indigo-500">
          blob
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ImageArtifactPreview
// ---------------------------------------------------------------------------

export function ImageArtifactPreview({ artifact }: { artifact: StepArtifactRef }) {
  const [state, setState] = useState<"loading" | "loaded" | "error">("loading");
  const src = artifactContentUrl(artifact.id);

  return (
    <div className="overflow-hidden rounded-md border border-neutral-200 bg-white">
      <ArtifactHeader badge="IMG" badgeColor="bg-violet-50 text-violet-600" artifact={artifact} />
      <div className="border-t border-neutral-100 bg-neutral-50 p-3">
        {state === "error" ? (
          <div className="flex items-center gap-2 py-2">
            <span className="text-xs text-red-500">Failed to load image</span>
            <button
              onClick={() => setState("loading")}
              className="rounded border border-neutral-200 px-2 py-0.5 text-[10px] font-medium text-neutral-500 hover:bg-neutral-100"
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="relative">
            {state === "loading" && (
              <div className="flex h-16 items-center justify-center">
                <span className="text-xs text-neutral-400">Loading image…</span>
              </div>
            )}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={src}
              alt={artifact.preview_text ?? artifact.filename ?? "image artifact"}
              className={`max-h-[480px] max-w-full rounded object-contain ${state === "loading" ? "absolute opacity-0" : ""}`}
              onLoad={() => setState("loaded")}
              onError={() => setState("error")}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DocumentArtifactPreview
// ---------------------------------------------------------------------------

export function DocumentArtifactPreview({ artifact }: { artifact: StepArtifactRef }) {
  const src = artifactContentUrl(artifact.id);
  const [showEmbed, setShowEmbed] = useState(false);

  return (
    <div className="overflow-hidden rounded-md border border-neutral-200 bg-white">
      <ArtifactHeader badge="PDF" badgeColor="bg-orange-50 text-orange-600" artifact={artifact} />
      <div className="space-y-2 border-t border-neutral-100 px-3 py-2">
        <div className="flex gap-2">
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-600 transition-colors hover:border-neutral-300 hover:bg-neutral-50"
          >
            Open
          </a>
          <button
            onClick={() => setShowEmbed(!showEmbed)}
            className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50"
          >
            {showEmbed ? "Hide preview" : "Preview"}
          </button>
        </div>
        {showEmbed && (
          <div className="overflow-hidden rounded border border-neutral-200">
            <object
              data={src}
              type="application/pdf"
              className="h-[480px] w-full"
            >
              <div className="flex flex-col items-center gap-2 p-6 text-center">
                <p className="text-xs text-neutral-400">
                  PDF preview not supported in this browser.
                </p>
                <a
                  href={src}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md border border-neutral-200 px-3 py-1.5 text-[11px] font-medium text-neutral-600 transition-colors hover:border-neutral-300 hover:bg-neutral-50"
                >
                  Open PDF directly
                </a>
              </div>
            </object>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// GenericMediaArtifactCard
// ---------------------------------------------------------------------------

export function GenericMediaArtifactCard({ artifact }: { artifact: StepArtifactRef }) {
  const src = artifactContentUrl(artifact.id);

  return (
    <div className="overflow-hidden rounded-md border border-neutral-200 bg-white">
      <div className="flex min-w-0 items-center justify-between gap-2 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2 text-[11px]">
          <span className="shrink-0 rounded bg-neutral-100 px-1.5 py-px text-[9px] font-medium text-neutral-500">
            {mimeLabel(artifact.mime_type)}
          </span>
          <span className="min-w-0 truncate font-mono font-medium text-neutral-600">
            {artifact.filename ?? artifact.kind}
          </span>
          {artifact.mime_type && (
            <span className="shrink-0 text-[10px] text-neutral-400">{artifact.mime_type}</span>
          )}
          {artifact.size_bytes != null && (
            <span className="shrink-0 text-[10px] tabular-nums text-neutral-400">
              {formatBytes(artifact.size_bytes)}
            </span>
          )}
          {artifact.storage_kind === "blob" && (
            <span className="shrink-0 rounded bg-indigo-50 px-1.5 py-px text-[9px] font-medium text-indigo-500">
              blob
            </span>
          )}
        </div>
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 rounded-md border border-neutral-200 px-2.5 py-1 text-[10px] font-medium text-neutral-500 transition-colors hover:border-neutral-300 hover:bg-neutral-50 hover:text-neutral-700"
        >
          Open
        </a>
      </div>
      {artifact.preview_text && (
        <div className="border-t border-neutral-100 px-3 py-1.5">
          <p className="truncate font-mono text-[10px] text-neutral-400">{artifact.preview_text}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Smart dispatcher: picks the right renderer
// ---------------------------------------------------------------------------

export function MediaArtifactRenderer({ artifact }: { artifact: StepArtifactRef }) {
  if (isImageArtifact(artifact)) {
    return <ImageArtifactPreview artifact={artifact} />;
  }
  if (isDocumentArtifact(artifact)) {
    return <DocumentArtifactPreview artifact={artifact} />;
  }
  return <GenericMediaArtifactCard artifact={artifact} />;
}

// ---------------------------------------------------------------------------
// ContentBlockRow — renders a canonical content block from LLM output
// ---------------------------------------------------------------------------

interface ContentBlockRowProps {
  block: Record<string, unknown>;
  artifacts: StepArtifactRef[];
}

export function ContentBlockRow({ block, artifacts }: ContentBlockRowProps) {
  const type = block.type as string | undefined;

  if (type === "text" || type === "thinking" || type === "redacted_thinking" || type === "tool_call") {
    return null;
  }

  const artifactId = block.artifact_id as string | undefined;
  const matchedArtifact = artifactId
    ? artifacts.find((a) => a.id === artifactId)
    : undefined;

  if (matchedArtifact) {
    return <MediaArtifactRenderer artifact={matchedArtifact} />;
  }

  const mime = block.mime_type as string | undefined;
  const filename = block.filename as string | undefined;
  const previewText = block.preview_text as string | undefined;

  return (
    <div className="overflow-hidden rounded-md border border-neutral-200 bg-white px-3 py-2">
      <div className="flex min-w-0 items-center gap-2 text-[11px]">
        <span className="shrink-0 rounded bg-neutral-100 px-1.5 py-px text-[9px] font-medium text-neutral-500">
          {(type ?? "media").toUpperCase()}
        </span>
        {filename && (
          <span className="min-w-0 truncate font-mono font-medium text-neutral-600">{filename}</span>
        )}
        {mime && (
          <span className="shrink-0 text-[10px] text-neutral-400">{mime}</span>
        )}
      </div>
      {previewText && (
        <p className="mt-1 truncate font-mono text-[10px] text-neutral-400">{previewText}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CompareMediaBadge — compact media badge for compare page
// ---------------------------------------------------------------------------

export function CompareMediaBadge({ block }: { block: Record<string, unknown> }) {
  const t = (block.type as string) ?? "media";
  const fname = block.filename as string | undefined;
  const mime = typeof block.mime_type === "string" ? block.mime_type : undefined;

  const badgeColors: Record<string, string> = {
    image: "bg-violet-50 text-violet-600",
    document: "bg-orange-50 text-orange-600",
    file: "bg-neutral-100 text-neutral-500",
  };

  return (
    <div className="flex min-w-0 items-center gap-1.5 rounded bg-neutral-50 px-2 py-1 text-[10px]">
      <span className={`shrink-0 rounded px-1 py-px text-[9px] font-medium ${badgeColors[t] ?? "bg-neutral-200 text-neutral-500"}`}>
        {t.toUpperCase()}
      </span>
      {fname && <span className="min-w-0 truncate font-mono text-neutral-600">{fname}</span>}
      {mime && <span className="shrink-0 text-neutral-400">{mime}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InputMediaMarker — compact badge for multimodal user input content
// ---------------------------------------------------------------------------

export function InputMediaMarker({ block }: { block: Record<string, unknown> }) {
  const type = block.type as string | undefined;

  if (!type || type === "text" || type === "input_text") return null;

  let label: string;
  if (type === "image_url" || type === "image" || type === "input_image") {
    label = "image";
  } else if (type === "document" || type === "input_pdf") {
    const fname = (block.filename as string) || (block.name as string) || "";
    label = fname ? `doc: ${fname}` : "document";
  } else if (type === "file" || type === "input_file") {
    const fname = (block.filename as string) || "";
    label = fname ? `file: ${fname}` : "file";
  } else {
    label = type;
  }

  return (
    <span className="inline-flex max-w-[200px] items-center truncate rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600">
      {label}
    </span>
  );
}
