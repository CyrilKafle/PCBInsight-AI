"""Tests for the tabbed, interactive demo report.

The "Try it" rule checker re-implements each engine threshold in JavaScript so
it can run in a static page. The parity test below runs that JavaScript under
node against the real Python check functions, on the same inputs, so the two
cannot silently drift apart."""

import json
import re
import shutil
import subprocess

import pytest

from app.analysis import decoupling, differential_pairs, ground, manufacturability, placement, power, routing, signal_integrity, thermal
from app.analysis.scoring import score as compute_score
from app.analysis.scoring import subscore_for
from app.models.issue import Issue, Severity
from app.reports import interactive_report as ir
from tests.factories import make_board, make_component, make_net, make_trace, make_via


def _issue(summary="Test issue", category="routing", severity=Severity.HIGH, confidence=1.0, id_="RTE-001"):
    return Issue(
        id=id_,
        category=category,
        severity=severity,
        confidence=confidence,
        summary=summary,
        explanation="Test explanation",
        principle="Test principle",
        suggested_fix="Test fix",
    )


def _render(issues=None, ai=None):
    issues = issues if issues is not None else []
    return ir.render(make_board(name="my_board"), issues, compute_score(issues), ai, landing_href="index.html")


# --- structure -------------------------------------------------------------------


def test_render_has_one_view_per_tab_and_a_back_button():
    html = _render([_issue()])
    for key, _label in ir.VIEWS:
        assert f'id="view-{key}"' in html
        assert f'href="#{key}"' in html
    # every view except the overview has a back button, and the landing link is present
    assert html.count('class="back-btn"') == len(ir.VIEWS) - 1
    assert 'href="index.html"' in html
    assert html.startswith("<!doctype html>")


def test_render_includes_board_name_and_finding_text():
    html = _render([_issue(summary="Thin power trace on net +3V3")])
    assert "my_board" in html
    assert "Thin power trace on net +3V3" in html
    assert "Test explanation" in html and "Test fix" in html


def test_render_escapes_html_in_issue_content():
    html = _render([_issue(summary="<script>alert(1)</script>")])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_embedded_data_cannot_break_out_of_its_script_tag():
    html = _render([_issue(summary="</script><b>x</b>")])
    match = re.search(r'<script id="pcbi-data" type="application/json">(.*?)</script>', html, re.S)
    assert match and "</" not in match.group(1)
    json.loads(match.group(1))


def test_render_with_no_issues_still_renders_every_view():
    html = _render([])
    assert "No issues found" in html
    assert "No findings to simulate" in html


def test_ai_review_is_rendered_or_absent_message_shown():
    assert "No AI narrative review" in _render([])
    html = _render([], ai="## Summary\n\nAll good.")
    assert "All good." in html and "No AI narrative review" not in html


# --- score formula in the page mirrors scoring.py ---------------------------------


