"""Structured output of every analysis check in app/analysis/. This is the
common contract the report generator (Phase 2) and the AI summarizer
(Phase 3) both consume."""

from enum import Enum

from pydantic import BaseModel

from app.models.board import Point


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Issue(BaseModel):
    id: str = ""  # category-prefixed, e.g. "PWR-004" -- assigned by run_all_checks, not by individual check modules
    category: str  # e.g. "routing", "power", "decoupling"
    severity: Severity
    confidence: float  # 0.0-1.0
    summary: str
    explanation: str  # why this matters
    principle: str  # the engineering principle involved
    suggested_fix: str
    location: Point | None = None
    refs: list[str] = []  # component/net references involved, e.g. ["U1", "3V3"]


class SubScore(BaseModel):
    category: str
    # 0-100, or None when no check feeds this subscore (shown as N/A and left
    # out of the overall score). None never means "perfect".
    score: int | None
    # The value before rounding, so reports can show the exact arithmetic.
    unrounded: float | None = None

    @property
    def evaluated(self) -> bool:
        return self.score is not None


class EngineeringScore(BaseModel):
    overall: int  # 0-100, mean of the evaluated subscores only
    subscores: list[SubScore]
    # 1 = original formula (every subscore, including unchecked ones at 100,
    # averaged after rounding). 2 = unevaluated subscores are N/A and excluded,
    # mean of unrounded values, rounded once. Payloads without the field are v1.
    formula_version: int = 1

    @property
    def evaluated(self) -> list[SubScore]:
        return [s for s in self.subscores if s.score is not None]

    @property
    def not_evaluated(self) -> list[SubScore]:
        return [s for s in self.subscores if s.score is None]
