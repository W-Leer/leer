"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const LINE_THRESHOLD = 16;
const CHAR_THRESHOLD = 2000;
const COLLAPSED_MAX_HEIGHT = 256;

function isLongText(text: string): boolean {
  if (text.length > CHAR_THRESHOLD) return true;
  let newlines = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "\n" && ++newlines >= LINE_THRESHOLD) return true;
  }
  return false;
}

export function ExpandableTextBlock({
  text,
  forceExpanded,
}: {
  text: string;
  /** When true (e.g. Raw mode), always show full content. */
  forceExpanded?: boolean;
}) {
  const shouldClamp = !forceExpanded && isLongText(text);
  const [expanded, setExpanded] = useState(false);
  const [needsClamp, setNeedsClamp] = useState(shouldClamp);
  const preRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (!shouldClamp) {
      setNeedsClamp(false);
      return;
    }
    const el = preRef.current;
    if (el) {
      setNeedsClamp(el.scrollHeight > COLLAPSED_MAX_HEIGHT + 24);
    }
  }, [text, shouldClamp]);

  const toggle = useCallback(() => setExpanded((v) => !v), []);

  if (!shouldClamp || forceExpanded) {
    return (
      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700">
        {text}
      </pre>
    );
  }

  const collapsed = needsClamp && !expanded;

  return (
    <div className="relative">
      <pre
        ref={preRef}
        className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-700 transition-[max-height] duration-200"
        style={collapsed ? { maxHeight: COLLAPSED_MAX_HEIGHT, overflow: "hidden" } : undefined}
      >
        {text}
      </pre>

      {collapsed && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-white/90 to-transparent dark:from-neutral-900/90" />
      )}

      {needsClamp && (
        <button
          onClick={toggle}
          className={`relative z-10 mt-1.5 text-[11px] font-medium transition-colors ${
            collapsed
              ? "text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
              : "text-neutral-400 hover:text-neutral-600"
          }`}
        >
          {expanded ? "Show less" : "Show full output"}
        </button>
      )}
    </div>
  );
}
