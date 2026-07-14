"""Phase 0: locate and parse a KiCad project directory into an app.models.board.Board.

Responsible for finding `.kicad_pcb` / `.kicad_sch` / netlist / project files
within an uploaded directory tree and extracting components, nets, traces,
vias, copper pours, footprints, and board dimensions from the `.kicad_pcb`
S-expression file (parsed by `app.parser.sexpr`, no `pcbnew` dependency).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.board import Board, Component, CopperPour, Footprint, Net, Point, Trace, Via
from app.parser.sexpr import SExpr, child_values, find_all, find_first, parse as parse_sexpr

_COPPER_LAYER_TYPES = {"signal", "power", "mixed", "jumper"}

_IC_PREFIXES = {"U", "IC"}
_MCU_MARKERS = ("STM32", "ATMEGA", "ATTINY", "PIC", "ESP32", "ESP8266", "MSP430", "NRF52", "SAMD")
_FPGA_MARKERS = ("FPGA", "ICE40", "ECP5", "XC6", "XC7", "XC9", "CYCLONE", "ARTIX")
_CONNECTOR_PREFIXES = {"J", "P", "CN"}


def find_project_files(project_dir: Path) -> dict[str, Path]:
    """Locate .kicad_pcb, .kicad_sch, netlist, and project metadata files
    within an uploaded KiCad project directory."""
    patterns = {
        "project": "*.kicad_pro",
        "pcb": "*.kicad_pcb",
        "schematic": "*.kicad_sch",
        "netlist": "*.net",
    }
    files: dict[str, Path] = {}
    for key, pattern in patterns.items():
        matches = sorted(project_dir.rglob(pattern))
        if matches:
            files[key] = matches[0]
    if "pcb" not in files:
        raise FileNotFoundError(f"no .kicad_pcb file found under {project_dir}")
    return files


def parse_board(pcb_file: Path) -> Board:
    """Parse a .kicad_pcb file into the internal Board representation."""
    root = parse_sexpr(pcb_file.read_text(encoding="utf-8"))

    net_names = _net_names(root)
    traces = _parse_traces(root, net_names)
    vias = _parse_vias(root, net_names)
    pours = _parse_pours(root)
    nets = _build_nets(net_names, traces, vias)
    components = _parse_footprints(root, net_names)

    edge_points = _edge_cuts_points(root)
    xs = [p.x for p in edge_points]
    ys = [p.y for p in edge_points]
    origin_x = min(xs) if xs else 0.0
    origin_y = min(ys) if ys else 0.0
    width_mm = max(xs) - origin_x if xs else 0.0
    height_mm = max(ys) - origin_y if ys else 0.0

    return Board(
        name=pcb_file.stem,
        layer_count=_layer_count(root),
        width_mm=width_mm,
        height_mm=height_mm,
        origin=Point(x=origin_x, y=origin_y),
        components=components,
        nets=nets,
        pours=pours,
    )


def classify_component(reference: str, value: str) -> str:
    """Coarse component-kind classification from refdes prefix + value, e.g.
    "U1"/"ATmega328P" -> "MCU". Used by later analysis phases (decoupling,
    thermal) to find ICs/regulators without re-deriving this every time."""
    match = re.match(r"[A-Za-z]+", reference)
    prefix = match.group(0).upper() if match else ""
    value_upper = value.upper()

    if prefix in _IC_PREFIXES:
        if any(marker in value_upper for marker in _MCU_MARKERS):
            return "MCU"
        if any(marker in value_upper for marker in _FPGA_MARKERS):
            return "FPGA"
        if "REG" in value_upper or value_upper.startswith(("LM", "AMS1117", "AP", "MCP1")):
            return "regulator"
        return "IC"
    if prefix in _CONNECTOR_PREFIXES:
        return "connector"
    if prefix == "Q":
        return "transistor"
    if prefix == "D":
        return "diode"
    if prefix == "R":
        return "resistor"
    if prefix == "C":
        return "capacitor"
    if prefix == "L":
        return "inductor"
    if prefix in {"Y", "X"}:
        return "oscillator"
    if prefix in {"SW", "S"}:
        return "switch"
    return "other"


def _layer_count(root: SExpr) -> int:
    layers = find_first(root, "layers")
    if not layers:
        return 0
    return sum(
        1
        for entry in layers[1:]
        if isinstance(entry, list) and len(entry) >= 3 and entry[2] in _COPPER_LAYER_TYPES
    )


def _all_xy_points(expr: SExpr) -> list[Point]:
    return [
        Point(x=item[1], y=item[2])
        for item in find_all(expr, "xy")
        if len(item) >= 3
    ]


def _edge_cuts_points(root: SExpr) -> list[Point]:
    points: list[Point] = []
    for tag in ("gr_line", "gr_rect", "gr_poly", "gr_arc", "gr_circle"):
        for item in find_all(root, tag):
            layer = child_values(item, "layer")
            if not layer or layer[0] != "Edge.Cuts":
                continue
            for corner_tag in ("start", "end", "center", "mid"):
                vals = child_values(item, corner_tag)
                if len(vals) >= 2:
                    points.append(Point(x=vals[0], y=vals[1]))
            points.extend(_all_xy_points(item))
    return points


def _net_names(root: SExpr) -> dict[int, str]:
    names: dict[int, str] = {}
    for item in root:
        if isinstance(item, list) and len(item) >= 3 and item[0] == "net":
            names[int(item[1])] = str(item[2])
    return names


def _net_for(expr: SExpr, net_names: dict[int, str]) -> str:
    net_id = child_values(expr, "net")
    if not net_id:
        return ""
    return net_names.get(int(net_id[0]), "")


def _parse_traces(root: SExpr, net_names: dict[int, str]) -> list[Trace]:
    traces = []
    for seg in find_all(root, "segment"):
        start = child_values(seg, "start")
        end = child_values(seg, "end")
        width = child_values(seg, "width")
        layer = child_values(seg, "layer")
        if len(start) < 2 or len(end) < 2:
            continue
        traces.append(
            Trace(
                net=_net_for(seg, net_names),
                layer=layer[0] if layer else "",
                width=width[0] if width else 0.0,
                start=Point(x=start[0], y=start[1]),
                end=Point(x=end[0], y=end[1]),
            )
        )
    return traces


def _parse_vias(root: SExpr, net_names: dict[int, str]) -> list[Via]:
    vias = []
    for via in find_all(root, "via"):
        at = child_values(via, "at")
        size = child_values(via, "size")
        drill = child_values(via, "drill")
        if len(at) < 2:
            continue
        vias.append(
            Via(
                net=_net_for(via, net_names),
                position=Point(x=at[0], y=at[1]),
                drill=drill[0] if drill else 0.0,
                diameter=size[0] if size else 0.0,
            )
        )
    return vias


def _parse_pours(root: SExpr) -> list[CopperPour]:
    pours = []
    for zone in find_all(root, "zone"):
        net_name = child_values(zone, "net_name")
        layer = child_values(zone, "layer")
        if not layer:
            layers = child_values(zone, "layers")
            layer = [layers[0]] if layers else []
        pours.append(
            CopperPour(
                net=str(net_name[0]) if net_name else "",
                layer=str(layer[0]) if layer else "",
                outline=_all_xy_points(zone),
            )
        )
    return pours


def _build_nets(
    net_names: dict[int, str], traces: list[Trace], vias: list[Via]
) -> list[Net]:
    nets: dict[str, Net] = {}
    for name in net_names.values():
        if name:
            nets.setdefault(name, Net(name=name))
    for trace in traces:
        if trace.net:
            nets.setdefault(trace.net, Net(name=trace.net)).traces.append(trace)
    for via in vias:
        if via.net:
            nets.setdefault(via.net, Net(name=via.net)).vias.append(via)
    return list(nets.values())


def _parse_footprints(root: SExpr, net_names: dict[int, str]) -> list[Component]:
    components = []
    for fp in find_all(root, "footprint"):
        at = child_values(fp, "at")
        x, y = (at[0], at[1]) if len(at) >= 2 else (0.0, 0.0)
        rotation = at[2] if len(at) >= 3 else 0.0
        layer_vals = child_values(fp, "layer")
        layer = str(layer_vals[0]) if layer_vals else ""

        reference, value = "", ""
        for text_item in find_all(fp, "fp_text"):
            if len(text_item) >= 3 and text_item[1] == "reference":
                reference = str(text_item[2])
            elif len(text_item) >= 3 and text_item[1] == "value":
                value = str(text_item[2])
        if not reference or not value:
            for prop in find_all(fp, "property"):
                if len(prop) >= 3 and prop[1] == "Reference" and not reference:
                    reference = str(prop[2])
                elif len(prop) >= 3 and prop[1] == "Value" and not value:
                    value = str(prop[2])

        footprint = Footprint(
            reference=reference,
            value=value,
            layer=layer,
            position=Point(x=x, y=y),
            rotation=rotation,
            pad_nets=_pad_nets(fp, net_names),
        )
        components.append(Component(footprint=footprint, kind=classify_component(reference, value)))
    return components


def _pad_nets(footprint: SExpr, net_names: dict[int, str]) -> list[str]:
    names: list[str] = []
    for pad in find_all(footprint, "pad"):
        name = _net_for(pad, net_names)
        if name and name not in names:
            names.append(name)
    return names
