// Mirrors backend/app/models/board.py and backend/app/models/issue.py.
// Field names match the Pydantic models' snake_case JSON output exactly.

export interface Point {
  x: number;
  y: number;
}

export interface Footprint {
  reference: string;
  value: string;
  layer: string;
  position: Point;
  rotation: number;
  pad_nets: string[];
}

export interface Component {
  footprint: Footprint;
  kind: string;
}

export interface Trace {
  net: string;
  layer: string;
  width: number;
  start: Point;
  end: Point;
}

export interface Via {
  net: string;
  position: Point;
  drill: number;
  diameter: number;
}

export interface CopperPour {
  net: string;
  layer: string;
  outline: Point[];
}

export interface Net {
  name: string;
  traces: Trace[];
  vias: Via[];
}

export interface Board {
  name: string;
  layer_count: number;
  width_mm: number;
  height_mm: number;
  origin: Point;
  components: Component[];
  nets: Net[];
  pours: CopperPour[];
  /** Parser notes: input skipped or approximated for this board. */
  limitations?: string[];
}

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface Issue {
  id: string;
  category: string;
  severity: Severity;
  confidence: number;
  summary: string;
  explanation: string;
  principle: string;
  suggested_fix: string;
  location: Point | null;
  refs: string[];
}

export interface SubScore {
  category: string;
  /** 0-100, or null when no check feeds this subscore (N/A, not in the overall). */
  score: number | null;
  unrounded?: number | null;
}

export interface EngineeringScore {
  overall: number;
  subscores: SubScore[];
  /** 2 = N/A subscores excluded, unrounded mean rounded once. Missing = 1. */
  formula_version?: number;
}

export interface AiError {
  category: "not_configured" | "provider_error" | "withheld";
  message: string;
}

export interface ReviewResponse {
  board: Board;
  issues: Issue[];
  score: EngineeringScore;
  schema_version?: number;
  ai_review: string | null;
  ai_review_status?: "valid" | "repaired" | "withheld" | null;
  ai_error?: AiError | null;
}