def test_scores_view_matches_backend_score():
    issues = [_issue(severity=Severity.MEDIUM, confidence=0.65, category="power", id_="PWR-001")]
    score = compute_score(issues)
    html = ir.render(make_board(), issues, score)
    data = json.loads(re.search(r'<script id="pcbi-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    assert {s["name"]: s["score"] for s in data["subscores"]} == {s.category: s.score for s in score.subscores}
    assert data["severityPoints"]["medium"] == 8.0
    assert data["issues"][0]["sub"] == subscore_for("power")


# --- JS rule checker parity with the engine ---------------------------------------

node = shutil.which("node")


def _sig(issues, keep):
    return sorted(
        (subscore_for(i.category), i.severity.value, round(i.confidence, 3)) for i in issues if keep(i)
    )


def _chain(net, n, total, y=0.0, width=0.25):
    step = total / n
    return [make_trace(net, i * step, y, (i + 1) * step, y, width) for i in range(n)]


def _expected(rule_id, v):
    if rule_id == "trace_width":
        name = {"power": "3V3", "ground": "GND", "signal": "SIG_A"}[v["net"]]
        board = make_board(nets=[make_net(name, [make_trace(name, 0, 0, 5, 0, v["width"])])])
        issues = power.check(board) + ground.check(board) + manufacturability.check(board)
        return _sig(issues, lambda i: i.summary.startswith(("Thin power trace", "Thin ground trace", "Trace on net")))
    if rule_id == "annular_ring":
        board = make_board(nets=[make_net("SIG", vias=[make_via("SIG", 5, 5, drill=v["drill"], diameter=v["pad"])])])
        return _sig(manufacturability.check(board), lambda i: i.summary.startswith("Via on net"))
    if rule_id == "long_trace":
        board = make_board(width_mm=300, nets=[make_net("SIG", [make_trace("SIG", 0, 0, v["length"], 0)])])
        return _sig(routing.check(board), lambda i: i.summary.startswith("Long trace"))
    if rule_id == "via_count":
        name = "CLK" if v["clock"] else "SIG"
        net = make_net(name, [make_trace(name, 0, 0, 5, 0)], [make_via(name, 1 + k, 1) for k in range(int(v["vias"]))])
        board = make_board(nets=[net])
        issues = routing.check(board) + signal_integrity.check(board)
        return _sig(issues, lambda i: "vias" in i.summary and i.summary.startswith(("Net ", "Clock net")))
    if rule_id == "segments":
        board = make_board(nets=[make_net("SIG", _chain("SIG", int(v["segments"]), 20))])
        return _sig(routing.check(board), lambda i: "routed with" in i.summary)
    if rule_id == "acute_angle":
        import math

        a = math.radians(v["angle"])
        traces = [make_trace("SIG", 0, 0, 10, 0), make_trace("SIG", 0, 0, 10 * math.cos(a), 10 * math.sin(a))]
        board = make_board(nets=[make_net("SIG", traces)])
        return _sig(routing.check(board), lambda i: i.summary.startswith("Acute-angle"))
    if rule_id == "decoupling":
        comps = [make_component("U1", "X", v["kind"], 0, 0, pad_nets=["3V3"])]
        if not v["none"]:
            comps.append(make_component("C1", "100n", "capacitor", v["gap"], 0, pad_nets=["3V3", "GND"]))
        return _sig(decoupling.check(make_board(components=comps)), lambda i: True)
    if rule_id == "supply_path":
        board = make_board(width_mm=300, nets=[make_net("3V3", [make_trace("3V3", 0, 0, v["length"], 0, 0.5)])])
        return _sig(power.check(board), lambda i: i.summary.startswith("Supply net"))
    if rule_id == "diff_pair":
        def pair(name, length, vias, segs):
            return make_net(name, _chain(name, int(segs), length), [make_via(name, 1 + k, 1) for k in range(int(vias))])

        board = make_board(width_mm=300, nets=[pair("USB_P", v["lenP"], v["viaP"], v["segP"]), pair("USB_N", v["lenN"], v["viaN"], v["segN"])])
        return _sig(differential_pairs.check(board), lambda i: True)
    if rule_id == "clock_length":
        board = make_board(width_mm=300, nets=[make_net("CLK", [make_trace("CLK", 0, 0, v["length"], 0)])])
        return _sig(signal_integrity.check(board), lambda i: i.summary.endswith("mm") and "totals" in i.summary)
    if rule_id == "via_density":
        n = int(v["vias"])
        board = make_board(width_mm=v["w"], height_mm=v["h"], nets=[make_net("SIG", vias=[make_via("SIG", 1, 1) for _ in range(n)])])
        return _sig(manufacturability.check(board), lambda i: i.summary.startswith("Via density"))
    if rule_id == "connector_edge":
        board = make_board(components=[make_component("J1", "USB", "connector", v["dist"], 20)])
        return _sig(placement.check(board), lambda i: i.summary.startswith("Connector"))
    if rule_id == "crowding":
        comps = [make_component("R1", "1k", "passive", 10, 10), make_component("R2", "1k", "passive", 10 + v["gap"], 10)]
        return _sig(placement.check(make_board(components=comps)), lambda i: "apart" in i.summary)
    if rule_id == "heat_spacing":
        comps = [make_component("U2", "LDO", "regulator", 10, 10), make_component("U3", "LDO", "regulator", 10 + v["gap"], 10)]
        return _sig(thermal.check(make_board(components=comps)), lambda i: i.summary.startswith("Heat sources"))
    raise AssertionError(rule_id)


_CASES = {
    "trace_width": [{"width": w, "net": n} for n in ("power", "ground", "signal") for w in (0.05, 0.1, 0.149, 0.15, 0.2, 0.299, 0.3, 0.5)],
    "annular_ring": [{"pad": p, "drill": d} for p, d in ((0.6, 0.3), (0.4, 0.3), (0.45, 0.3), (0.5, 0.35), (0.3, 0.3), (0.8, 0.4))],
    "long_trace": [{"length": x} for x in (10, 59, 60, 61, 119, 120, 150)],
    "via_count": [{"vias": n, "clock": c} for c in (False, True) for n in (0, 1, 2, 3, 4, 5, 8)],
    "segments": [{"segments": n} for n in (1, 5, 8, 9, 14)],
    "acute_angle": [{"angle": a} for a in (20, 45, 89, 91, 120, 150)],
    "decoupling": [{"kind": k, "gap": g, "none": z} for k in ("MCU", "FPGA", "regulator", "IC") for g in (1, 2.5, 3, 4, 5, 6) for z in (False,)] + [{"kind": "MCU", "gap": 1, "none": True}],
    "supply_path": [{"length": x} for x in (10, 79, 80, 100)],
    "diff_pair": [
        {"lenP": 42, "lenN": 42.1, "viaP": 1, "viaN": 1, "segP": 4, "segN": 4},
        {"lenP": 42, "lenN": 44.5, "viaP": 1, "viaN": 1, "segP": 1, "segN": 1},
        {"lenP": 42, "lenN": 42, "viaP": 2, "viaN": 0, "segP": 3, "segN": 3},
        {"lenP": 42, "lenN": 42, "viaP": 1, "viaN": 1, "segP": 3, "segN": 5},
        {"lenP": 42, "lenN": 42, "viaP": 1, "viaN": 1, "segP": 3, "segN": 6},
        {"lenP": 30, "lenN": 31, "viaP": 0, "viaN": 3, "segP": 2, "segN": 9},
    ],
    "clock_length": [{"length": x} for x in (5, 39, 40, 41, 80)],
    "via_density": [{"vias": n, "w": w, "h": h} for n, w, h in ((40, 60, 40), (160, 40, 30), (6, 40, 30), (30, 20, 30), (0, 40, 30))],
    "connector_edge": [{"dist": x} for x in (1, 4, 10, 10.5, 18)],
    "crowding": [{"gap": x} for x in (0.2, 0.9, 1.0, 1.1, 3)],
    "heat_spacing": [{"gap": x} for x in (2, 7.9, 8, 8.1, 15)],
}

_HARNESS = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const EVAL = (function () { %s; return EVAL; })();
const out = input.cases.map(function (c) {
  const r = EVAL[c.id](c.values, input.limits[c.id]);
  return r.map(function (f) { return [f.sub, f.sev, Math.round(f.conf * 1000) / 1000]; }).sort();
});
process.stdout.write(JSON.stringify(out));
"""


def test_every_rule_has_cases_and_a_matching_evaluator():
    ids = {r["id"] for r in ir._rule_definitions()}
    assert ids == set(_CASES)
    for rule in ir._rule_definitions():
        assert f"{rule['id']}: function" in ir._RULES_JS
        assert len(rule["presets"]) == 2
        assert {f["key"] for f in rule["fields"]} >= set(rule["presets"][0][1])


@pytest.mark.skipif(node is None, reason="node is not installed")
def test_js_rule_checker_matches_python_engine():
    rules = {r["id"]: r for r in ir._rule_definitions()}
    cases, expected = [], []
    for rule_id, value_sets in _CASES.items():
        for values in value_sets:
            cases.append({"id": rule_id, "values": values})
            expected.append(_expected(rule_id, values))
    payload = json.dumps({"cases": cases, "limits": {k: v["limits"] for k, v in rules.items()}})
    proc = subprocess.run(
        [node, "-e", _HARNESS % ir._RULES_JS], input=payload, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    actual = json.loads(proc.stdout)
    mismatches = [
        (case, exp, [tuple(x) for x in act])
        for case, exp, act in zip(cases, expected, actual)
        if [tuple(x) for x in act] != [tuple(x) for x in exp]
    ]
    assert not mismatches, mismatches[:5]
