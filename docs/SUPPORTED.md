# Supported input

What the parser (`backend/app/parser/kicad_project.py`) reads from a KiCad project, what it skips, and how it tells you. Checked against the code on 20 November 2026 (v1.1).

## File format

| | |
|---|---|
| Tested format version | `20240108` (KiCad 8). Every board in `examples/` uses it. |
| Other versions | Parsed, with a limitation note in the report: "File format version N has not been tested". |
| No `(version ...)` | Parsed, with a limitation note. |
| Encoding | UTF-8 text. Anything else is rejected with a clear error. |

## One board per review

- Exactly one `.kicad_pcb` file is reviewed. If an upload or folder contains more than one (searched recursively), the review stops with an error that lists them, instead of picking one silently.
- KiCad autosave copies (`_autosave-*.kicad_pcb`) are ignored.
- The CLI's batch mode is unchanged: each subfolder that contains a board is reviewed on its own.

## Parsed

| Construct | What is used |
|---|---|
| `layers` | Copper layer count (layer types `signal`, `power`, `mixed`, `jumper`) |
| `net` | Net numbers and names |
| `segment` (straight tracks) | Start, end, width, layer, net |
| `via` | Position, pad diameter, drill, net |
| `zone` (copper pours) | Net name, layer, and every `xy` point inside the zone. This includes filled-polygon points, not only the outline. |
| `footprint` | Position, rotation, layer, reference and value (from `fp_text` or `property`), and the nets of its pads |
| Edge.Cuts `gr_line`, `gr_rect`, `gr_poly` | Points used for the board's bounding box (origin, width, height) |
| Edge.Cuts `gr_arc`, `gr_circle` | Only their start, mid, end and center points. The bounding box is approximate, and the report says so. |

## Not parsed

| Construct | Effect | Shown in the report? |
|---|---|---|
| `arc` copper tracks (curved routing) | Ignored by routing, length and width checks | Yes, with the count |
| Missing Edge.Cuts outline | Board size is 0 and edge-distance checks cannot work | Yes |
| Schematic (`.kicad_sch`) | Located, never analyzed. No electrical rules check (ERC). | Yes, when a schematic is next to the board |
| Pad size, shape and exact position | Pads only contribute their nets | No (listed here) |
| Silkscreen and fab text geometry | Not checked | No (listed here) |
| Rule areas / keepouts, board stackup and thickness | Not checked | No (listed here) |
| Design rules in `.kicad_pro` / `.kicad_dru` | Checks use PCBInsight's own thresholds, not the project's rules | No (listed here) |
| Netlist (`.net`), 3D models, dimensions, groups | Not used | No (listed here) |

## Malformed input

The parser raises `BoardParseError` (the API returns HTTP 400 with the message) for:

- empty, truncated or unbalanced files,
- files whose top-level element is not `kicad_pcb` (for example a renamed schematic),
- values it cannot read, such as a non-numeric coordinate or net number,
- non-UTF-8 files.

Before v1.1, some of these produced an empty board that scored 100/100.

## Tests

`backend/tests/test_input_boundary.py`: rotated footprints, a board outline away from the origin (edge distances measured from the real outline), malformed files, several boards in one upload, autosave copies, and each limitation note.
