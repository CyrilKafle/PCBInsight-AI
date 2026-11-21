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

# File-format versions every board in examples/ uses. Other versions still
# parse, with a limitation note, because they have not been tested here.
TESTED_FORMAT_VERSIONS = {20240108: "KiCad 8"}

# KiCad's own autosave copies; never the board the user means.
_AUTOSAVE_PREFIX = "_autosave-"


class BoardParseError(ValueError):
    """The upload is not a readable KiCad .kicad_pcb file. The message is
    written for the user and never includes file contents."""


class MultipleBoardsError(ValueError):
    """More than one .kicad_pcb file was found, so the board to review is ambiguous."""


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
        matches = project_matches(project_dir, pattern)
        if key == "pcb" and len(matches) > 1:
            names = ", ".join(m.name for m in matches)
            raise MultipleBoardsError(
                f"found {len(matches)} .kicad_pcb files ({names}); review one board at a time"
            )
        if matches:
            files[key] = matches[0]
    if "pcb" not in files:
        raise FileNotFoundError(f"no .kicad_pcb file found under {project_dir}")
    return files


def project_matches(project_dir: Path, pattern: str) -> list[Path]:
    """Files matching `pattern` that belong to this project, autosave copies
    excluded. Files directly in `project_dir` win; subfolders are searched
    only when there are none at the top level (so a panel/ or old/ copy does
    not make a normal project ambiguous)."""

    def keep(paths):
        return sorted(p for p in paths if not p.name.startswith(_AUTOSAVE_PREFIX))

    return keep(project_dir.glob(pattern)) or keep(project_dir.rglob(pattern))


def parse_board(pcb_file: Path) -> Board:
    """Parse a .kicad_pcb file into the internal Board representation.

    Raises BoardParseError for input that is not a readable KiCad board, so a
    malformed upload never turns into an empty board with a perfect score."""
    name = pcb_file.name
    try:
        text = pcb_file.read_text(encoding="utf-8-sig")  # tolerate a byte-order mark
    except UnicodeDecodeError as exc:
        raise BoardParseError(f"{name} is not UTF-8 text, so it is not a KiCad .kicad_pcb file") from exc
    if not text.strip():
        raise BoardParseError(f"{name} is empty")
    if not text.lstrip().startswith("("):
        raise BoardParseError(f"{name} is not a KiCad PCB file: it does not start with a parenthesized (kicad_pcb ...) list")
    try:
        root = parse_sexpr(text)
    except (IndexError, ValueError) as exc:
        raise BoardParseError(f"{name} is not a complete S-expression (empty, truncated or unbalanced)") from exc
    except RecursionError as exc:
        raise BoardParseError(f"{name} is nested too deeply to be a KiCad board file") from exc
    if not isinstance(root, list) or not root:
        raise BoardParseError(f"{name} is not a KiCad PCB file: it does not start with a parenthesized (kicad_pcb ...) list")
    if root[0] != "kicad_pcb":
        top = root[0]
        what = f"'{top[:40]}'" if isinstance(top, str) else "a nested list"
        raise BoardParseError(f"{name} is not a KiCad PCB file: it starts with {what}, not 'kicad_pcb'")
    try:
        return _build_board(pcb_file, root)
    except (ValueError, TypeError, IndexError) as exc:
        raise BoardParseError(f"{name} has a value the parser cannot read ({type(exc).__name__})") from exc


def _build_board(pcb_file: Path, root: SExpr) -> Board:
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
        limitations=_limitations(root, pcb_file, has_outline=bool(edge_points)),
    )


def _limitations(root: SExpr, pcb_file: Path, has_outline: bool) -> list[str]:
    """Board-specific notes on what was skipped or approximated. The static
    list of unsupported constructs lives in docs/SUPPORTED.md."""
    notes: list[str] = []
    version = child_values(root, "version")
    tested = ", ".join(f"{v} ({label})" for v, label in TESTED_FORMAT_VERSIONS.items())
    if not version:
        notes.append("The file has no format version, so it may not match the tested KiCad 8 format.")
    elif not isinstance(version[0], float) or version[0] != int(version[0]):
        notes.append(f"The file's format version is not a number this parser recognizes; tested: {tested}.")
    elif int(version[0]) not in TESTED_FORMAT_VERSIONS:
        notes.append(f"File format version {int(version[0])} has not been tested; tested: {tested}.")

    arcs = [item for item in root if isinstance(item, list) and item and item[0] == "arc"]
    if arcs:
        notes.append(
            f"{len(arcs)} curved copper track{'s' if len(arcs) != 1 else ''} (arc) "
            f"{'were' if len(arcs) != 1 else 'was'} not parsed, so routing and length checks ignore "
            f"{'them' if len(arcs) != 1 else 'it'}."
        )

    if not has_outline:
        notes.append("No Edge.Cuts board outline was found, so board size and edge-distance checks are unavailable.")
    elif any(_on_edge_cuts(item) for tag in ("gr_arc", "gr_circle") for item in find_all(root, tag)):
        notes.append(
            "The board outline has arcs or circles; board size is estimated from their end, mid and center "
            "points, not the exact curve."
        )

    if project_matches(pcb_file.parent, "*.kicad_sch"):
        notes.append("A schematic was found but is not analyzed; no electrical rules check (ERC) was run.")
    return notes


def _on_edge_cuts(item: SExpr) -> bool:
    layer = child_values(item, "layer")
    return bool(layer) and layer[0] == "Edge.Cuts"


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
