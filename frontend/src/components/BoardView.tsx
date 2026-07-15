import { useEffect, useMemo, useRef, useState } from "react";
import { boardBounds } from "../geometry";
import type { Board, Issue, Point, Severity } from "../types";

// KiCad-ish layer colors, tuned for a dark background. Unknown layers fall
// back to a small palette keyed by discovery order so any stackup stays
// visually distinct.
const LAYER_COLORS: Record<string, string> = {
  "F.Cu": "#e05252",
  "B.Cu": "#5277e0",
  "In1.Cu": "#5aa469",
  "In2.Cu": "#c8a04b",
  "In3.Cu": "#9b6bd0",
  "In4.Cu": "#4bb0c8",
};
const FALLBACK_COLORS = ["#d08770", "#a3be8c", "#b48ead", "#88c0d0", "#ebcb8b", "#bf616a"];

const SEVERITY_MARKER: Record<Severity, string> = {
  critical: "#ef4444",
  high: "#f87171",
  medium: "#fb923c",
  low: "#facc15",
  info: "#9ca3af",
};

interface Transform {
  k: number;
  x: number;
  y: number;
}

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 40;

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

export function BoardView({
  board,
  issues,
  selectedIssueId,
  onSelectIssue,
}: {
  board: Board;
  issues: Issue[];
  selectedIssueId: string | null;
  onSelectIssue: (id: string) => void;
}) {
  const bounds = useMemo(() => boardBounds(board), [board]);
  const viewBox = `${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`;
  const viewMin = Math.min(bounds.width, bounds.height);

  const layers = useMemo(() => {
    const found = new Set<string>();
    for (const net of board.nets) for (const trace of net.traces) found.add(trace.layer);
    for (const pour of board.pours) found.add(pour.layer);
    return Array.from(found).sort();
  }, [board]);

  const layerColor = useMemo(() => {
    const map: Record<string, string> = {};
    let fallback = 0;
    for (const layer of layers) {
      map[layer] = LAYER_COLORS[layer] ?? FALLBACK_COLORS[fallback++ % FALLBACK_COLORS.length];
    }
    return map;
  }, [layers]);

  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(() => new Set(layers));
  const [showComponents, setShowComponents] = useState(true);
  const [showVias, setShowVias] = useState(true);
  const [showLabels, setShowLabels] = useState(false);
  const [transform, setTransform] = useState<Transform>({ k: 1, x: 0, y: 0 });

  // Reset visible layers whenever the board (and thus its layer set) changes.
  useEffect(() => setVisibleLayers(new Set(layers)), [layers]);

  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);

  function toViewBox(clientX: number, clientY: number): Point | null {
    const svg = svgRef.current;
    if (!svg) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const mapped = pt.matrixTransform(ctm.inverse());
    return { x: mapped.x, y: mapped.y };
  }

  // Non-passive wheel listener so we can preventDefault the page scroll and
  // zoom toward the cursor instead.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    function onWheel(event: WheelEvent) {
      event.preventDefault();
      const p = toViewBox(event.clientX, event.clientY);
      if (!p) return;
      setTransform((prev) => {
        const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
        const k = clamp(prev.k * factor, MIN_ZOOM, MAX_ZOOM);
        const ratio = k / prev.k;
        return { k, x: p.x - (p.x - prev.x) * ratio, y: p.y - (p.y - prev.y) * ratio };
      });
    }
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  function onPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    const p = toViewBox(event.clientX, event.clientY);
    if (!p) return;
    dragRef.current = { x: p.x, y: p.y, tx: transform.x, ty: transform.y };
    (event.target as Element).setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!dragRef.current) return;
    const p = toViewBox(event.clientX, event.clientY);
    if (!p) return;
    const start = dragRef.current;
    setTransform((prev) => ({ ...prev, x: start.tx + (p.x - start.x), y: start.ty + (p.y - start.y) }));
  }

  function endDrag() {
    dragRef.current = null;
  }

  function toggleLayer(layer: string) {
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }

  function resetView() {
    setTransform({ k: 1, x: 0, y: 0 });
  }

  const groupTransform = `translate(${transform.x} ${transform.y}) scale(${transform.k})`;
  // Markers and component squares are drawn inside the scaled group, so divide
  // their size by k to keep a roughly constant on-screen footprint at any zoom.
  const markerR = (viewMin * 0.018) / transform.k;
  const componentHalf = (viewMin * 0.01) / transform.k;
  const hairline = viewMin * 0.0015;
  const locatedIssues = issues.filter((issue) => issue.location);

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800 px-6 py-4">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">Board view</h3>
          <p className="mt-1 text-xs text-neutral-500">
            {board.width_mm.toFixed(1)} × {board.height_mm.toFixed(1)} mm · {board.layer_count} layers · scroll to
            zoom, drag to pan
          </p>
        </div>
        <button
          type="button"
          onClick={resetView}
          className="rounded-md bg-neutral-800 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-700"
        >
          Reset view
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-neutral-800 px-6 py-3 text-xs">
        {layers.map((layer) => (
          <label key={layer} className="flex items-center gap-1.5 text-neutral-300">
            <input
              type="checkbox"
              checked={visibleLayers.has(layer)}
              onChange={() => toggleLayer(layer)}
              className="rounded border-neutral-600 bg-neutral-900"
            />
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: layerColor[layer] }} />
            {layer}
          </label>
        ))}
        <span className="text-neutral-700">|</span>
        <label className="flex items-center gap-1.5 text-neutral-300">
          <input type="checkbox" checked={showComponents} onChange={(e) => setShowComponents(e.target.checked)} className="rounded border-neutral-600 bg-neutral-900" />
          Components
        </label>
        <label className="flex items-center gap-1.5 text-neutral-300">
          <input type="checkbox" checked={showVias} onChange={(e) => setShowVias(e.target.checked)} className="rounded border-neutral-600 bg-neutral-900" />
          Vias
        </label>
        <label className="flex items-center gap-1.5 text-neutral-300">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} className="rounded border-neutral-600 bg-neutral-900" />
          Labels
        </label>
      </div>

      <svg
        ref={svgRef}
        viewBox={viewBox}
        className="block w-full touch-none select-none bg-neutral-950"
        style={{
          aspectRatio: `${bounds.width} / ${bounds.height}`,
          maxHeight: 520,
          cursor: dragRef.current ? "grabbing" : "grab",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <g transform={groupTransform}>
          {/* Board outline */}
          <rect
            x={board.origin.x}
            y={board.origin.y}
            width={board.width_mm}
            height={board.height_mm}
            fill="#0c0c0d"
            stroke="#c9a227"
            strokeWidth={hairline * 1.5}
          />

          {/* Copper pours */}
          {board.pours
            .filter((pour) => visibleLayers.has(pour.layer))
            .map((pour, index) => (
              <polygon
                key={`pour-${index}`}
                points={pour.outline.map((p) => `${p.x},${p.y}`).join(" ")}
                fill={layerColor[pour.layer] ?? "#666"}
                fillOpacity={0.12}
              />
            ))}

          {/* Traces */}
          {board.nets.flatMap((net) =>
            net.traces
              .filter((trace) => visibleLayers.has(trace.layer))
              .map((trace, index) => (
                <line
                  key={`${net.name}-t${index}`}
                  x1={trace.start.x}
                  y1={trace.start.y}
                  x2={trace.end.x}
                  y2={trace.end.y}
                  stroke={layerColor[trace.layer] ?? "#888"}
                  strokeWidth={trace.width}
                  strokeLinecap="round"
                  opacity={0.85}
                />
              )),
          )}

          {/* Vias */}
          {showVias &&
            board.nets.flatMap((net) =>
              net.vias.map((via, index) => (
                <circle
                  key={`${net.name}-v${index}`}
                  cx={via.position.x}
                  cy={via.position.y}
                  r={Math.max(via.diameter / 2, hairline * 2)}
                  fill="#d1d5db"
                  stroke="#111"
                  strokeWidth={hairline}
                />
              )),
            )}

          {/* Components */}
          {showComponents &&
            board.components.map((component) => {
              const pos = component.footprint.position;
              return (
                <g key={component.footprint.reference}>
                  <rect
                    x={pos.x - componentHalf}
                    y={pos.y - componentHalf}
                    width={componentHalf * 2}
                    height={componentHalf * 2}
                    fill={component.footprint.layer.startsWith("B") ? "#5277e0" : "#e05252"}
                    fillOpacity={0.35}
                    stroke={component.footprint.layer.startsWith("B") ? "#5277e0" : "#e05252"}
                    strokeWidth={hairline}
                  />
                  {showLabels && (
                    <text
                      x={pos.x}
                      y={pos.y - componentHalf * 1.4}
                      fill="#9ca3af"
                      fontSize={componentHalf * 1.8}
                      textAnchor="middle"
                    >
                      {component.footprint.reference}
                    </text>
                  )}
                </g>
              );
            })}

          {/* Issue markers -- drawn last so they sit on top and stay clickable */}
          {locatedIssues.map((issue) => {
            const loc = issue.location as Point;
            const selected = issue.id === selectedIssueId;
            return (
              <g
                key={`marker-${issue.id}`}
                className="cursor-pointer"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => onSelectIssue(issue.id)}
              >
                <circle
                  cx={loc.x}
                  cy={loc.y}
                  r={selected ? markerR * 1.5 : markerR}
                  fill={SEVERITY_MARKER[issue.severity]}
                  fillOpacity={0.85}
                  stroke={selected ? "#ffffff" : "#0c0c0d"}
                  strokeWidth={markerR * (selected ? 0.35 : 0.2)}
                />
              </g>
            );
          })}
        </g>
      </svg>

      {locatedIssues.length > 0 && (
        <p className="border-t border-neutral-800 px-6 py-2 text-xs text-neutral-500">
          {locatedIssues.length} issue{locatedIssues.length === 1 ? "" : "s"} with a board location — click a marker
          to open it below.
        </p>
      )}
    </div>
  );
}
