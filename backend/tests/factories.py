"""Small builders for constructing minimal Board fixtures in analysis unit
tests, without needing a full .kicad_pcb file per test case."""

from app.models.board import Board, Component, CopperPour, Footprint, Net, Point, Trace, Via


def make_component(
    ref: str,
    value: str,
    kind: str,
    x: float = 0.0,
    y: float = 0.0,
    rotation: float = 0.0,
    layer: str = "F.Cu",
    pad_nets: list[str] | None = None,
) -> Component:
    return Component(
        footprint=Footprint(
            reference=ref,
            value=value,
            layer=layer,
            position=Point(x=x, y=y),
            rotation=rotation,
            pad_nets=pad_nets or [],
        ),
        kind=kind,
    )


def make_trace(net: str, x1: float, y1: float, x2: float, y2: float, width: float = 0.25, layer: str = "F.Cu") -> Trace:
    return Trace(net=net, layer=layer, width=width, start=Point(x=x1, y=y1), end=Point(x=x2, y=y2))


def make_via(net: str, x: float, y: float, drill: float = 0.3, diameter: float = 0.6) -> Via:
    return Via(net=net, position=Point(x=x, y=y), drill=drill, diameter=diameter)


def make_pour(net: str, layer: str, points: list[tuple[float, float]]) -> CopperPour:
    return CopperPour(net=net, layer=layer, outline=[Point(x=x, y=y) for x, y in points])


def make_net(name: str, traces: list[Trace] | None = None, vias: list[Via] | None = None) -> Net:
    return Net(name=name, traces=traces or [], vias=vias or [])


def make_board(
    name: str = "test_board",
    width_mm: float = 50.0,
    height_mm: float = 40.0,
    layer_count: int = 2,
    origin: tuple[float, float] = (0.0, 0.0),
    components: list[Component] | None = None,
    nets: list[Net] | None = None,
    pours: list[CopperPour] | None = None,
) -> Board:
    return Board(
        name=name,
        layer_count=layer_count,
        width_mm=width_mm,
        height_mm=height_mm,
        origin=Point(x=origin[0], y=origin[1]),
        components=components or [],
        nets=nets or [],
        pours=pours or [],
    )
