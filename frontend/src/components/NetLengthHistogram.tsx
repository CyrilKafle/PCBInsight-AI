import { useMemo } from "react";
import { netLength } from "../geometry";
import type { Board } from "../types";

const BUCKET_COUNT = 8;
const BAR_AREA_PX = 140;
const LABEL_PX = 18;

// Distribution of routed net lengths. Long nets are a signal-integrity smell
// (propagation delay, antenna behaviour), so seeing the tail at a glance is
// useful; this is purely descriptive over the parsed geometry.
export function NetLengthHistogram({ board }: { board: Board }) {
  const { buckets, maxCount, longest } = useMemo(() => {
    const lengths = board.nets.map(netLength).filter((length) => length > 0);
    if (lengths.length === 0) {
      return { buckets: [], maxCount: 0, longest: 0 };
    }
    const max = Math.max(...lengths);
    const bucketCount = Math.min(BUCKET_COUNT, lengths.length);
    const width = max / bucketCount || 1;
    const counts = new Array(bucketCount).fill(0);
    for (const length of lengths) {
      const index = Math.min(bucketCount - 1, Math.floor(length / width));
      counts[index] += 1;
    }
    return {
      buckets: counts.map((count, i) => ({ count, from: i * width, to: (i + 1) * width })),
      maxCount: Math.max(...counts),
      longest: max,
    };
  }, [board]);

  if (buckets.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6 text-center text-sm text-neutral-500">
        No routed nets to chart.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">Net length distribution</h3>
      <p className="mt-1 text-xs text-neutral-500">Longest routed net: {longest.toFixed(1)} mm</p>
      <div className="mt-4 flex items-end gap-1.5" style={{ height: BAR_AREA_PX + LABEL_PX }}>
        {buckets.map((bucket, index) => {
          const barPx = maxCount ? (bucket.count / maxCount) * BAR_AREA_PX : 0;
          return (
            <div
              key={index}
              className="flex flex-1 flex-col items-center justify-end gap-1"
              title={`${bucket.count} net(s), ${bucket.from.toFixed(1)}–${bucket.to.toFixed(1)} mm`}
            >
              <span className="text-xs text-neutral-400" style={{ height: LABEL_PX }}>
                {bucket.count || ""}
              </span>
              <div
                className="w-full rounded-t bg-blue-600"
                style={{ height: Math.max(barPx, bucket.count ? 4 : 0) }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-neutral-600">
        <span>0 mm</span>
        <span>{longest.toFixed(0)} mm</span>
      </div>
    </div>
  );
}
