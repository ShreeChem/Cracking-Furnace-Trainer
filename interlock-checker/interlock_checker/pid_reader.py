"""Step 1: read the P&ID.

The P&ID arrives as a DEXPI file (Proteus XML), the vendor-neutral exchange
format that P&ID tools such as AVEVA, SmartPlant or COMOS can export. pyDEXPI
(TU Delft, AGPL-3.0) turns that file into Python objects; this module then
walks those objects and builds a simple tag list, like reading the instrument
index off a drawing.
"""

from __future__ import annotations

from pathlib import Path

from .models import FAIL_CLOSE, FAIL_LAST, FAIL_OPEN, PidData, PidItem


class PidReadError(Exception):
    """Raised when the P&ID file cannot be read. The message says why."""


# pyDEXPI fail-action values -> short P&ID notation.
_FAIL_MAP = {
    "fail close": FAIL_CLOSE,
    "fail open": FAIL_OPEN,
    "fail retain position": FAIL_LAST,
}


def _text(value) -> str:
    """Turn an optional pyDEXPI value (str, enum or None) into clean text."""
    if value is None:
        return ""
    value = getattr(value, "value", value)       # enums carry their text in .value
    text = str(value).strip()
    return "" if text.lower() == "null" else text


def _loop_tag(pif) -> str:
    """Build a loop tag such as 'FZT-101A' from the parts DEXPI stores separately."""
    category = _text(pif.processInstrumentationFunctionCategory)
    modifier = _text(pif.processInstrumentationFunctionModifier)
    number = _text(pif.processInstrumentationFunctionNumber)
    if not number:
        return ""
    letters = category + modifier
    return f"{letters}-{number}" if letters else number


def _fail_action(actuating_system) -> str | None:
    if actuating_system is None or actuating_system.controlledActuator is None:
        return None
    return _FAIL_MAP.get(_text(actuating_system.controlledActuator.failAction).lower())


def load_dexpi_model(path: str | Path):
    """Load a DEXPI Proteus XML file with pyDEXPI and return the model.

    Fails loudly with a PidReadError instead of returning an empty result.
    """
    path = Path(path)
    if not path.is_file():
        raise PidReadError(f"P&ID file not found: {path}")
    try:
        from pydexpi.loaders import ProteusSerializer
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise PidReadError(
            "pyDEXPI is not installed. Run:  pip install pydexpi"
        ) from exc

    serializer = ProteusSerializer()
    try:
        model = serializer.load_from_bytes(path.read_bytes())
    except Exception as exc:
        raise PidReadError(
            f"Could not read '{path.name}' as a DEXPI (Proteus XML) P&ID: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if model is None or model.conceptualModel is None:
        raise PidReadError(
            f"'{path.name}' was read but contains no DEXPI plant model. "
            "Is it a DEXPI Proteus XML export?"
        )
    return model, serializer


def read_pid(path: str | Path) -> PidData:
    """Read a DEXPI P&ID and return every tag the checks need."""
    model, serializer = load_dexpi_model(path)
    cm = model.conceptualModel
    data = PidData(source=str(path))

    # Equipment: furnace, fans, pumps, drums ...
    for item in cm.taggedPlantItems:
        data.add(PidItem(tag=_text(item.tagName), kind="equipment",
                         description=type(item).__name__))

    # Actuating systems carry the valve fail position (FC / FO / FL).
    for system in cm.actuatingSystems:
        data.add(PidItem(tag=_text(system.actuatingSystemNumber), kind="final_element",
                         fail_action=_fail_action(system)))

    # Instrument loops: the bubble on the P&ID, with its transmitters and valves.
    for pif in cm.processInstrumentationFunctions:
        loop = _loop_tag(pif)
        common = dict(
            loop=loop,
            description=_text(pif.deviceInformation),
            safety_class=_text(pif.safetyRelevanceClass),
            voting=_text(pif.votingSystemRepresentation),
        )
        for sgf in pif.processSignalGeneratingFunctions:
            data.add(PidItem(tag=_text(sgf.processSignalGeneratingFunctionNumber),
                             kind="transmitter", **common))
        for af in pif.actuatingFunctions:
            data.add(PidItem(tag=_text(af.actuatingFunctionNumber), kind="final_element",
                             fail_action=_fail_action(af.systems), **common))
        for aef in pif.actuatingElectricalFunctions:
            data.add(PidItem(tag=_text(aef.actuatingElectricalFunctionNumber),
                             kind="final_element", **common))
        # Added last, so a transmitter or valve with the same tag keeps its own kind.
        data.add(PidItem(tag=loop, kind="loop", **common))

    if not data.items:
        raise PidReadError(
            f"No tagged items (equipment, instruments or valves) were found in "
            f"'{Path(path).name}'. The file loaded, but there is nothing to check."
        )

    # Pass on pyDEXPI's own error messages so lost data is never silent.
    for entry in serializer.get_loading_errors().get_errors():
        if _text(entry.level).lower() in ("error", "critical"):
            data.warnings.append(f"pyDEXPI {_text(entry.level)}: {entry.message}")
    return data
