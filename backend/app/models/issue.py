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
    score: int  # 0-100


class EngineeringScore(BaseModel):
    overall: int  # 0-100
    subscores: list[SubScore]
