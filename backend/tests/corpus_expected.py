"""Expected findings for every board in examples/ (v1.1 item 6).

Captured from the engine at the commit that added this file, then checked
against the per-board descriptions in examples/README.md (finding counts and
which categories each board is built to trip). This pins current behavior:
any change to a finding ID, severity, rule weight, measured value (in the
summary) or score fails the test and must be reviewed. It is not an
independent ground truth; comparing against KiCad DRC is planned for P3.
"""

# board -> (overall score, {finding id: (severity, rule weight, summary)})
EXPECTED = {
    'flawed_reference': (
        81,
        {
            'RTE-001': ('medium', 0.6, 'Acute-angle bend on net GND (42°)'),
            'RTE-002': ('low', 0.4, 'Possible dangling trace end on net GND'),
            'RTE-003': ('medium', 0.6, 'Acute-angle bend on net /CLK (57°)'),
            'RTE-004': ('low', 0.4, 'Possible dangling trace end on net /CLK'),
            'RTE-005': ('low', 0.4, 'Possible dangling trace end on net /USB_DP'),
            'RTE-006': ('low', 0.4, 'Possible dangling trace end on net /USB_DM'),
            'PWR-001': ('medium', 0.65, 'Thin power trace on net +5V (0.15mm)'),
            'PWR-002': ('medium', 0.65, 'Thin power trace on net +3V3 (0.15mm)'),
            'PWR-003': ('medium', 0.65, 'Thin power trace on net +3V3 (0.15mm)'),
            'GND-001': ('medium', 0.4, '2 separate ground-like nets found (GND, GND2)'),
            'GND-002': ('medium', 0.55, 'No copper pour found for ground net GND'),
            'GND-003': ('medium', 0.55, 'No copper pour found for ground net GND2'),
            'GND-004': ('medium', 0.55, 'Thin ground trace on net GND (0.15mm)'),
            'GND-005': ('medium', 0.55, 'Thin ground trace on net GND (0.15mm)'),
            'DECAP-001': ('medium', 0.5, 'Decoupling capacitor C1 is 23.3mm from U1'),
            'DECAP-002': ('medium', 0.5, 'Decoupling capacitor C1 is 36.9mm from U2'),
            'DECAP-003': ('high', 0.55, "No decoupling capacitor found on U2's +5V net"),
            'MFG-001': ('high', 0.7, 'Via on net GND has a 0.025mm annular ring'),
            'MFG-002': ('high', 0.7, 'Via on net /CLK has a 0.025mm annular ring'),
            'MFG-003': ('high', 0.7, 'Via on net /CLK has a 0.025mm annular ring'),
            'MFG-004': ('high', 0.7, 'Via on net /CLK has a 0.025mm annular ring'),
            'THERM-001': ('medium', 0.45, 'No copper pour near heat source U2'),
            'SIG-001': ('low', 0.45, 'Clock net /CLK uses 3 vias'),
            'SIG-002': ('low', 0.4, 'Clock net /CLK totals 53.9mm'),
        },
    ),
    'high_quality_reference': (
        100,
        {},
    ),
    'manufacturing_reference': (
        94,
        {
            'RTE-001': ('medium', 0.6, 'Net STITCH uses 8 vias'),
            'PLACE-001': ('info', 0.35, 'Components occupy only 0% of the board footprint area'),
            'MFG-001': ('high', 0.7, 'Trace on net SIG1 is 0.10mm wide'),
            'MFG-002': ('high', 0.7, 'Via on net STITCH has a 0.025mm annular ring'),
            'MFG-003': ('high', 0.7, 'Via on net STITCH has a 0.025mm annular ring'),
            'MFG-004': ('low', 0.4, 'Via density is 5.6 vias/cm²'),
        },
    ),
    'mixed_realistic_board': (
        97,
        {
            'RTE-001': ('low', 0.4, 'Possible dangling trace end on net CLK'),
            'DECAP-001': ('medium', 0.5, 'Decoupling capacitor C3 is 10.0mm from U2'),
            'MFG-001': ('high', 0.7, 'Trace on net TP_SENSE is 0.12mm wide'),
            'SIG-001': ('low', 0.4, 'Clock net CLK totals 47.0mm'),
        },
    ),
    'parser_edge_cases': (
        98,
        {
            'RTE-001': ('low', 0.4, 'Possible dangling trace end on net R&D_信号'),
            'GND-001': ('medium', 0.55, 'Thin ground trace on net GND (0.25mm)'),
            'DECAP-001': ('high', 0.55, "No decoupling capacitor found on u1's VCC<3V3> net"),
        },
    ),
    'power_supply_board': (
        96,
        {
            'PWR-001': ('medium', 0.65, 'Thin power trace on net +5V (0.20mm)'),
            'GND-001': ('medium', 0.55, 'No copper pour found for ground net GND'),
            'DECAP-001': ('medium', 0.5, 'Decoupling capacitor C2 is 10.0mm from U1'),
            'DECAP-002': ('high', 0.55, "No decoupling capacitor found on U1's +5V net"),
            'THERM-001': ('medium', 0.45, 'No copper pour near heat source U1'),
        },
    ),
    'rf_clock_board': (
        98,
        {
            'RTE-001': ('low', 0.4, 'Possible dangling trace end on net XTAL_CLK'),
            'DIFF-001': ('medium', 0.6, 'Differential pair DATA_P/DATA_N length mismatch of 8.10mm'),
            'DIFF-002': ('low', 0.4, 'Differential pair DATA_P/DATA_N has asymmetric via count (0 vs 1)'),
            'DIFF-003': ('low', 0.35, 'Differential pair DATA_P/DATA_N routed with different segment counts (1 vs 4)'),
            'SIG-001': ('medium', 0.5, 'Branch point on clock net XTAL_CLK near (25.0, 15.0)'),
            'SIG-002': ('low', 0.45, 'Clock net XTAL_CLK uses 3 vias'),
            'SIG-003': ('low', 0.4, 'Clock net XTAL_CLK totals 58.0mm'),
        },
    ),
    'simple_board': (
        100,
        {
            'SIG-001': ('low', 0.4, 'Clock net /SCLK totals 40.0mm'),
        },
    ),
    'stm32_usb_dev': (
        97,
        {
            'RTE-001': ('low', 0.4, 'Possible dangling trace end on net /USB_DP'),
            'RTE-002': ('low', 0.4, 'Possible dangling trace end on net /USB_DM'),
            'RTE-003': ('low', 0.4, 'Possible dangling trace end on net /XTAL_IN'),
            'RTE-004': ('low', 0.4, 'Possible dangling trace end on net /XTAL_OUT'),
            'RTE-005': ('low', 0.4, 'Possible dangling trace end on net /SWDIO'),
            'RTE-006': ('low', 0.4, 'Possible dangling trace end on net /SWCLK'),
            'PWR-001': ('medium', 0.65, 'Thin power trace on net +3V3 (0.25mm)'),
            'DECAP-001': ('medium', 0.5, 'Decoupling capacitor C1 is 3.2mm from U1'),
        },
    ),
    'thermal_reference': (
        98,
        {
            'THERM-001': ('medium', 0.45, 'No copper pour near heat source U1'),
            'THERM-002': ('medium', 0.45, 'No copper pour near heat source Q1'),
            'THERM-003': ('medium', 0.4, 'Heat sources U1 and Q1 are 4.1mm apart'),
        },
    ),
}
