"""Shared test helpers: paths to the example files and small in-memory inputs."""

from pathlib import Path

import pytest

from interlock_checker.models import Cause, CeMatrix, Effect, PidData, PidItem

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
RULES = ROOT / "rules" / "rules.yaml"
PUBLIC_C01 = EXAMPLES / "public" / "C01V04-VER.EX01.xml"


@pytest.fixture
def seeded_files():
    return EXAMPLES / "synthetic_furnace_pid.xml", EXAMPLES / "synthetic_furnace_ce.xlsx"


@pytest.fixture
def clean_files():
    return EXAMPLES / "synthetic_furnace_pid_clean.xml", EXAMPLES / "synthetic_furnace_ce_clean.xlsx"


def make_pid(*items: PidItem) -> PidData:
    pid = PidData(source="test")
    for item in items:
        pid.add(item)
    return pid


@pytest.fixture
def clean_pair():
    """A tiny consistent P&ID + C&E: one trip transmitter closing one fail-close valve."""
    pid = make_pid(
        PidItem("PZT-1", "transmitter", safety_class="SIL2", voting="2oo3"),
        PidItem("XV-1", "final_element", fail_action="FC"),
        PidItem("XV-2", "final_element", fail_action="FO"),
        PidItem("PT-9", "transmitter"),            # ordinary transmitter, not a trip
    )
    ce = CeMatrix(source="test")
    ce.causes.append(Cause("C01", "PZT-1", "Pressure low-low", voting="2oo3", sil="SIL2",
                           latching="YES", reset="MANUAL"))
    ce.effects += [Effect("E01", "XV-1", "Shutoff", "CLOSE", "CLOSED"),
                   Effect("E02", "XV-2", "Vent", "OPEN", "OPEN")]
    ce.links[("C01", "E01")] = "CLOSE"
    ce.links[("C01", "E02")] = "OPEN"
    return pid, ce
