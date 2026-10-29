"""Make the SYNTHETIC example data: a furnace P&ID (DEXPI XML) and a C&E matrix (Excel).

Everything here is invented for training. The trips follow the ethane cracking
furnace in this repository's trainer (src/engine.js): pass flow low-low, steam to
hydrocarbon ratio low-low, COT high-high, arch O2 low-low, firebox pressure
high-high and steam drum level low-low. Four typical furnace trips that the
trainer does not model are added: fuel gas pressure low-low, flame failure,
tube metal temperature high-high and a manual emergency shutdown button.

`seeded=True` (the default) plants deliberate mistakes so that every check has
something to find. Each one is marked "SEEDED" below and listed in the README.
`seeded=False` gives a clean, consistent pair that should produce zero findings.

Run:  python -m interlock_checker.synthetic --out examples
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SYNTHETIC_LABEL = "SYNTHETIC – FOR TRAINING ONLY"

# ---------------------------------------------------------------------------
# The plant (one source of truth for both files)
# ---------------------------------------------------------------------------

EQUIPMENT = [
    ("Furnace", "F-101"),          # ethane cracking furnace
    ("Fan", "K-101"),              # induced draft fan
    ("CentrifugalPump", "P-131A"),  # boiler feed water pump, duty
    ("CentrifugalPump", "P-131B"),  # boiler feed water pump, standby
    ("Vessel", "D-130"),           # steam drum
]


def pid_loops(seeded: bool = True) -> list[dict]:
    """Instrument loops on the synthetic P&ID.

    Each loop: category + modifier + number make the bubble tag; 'transmitters'
    are the measuring tags; 'valves' are (tag, fail action) pairs.
    """
    loops = [
        # Basic process control loops (DCS, not safety related)
        dict(cat="F", mod="IC", num="100", desc="Ethane feed flow control",
             transmitters=["FT-100"], valves=[("FV-100", "FailClose")]),
        dict(cat="F", mod="IC", num="110", desc="Dilution steam flow control",
             transmitters=["FT-110"],
             # SEEDED: dilution steam valve drawn fail-close; the trip wants it OPEN.
             valves=[("FV-110", "FailClose" if seeded else "FailOpen")]),
        dict(cat="T", mod="IC", num="150", desc="Coil outlet temperature control (fuel gas)",
             transmitters=["TT-150"], valves=[("TV-150", "FailClose")]),
        dict(cat="A", mod="IC", num="140", desc="Arch O2 control (stack damper)",
             transmitters=["AT-140"], valves=[]),
        dict(cat="L", mod="IC", num="130", desc="Steam drum level control (BFW)",
             transmitters=["LT-130"], valves=[("LV-130", "FailOpen")]),
    ]
    # Safety instrumented initiators (trip transmitters)
    for p in "ABCD":
        loops.append(dict(cat="F", mod="ZT", num=f"101{p}", desc=f"Pass {p} flow, low-low trip",
                          sil="SIL1", voting="1oo1", transmitters=[f"FZT-101{p}"], valves=[]))
    loops += [
        dict(cat="F", mod="ZT", num="110", desc="Steam/ethane ratio, low-low trip",
             sil="SIL2", voting="2oo3", transmitters=["FZT-110"], valves=[]),
        dict(cat="T", mod="ZT", num="150", desc="Coil outlet temperature, high-high trip",
             sil="SIL1", voting="2oo3", transmitters=["TZT-150"], valves=[]),
        dict(cat="A", mod="ZT", num="140", desc="Arch O2, low-low trip",
             sil="SIL2", voting="2oo3", transmitters=["AZT-140"], valves=[]),
        dict(cat="P", mod="ZT", num="141", desc="Firebox pressure, high-high trip",
             sil="SIL2", voting="2oo3", transmitters=["PZT-141"], valves=[]),
        dict(cat="L", mod="ZT", num="130", desc="Steam drum level, low-low trip",
             sil="SIL2", voting="2oo3", transmitters=["LZT-130"], valves=[]),
        dict(cat="P", mod="ZT", num="170", desc="Fuel gas pressure, low-low trip",
             sil="SIL2", voting="2oo3", transmitters=["PZT-170"], valves=[]),
        dict(cat="B", mod="ZS", num="171", desc="Flame failure (burner management)",
             sil="SIL2", voting="1oo1" if seeded else "1oo2",
             transmitters=["BZS-171"], valves=[]),
        # SEEDED: marked SIL2 on the P&ID but has no C&E row. Its tag has no 'Z',
        # so only the SIL marking reveals it as a trip transmitter.
        dict(cat="P", mod="T", num="172", desc="Fuel gas pressure, high-high trip",
             sil="SIL2", voting="2oo3", transmitters=["PT-172"], valves=[]),
        dict(cat="H", mod="S", num="199", desc="Emergency shutdown push button (control room)",
             sil="SIL1", voting="1oo1", transmitters=["HS-199"], valves=[]),
    ]
    if not seeded:
        # SEEDED (by omission): the TMT trip exists in the C&E but not on the P&ID.
        loops.append(dict(cat="T", mod="ZT", num="160", desc="Tube metal temperature, high-high trip",
                          sil="SIL1", voting="1oo2", transmitters=["TZT-160"], valves=[]))

    # Shutdown valves (one loop per valve, final elements of the SIS)
    sdvs = [
        # SEEDED: ethane feed shutoff drawn fail-last (FL); the trip wants it CLOSED.
        ("XV-100", "Ethane feed shutoff valve", "FailRetainPosition" if seeded else "FailClose"),
        ("XV-170", "Fuel gas first shutoff valve", "FailClose"),
        ("XV-171", "Fuel gas second shutoff valve", "FailClose"),
        # SEEDED: fuel gas vent (bleed) drawn fail-close; the trip wants it OPEN.
        ("XV-172", "Fuel gas vent valve (bleed)", "FailClose" if seeded else "FailOpen"),
        ("XV-175", "Pilot gas first shutoff valve", "FailClose"),
    ]
    if not seeded:
        # SEEDED (by omission): pilot gas second block valve missing from the P&ID.
        sdvs.append(("XV-176", "Pilot gas second shutoff valve", "FailClose"))
    for tag, desc, fail in sdvs:
        loops.append(dict(cat="X", mod="V", num=tag.split("-", 1)[1], desc=desc,
                          sil="SIL2", transmitters=[], valves=[(tag, fail)]))
    return loops


# Cause rows: (tag, description, setpoint, units, trip type, voting, SIL, latching, reset, group)
# group says which effects the cause drives (see EFFECT_GROUPS).
def ce_causes(seeded: bool = True) -> list[dict]:
    rows = []
    for p in "ABC" if seeded else "ABCD":   # SEEDED: pass D (FZT-101D) has no C&E row
        rows.append(dict(tag=f"FZT-101{p}", desc=f"Pass {p} flow low-low", sp="62", units="% of design",
                         type="LL", voting="1oo1", sil="SIL1", latch="YES", reset="MANUAL", group="process"))
    rows += [
        dict(tag="FZT-110", desc="Steam/ethane ratio low-low", sp="0.20", units="kg/kg", type="LL",
             voting="2oo3", sil="SIL2", latch="YES",
             reset="AUTO" if seeded else "MANUAL",       # SEEDED: auto reset on a SIF
             group="process"),
        dict(tag="TZT-150", desc="Coil outlet temperature high-high", sp="880", units="°C", type="HH",
             voting="2oo3", sil="SIL1", latch="YES", reset="MANUAL", group="cot"),
        dict(tag="AZT-140", desc="Arch O2 low-low", sp="0.5", units="vol %", type="LL",
             voting="2oo3", sil="SIL2", latch="YES", reset="MANUAL", group="combustion"),
        dict(tag="PZT-141", desc="Firebox pressure high-high", sp="+2.0", units="mmH2O", type="HH",
             voting="2oo3", sil="SIL2",
             latch="NO" if seeded else "YES",            # SEEDED: fuel gas trip not latched
             reset="MANUAL", group="combustion"),
        dict(tag="LZT-130", desc="Steam drum level low-low", sp="20", units="%", type="LL",
             voting="2oo3", sil="SIL2", latch="YES", reset="MANUAL", group="process"),
        dict(tag="PZT-170", desc="Fuel gas pressure low-low", sp="0.5", units="barg", type="LL",
             voting="2oo3", sil="SIL2", latch="YES", reset="MANUAL", group="combustion"),
        dict(tag="BZS-171", desc="Flame failure", sp="—", units="—", type="FAIL",
             voting="1oo1" if seeded else "1oo2",        # SEEDED: SIL2 trip on a single sensor
             sil="SIL2", latch="YES", reset="MANUAL", group="flame"),
        # SEEDED: TZT-160 is on the C&E but not on the P&ID (added after a HAZOP, MOC not closed)
        dict(tag="TZT-160", desc="Tube metal temperature high-high", sp="1080", units="°C", type="HH",
             voting="1oo2", sil="SIL1", latch="YES", reset="MANUAL", group="combustion"),
        dict(tag="HS-199", desc="Emergency shutdown push button", sp="—", units="—", type="MAN",
             voting="1oo1", sil="SIL1", latch="YES", reset="MANUAL", group="esd"),
    ]
    if not seeded:
        rows.append(dict(tag="PT-172", desc="Fuel gas pressure high-high", sp="3.5", units="barg", type="HH",
                         voting="2oo3", sil="SIL2", latch="YES", reset="MANUAL", group="combustion"))
    for i, r in enumerate(rows, start=1):
        r["id"] = f"C{i:02d}"
    return rows


CE_EFFECTS = [
    # (effect id, tag, description, default action, required safe position)
    ("E01", "XV-100", "Ethane feed shutoff valve", "CLOSE", "CLOSED"),
    ("E02", "FV-100", "Ethane feed flow control valve", "CLOSE", "CLOSED"),
    ("E03", "FV-110", "Dilution steam control valve (keep steam on coils)", "OPEN", "OPEN"),
    ("E04", "TV-150", "Fuel gas control valve (COT)", "CLOSE", "CLOSED"),
    ("E05", "XV-170", "Fuel gas first shutoff valve", "CLOSE", "CLOSED"),
    ("E06", "XV-171", "Fuel gas second shutoff valve", "CLOSE", "CLOSED"),
    ("E07", "XV-172", "Fuel gas vent valve (bleed)", "OPEN", "OPEN"),
    ("E08", "XV-175", "Pilot gas first shutoff valve", "CLOSE", "CLOSED"),
    ("E09", "XV-176", "Pilot gas second shutoff valve", "CLOSE", "CLOSED"),
]

# Which effect columns each kind of trip drives. 'X' means "use the column's default action".
_PROCESS = {"XV-100": "X", "FV-100": "X", "FV-110": "X"}
_MAIN_FUEL = {**_PROCESS, "TV-150": "X", "XV-170": "X", "XV-171": "X", "XV-172": "X"}
_ALL_FUEL = {**_MAIN_FUEL, "XV-175": "X", "XV-176": "X"}


def effect_groups(seeded: bool = True) -> dict[str, dict[str, str]]:
    return {
        "process": _PROCESS,
        # SEEDED: COT high-high written as OPEN on the fuel gas control valve (should be CLOSE).
        "cot": {**_PROCESS, "TV-150": "OPEN" if seeded else "CLOSE"},
        "combustion": _MAIN_FUEL,
        "flame": _ALL_FUEL,
        "esd": _ALL_FUEL,
    }


# ---------------------------------------------------------------------------
# DEXPI / Proteus XML writer
# ---------------------------------------------------------------------------

_RDL = "http://sandbox.dexpi.org/rdl/"


class _Ids:
    def __init__(self):
        self.n = 0

    def __call__(self, cls: str) -> str:
        self.n += 1
        return f"{cls}-{self.n}"


def _attrs(parent: ET.Element, attrs: list[tuple[str, str, str]]) -> None:
    """Add a DEXPI GenericAttributes block. attrs: (name, value, format)."""
    attrs = [a for a in attrs if a[1]]
    if not attrs:
        return
    block = ET.SubElement(parent, "GenericAttributes", Set="DexpiAttributes", Number=str(len(attrs)))
    for name, value, fmt in attrs:
        ET.SubElement(block, "GenericAttribute", Name=name, AttributeURI=_RDL + name,
                      Format=fmt, Value=value)


def _el(parent, tag, cls, ident, **extra) -> ET.Element:
    return ET.SubElement(parent, tag, ID=ident, ComponentClass=cls,
                         ComponentClassURI=_RDL + cls, **extra)


def build_pid_xml(seeded: bool = True) -> bytes:
    """Return the synthetic furnace P&ID as DEXPI 1.3 Proteus XML bytes."""
    ids = _Ids()
    root = ET.Element("PlantModel")
    ET.SubElement(root, "PlantInformation", Application="Dexpi", ApplicationVersion="1.3.1",
                  Date="2026-01-01", Discipline="PID", Is3D="no",
                  OriginatingSystem="interlock-checker synthetic generator (" + SYNTHETIC_LABEL + ")",
                  OriginatingSystemVendor="none (synthetic)", OriginatingSystemVersion="1.0",
                  SchemaVersion="4.1.1", Time="00:00:00", Units="mm")
    meta = _el(root, "MetaData", "MetaData", "MetaData-1")
    _attrs(meta, [
        ("DrawingNameAssignmentClass", f"{SYNTHETIC_LABEL} – Ethane cracking furnace F-101 SIS", "string"),
        ("DrawingNumberAssignmentClass", "SYN-PID-F101" + ("" if seeded else "-CLEAN"), "string"),
        ("EnterpriseNameAssignmentClass", "None – synthetic training data, no real plant", "string"),
    ])

    for cls, tag in EQUIPMENT:
        eq = _el(root, "Equipment", cls, ids(cls))
        _attrs(eq, [("TagNameAssignmentClass", tag, "string")])

    for loop in pid_loops(seeded):
        pif_id = ids("ProcessInstrumentationFunction")
        # Actuating systems are top-level elements that carry the fail action.
        functions = []
        for vtag, fail in loop["valves"]:
            af_id, as_id, ca_id = ids("ActuatingFunction"), ids("ActuatingSystem"), ids("ControlledActuator")
            asys = _el(root, "ActuatingSystem", "ActuatingSystem", as_id)
            _attrs(asys, [("ActuatingSystemNumberAssignmentClass", vtag, "string")])
            ET.SubElement(asys, "Association", Type="fulfills", ItemID=af_id)
            act = _el(asys, "ActuatingSystemComponent", "ControlledActuator", ca_id)
            short = {"FailClose": "F.C.", "FailOpen": "F.O.", "FailRetainPosition": "F.L."}[fail]
            _attrs(act, [("FailActionSpecialization", fail, "anyURI"),
                         ("FailActionRepresentationAssignmentClass", short, "string")])
            functions.append((vtag, af_id, as_id))

        pif = _el(root, "ProcessInstrumentationFunction", "ProcessInstrumentationFunction", pif_id)
        _attrs(pif, [
            ("ProcessInstrumentationFunctionCategoryAssignmentClass", loop["cat"], "string"),
            ("ProcessInstrumentationFunctionModifierAssignmentClass", loop["mod"], "string"),
            ("ProcessInstrumentationFunctionNumberAssignmentClass", loop["num"], "string"),
            ("DeviceInformationAssignmentClass", loop["desc"], "string"),
            ("SafetyRelevanceClassAssignmentClass", loop.get("sil", ""), "string"),
            ("VotingSystemRepresentationAssignmentClass", loop.get("voting", ""), "string"),
        ])
        for ttag in loop["transmitters"]:
            sgf = _el(pif, "ProcessSignalGeneratingFunction", "ProcessSignalGeneratingFunction",
                      ids("ProcessSignalGeneratingFunction"))
            _attrs(sgf, [("ProcessSignalGeneratingFunctionNumberAssignmentClass", ttag, "string")])
        for vtag, af_id, as_id in functions:
            af = _el(pif, "ActuatingFunction", "ActuatingFunction", af_id)
            _attrs(af, [("ActuatingFunctionNumberAssignmentClass", vtag, "string")])
            ET.SubElement(af, "Association", Type="is fulfilled by", ItemID=as_id)

    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    banner = (f"<!-- {SYNTHETIC_LABEL}. Invented ethane cracking furnace P&ID for the interlock "
              "checker example. Not based on any real plant. "
              + ("Contains deliberate mismatches (see README). " if seeded else "Clean variant. ")
              + "-->\n")
    return ('<?xml version="1.0" encoding="utf-8"?>\n' + banner + body + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# C&E Excel writer (IEC 62881 style layout)
# ---------------------------------------------------------------------------

CAUSE_HEADERS = ["Cause ID", "Initiator tag", "Description", "Trip setpoint", "Units",
                 "Trip type", "Voting", "SIL", "Latching", "Reset", "Notes"]
EFFECT_LABELS = ["Effect ID", "Final element tag", "Description", "Action on trip",
                 "Required safe position"]
HEADER_ROW = 10          # row with the cause column headings
FIRST_EFFECT_ROW = 5     # first of the five effect label rows

_RED = PatternFill("solid", fgColor="C8372D")
_GREY = PatternFill("solid", fgColor="E7E6E2")
_LINK = PatternFill("solid", fgColor="FCE4B6")
_THIN = Side(style="thin", color="999999")
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _stamp(ws, title: str, width: int) -> None:
    """Put the SYNTHETIC banner on top of a sheet and in its print header/footer."""
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    cell = ws.cell(row=1, column=1, value=SYNTHETIC_LABEL)
    cell.font = Font(bold=True, color="FFFFFF", size=14)
    cell.fill = _RED
    cell.alignment = Alignment(horizontal="center")
    ws.cell(row=2, column=1, value=title).font = Font(bold=True, size=12)
    ws.cell(row=3, column=1, value="Invented data for training. Not based on any real plant. "
                                    "Do not use for design, operation or SIL verification.")
    ws.oddHeader.center.text = SYNTHETIC_LABEL
    ws.oddFooter.center.text = SYNTHETIC_LABEL


def build_ce_workbook(seeded: bool = True) -> Workbook:
    causes = ce_causes(seeded)
    groups = effect_groups(seeded)
    wb = Workbook()
    ws = wb.active
    ws.title = "C&E Matrix"
    n_cols = len(CAUSE_HEADERS) + len(CE_EFFECTS)
    _stamp(ws, "Cause & Effect Matrix – Ethane cracking furnace F-101 SIS (IEC 62881 style)"
           + ("" if seeded else " – clean variant"), n_cols)

    label_col = len(CAUSE_HEADERS)              # effect labels sit in the 'Notes' column
    first_eff_col = label_col + 1
    for i, label in enumerate(EFFECT_LABELS):
        c = ws.cell(row=FIRST_EFFECT_ROW + i, column=label_col, value=label)
        c.font, c.fill, c.border = Font(bold=True), _GREY, _BOX
        c.alignment = Alignment(horizontal="right")
    for j, eff in enumerate(CE_EFFECTS):
        for i, value in enumerate(eff):
            c = ws.cell(row=FIRST_EFFECT_ROW + i, column=first_eff_col + j, value=value)
            c.border, c.alignment = _BOX, Alignment(horizontal="center", wrap_text=True)
            if i == 2:
                c.alignment = Alignment(text_rotation=90, horizontal="center", wrap_text=True)
    ws.row_dimensions[FIRST_EFFECT_ROW + 2].height = 150

    for k, head in enumerate(CAUSE_HEADERS, start=1):
        c = ws.cell(row=HEADER_ROW, column=k, value=head)
        c.font, c.fill, c.border = Font(bold=True), _GREY, _BOX

    for r, cause in enumerate(causes, start=HEADER_ROW + 1):
        values = [cause["id"], cause["tag"], cause["desc"], cause["sp"], cause["units"], cause["type"],
                  cause["voting"], cause["sil"], cause["latch"], cause["reset"], ""]
        for k, v in enumerate(values, start=1):
            ws.cell(row=r, column=k, value=v).border = _BOX
        links = groups[cause["group"]]
        for j, eff in enumerate(CE_EFFECTS):
            c = ws.cell(row=r, column=first_eff_col + j, value=links.get(eff[1]))
            c.border, c.alignment = _BOX, Alignment(horizontal="center")
            if c.value:
                c.fill = _LINK

    widths = [9, 14, 34, 12, 12, 9, 8, 7, 10, 10, 24]
    for k, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(k)].width = w
    for j in range(len(CE_EFFECTS)):
        ws.column_dimensions[get_column_letter(first_eff_col + j)].width = 10
    ws.freeze_panes = ws.cell(row=HEADER_ROW + 1, column=first_eff_col)

    legend = wb.create_sheet("Legend")
    _stamp(legend, "How to read this matrix", 4)
    lines = [
        ("Row", "One cause: an initiator (trip transmitter or push button) and its trip setting."),
        ("Column", "One effect: a final element (valve, motor) and the safe position it must reach."),
        ("X", "At an intersection: the cause drives the effect with the column's 'Action on trip'."),
        ("CLOSE / OPEN / STOP", "At an intersection: the cause drives the effect with this action."),
        ("Voting", "e.g. 2oo3 = two out of three transmitters must agree before the trip acts."),
        ("Latching", "YES = the trip stays active after the process returns to normal."),
        ("Reset", "MANUAL = an operator must reset the trip; AUTO = it clears by itself."),
        ("Source", "Trips follow the trainer in this repository (src/engine.js); four typical "
                   "furnace trips were added. All values are invented."),
    ]
    for i, (a, b) in enumerate(lines, start=5):
        legend.cell(row=i, column=1, value=a).font = Font(bold=True)
        legend.cell(row=i, column=2, value=b)
    legend.column_dimensions["A"].width = 22
    legend.column_dimensions["B"].width = 100
    return wb


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def write_examples(out_dir: str | Path) -> list[Path]:
    """Write the seeded and the clean example pair into out_dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for seeded, suffix in ((True, ""), (False, "_clean")):
        pid = out / f"synthetic_furnace_pid{suffix}.xml"
        pid.write_bytes(build_pid_xml(seeded))
        ce = out / f"synthetic_furnace_ce{suffix}.xlsx"
        build_ce_workbook(seeded).save(ce)
        written += [pid, ce]
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the SYNTHETIC example P&ID and C&E files.")
    parser.add_argument("--out", default="examples", help="output folder (default: examples)")
    args = parser.parse_args(argv)
    for path in write_examples(args.out):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
