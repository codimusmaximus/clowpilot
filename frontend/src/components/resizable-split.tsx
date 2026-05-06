"use client";

import { useCallback, useRef, useState } from "react";

export function ResizableSplit({
  left,
  right,
  defaultLeftPct = 42,
  minLeftPct = 22,
  maxLeftPct = 75,
}: {
  left: React.ReactNode;
  right: React.ReactNode;
  defaultLeftPct?: number;
  minLeftPct?: number;
  maxLeftPct?: number;
}) {
  const [leftPct, setLeftPct] = useState(defaultLeftPct);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;

      const onMove = (me: MouseEvent) => {
        if (!dragging.current || !containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const pct = ((me.clientX - rect.left) / rect.width) * 100;
        setLeftPct(Math.min(Math.max(pct, minLeftPct), maxLeftPct));
      };

      const onUp = () => {
        dragging.current = false;
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    },
    [minLeftPct, maxLeftPct]
  );

  return (
    <div ref={containerRef} className="flex h-full min-h-0 min-w-0 flex-1">
      <div className="min-h-0 min-w-0 overflow-hidden" style={{ width: `${leftPct}%` }}>
        {left}
      </div>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize chat and workspace"
        className="group relative z-10 flex w-1 shrink-0 cursor-col-resize items-center justify-center"
        onMouseDown={onMouseDown}
      >
        <div className="h-full w-px bg-rule transition-colors group-hover:bg-ember/40 group-active:bg-ember/60" />
        <div className="pointer-events-none absolute flex h-8 w-3 flex-col items-center justify-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
          <span className="h-4 w-px rounded-full bg-ember/60" />
        </div>
      </div>

      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        {right}
      </div>
    </div>
  );
}
