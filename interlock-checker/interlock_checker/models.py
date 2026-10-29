"""Plain data containers shared by the readers, the checks and the report.

Think of these as the blank forms the tool fills in: one form per instrument
on the P&ID, one per cause row and effect column of the C&E matrix, and one
per finding in the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Severity order used for sorting the report (most serious first).
SEVERITIES = ("HIGH", "MEDIUM", "LOW", "INFO")


def norm_tag(tag: str | None) -> str:
    """Return a tag in a form that ignores spacing, case and separators.

    'FZT-101A', 'fzt 101a' and 'FZT_101A' all become 'FZT101A', so a tag typed
    slightly differently on the P&ID and in the C&E still matches.
    """
    if tag is None:
        return ""
    return re.sub(r"[\s\-_/]", "", str(tag)).upper()


# Fail positions in the short form used on P&IDs.
FAIL_CLOSE = "FC"
FAIL_OPEN = "FO"
FAIL_LAST = "FL"


@dataclass
class PidItem:
    """One tagged item found on the P&ID (instrument, valve, motor or equipment)."""

    tag: str
    kind: str                       # 'transmitter', 'final_element', 'loop' or 'equipment'
    description: str = ""
    loop: str = ""                  # tag of the instrument loop it belongs to
    safety_class: str = ""          # e.g. 'SIL2' if the P&ID marks it as safety related
    voting: str = ""                # e.g. '2oo3'
    fail_action: str | None = None  # 'FC', 'FO', 'FL' or None if not shown


@dataclass
class PidData:
    """Everything the checker needs from the P&ID."""

    source: str
    items: dict[str, PidItem] = field(default_factory=dict)   # key: norm_tag(tag)
    warnings: list[str] = field(default_factory=list)          # parser messages worth showing

    def add(self, item: PidItem) -> None:
        key = norm_tag(item.tag)
        if not key:
            return
        existing = self.items.get(key)
        if existing is None:
            self.items[key] = item
            return
        # Same tag seen twice (e.g. actuating function and actuating system):
        # keep the first entry but fill in anything it is missing.
        for name in ("description", "loop", "safety_class", "voting", "fail_action"):
            if not getattr(existing, name) and getattr(item, name):
                setattr(existing, name, getattr(item, name))

    def get(self, tag: str) -> PidItem | None:
        return self.items.get(norm_tag(tag))


@dataclass
class Cause:
    """One row of the C&E matrix: an initiator and how its trip behaves."""

    cause_id: str
    tag: str
    description: str = ""
    setpoint: str = ""
    units: str = ""
    trip_type: str = ""      # e.g. LL, HH
    voting: str = ""         # e.g. 2oo3
    sil: str = ""            # e.g. SIL2
    latching: str = ""       # e.g. YES / NO
    reset: str = ""          # e.g. MANUAL / AUTO
    notes: str = ""
    row: int = 0             # Excel row number, so findings can point back to the sheet


@dataclass
class Effect:
    """One column of the C&E matrix: a final element and its safe state."""

    effect_id: str
    tag: str
    description: str = ""
    action: str = ""         # default action on trip: CLOSE, OPEN, STOP, ...
    safe_position: str = ""  # required safe position: CLOSED, OPEN, STOPPED, ...
    column: str = ""         # Excel column letter


@dataclass
class CeMatrix:
    """The whole cause-and-effect matrix."""

    source: str
    causes: list[Cause] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)
    # links[(cause_id, effect_id)] = action written in the intersection cell
    links: dict[tuple[str, str], str] = field(default_factory=dict)

    def effects_of(self, cause: Cause) -> list[tuple[Effect, str]]:
        """Effects driven by one cause, with the action at each intersection."""
        out = []
        for eff in self.effects:
            action = self.links.get((cause.cause_id, eff.effect_id))
            if action:
                out.append((eff, action))
        return out

    def causes_of(self, effect: Effect) -> list[tuple[Cause, str]]:
        """Causes that drive one effect, with the action at each intersection."""
        out = []
        for cause in self.causes:
            action = self.links.get((cause.cause_id, effect.effect_id))
            if action:
                out.append((cause, action))
        return out


@dataclass
class Finding:
    """One line of the mismatch report."""

    check: str
    tags: list[str]
    severity: str
    explanation: str
    suggested_action: str
    finding_id: str = ""     # filled in when the report is numbered

    @property
    def tag_text(self) -> str:
        return ", ".join(self.tags)
