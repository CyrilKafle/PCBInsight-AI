"""Internal board representation. The parser (Phase 0) populates these; every
analysis check (Phase 1) and the AI summarizer (Phase 3) read from this model
only — never from raw KiCad files directly.
"""

from pydantic import BaseModel, Field


class Point(BaseModel):
    x: float
    y: float


class Footprint(BaseModel):
    reference: str  # e.g. "U1", "R15"
    value: str
    layer: str
    position: Point
    rotation: float
    pad_nets: list[str] = []  # net names touched by this footprint's pads


class Component(BaseModel):
    footprint: Footprint
    kind: str  # e.g. "MCU", "FPGA", "regulator", "passive", "connector"


class Trace(BaseModel):
    net: str
    layer: str
    width: float
    start: Point
    end: Point


class Via(BaseModel):
    net: str
    position: Point
    drill: float
    diameter: float


class CopperPour(BaseModel):
    net: str
    layer: str
    outline: list[Point]


class Net(BaseModel):
    name: str
    traces: list[Trace] = []
    vias: list[Via] = []


class Board(BaseModel):
    name: str
    layer_count: int
    width_mm: float
    height_mm: float
    origin: Point = Field(default_factory=lambda: Point(x=0.0, y=0.0))  # min corner of Edge.Cuts, for edge-relative checks
    components: list[Component] = []
    nets: list[Net] = []
    pours: list[CopperPour] = []
