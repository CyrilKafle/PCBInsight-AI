// Client-side geometry helpers over the board model. These recompute simple
// derived quantities (net length, bounding box) from the same coordinates the
// backend already sent -- no new backend data, and the deterministic engine
// stays the source of any *findings*; this is presentation only.

import type { Board, Net, Point } from "./types";

export function netLength(net: Net): number {
  return net.traces.reduce(
    (sum, trace) => sum + Math.hypot(trace.end.x - trace.start.x, trace.end.y - trace.start.y),
    0,
  );
}

export interface Bounds {
  minX: number;
  minY: number;
  width: number;
  height: number;
}

// Bounding box over the board rectangle and all drawn geometry, padded a
// little so nothing sits flush against the SVG edge.
export function boardBounds(board: Board): Bounds {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  const include = (p: Point) => {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  };

  include(board.origin);
  include({ x: board.origin.x + board.width_mm, y: board.origin.y + board.height_mm });
  for (const net of board.nets) {
    for (const trace of net.traces) {
      include(trace.start);
      include(trace.end);
    }
    for (const via of net.vias) include(via.position);
  }
  for (const component of board.components) include(component.footprint.position);
  for (const pour of board.pours) for (const point of pour.outline) include(point);

  if (!Number.isFinite(minX)) {
    // Degenerate board with no geometry -- fall back to declared size.
    minX = 0;
    minY = 0;
    maxX = board.width_mm || 100;
    maxY = board.height_mm || 100;
  }

  const pad = Math.max(maxX - minX, maxY - minY) * 0.05 + 2;
  return { minX: minX - pad, minY: minY - pad, width: maxX - minX + pad * 2, height: maxY - minY + pad * 2 };
}
