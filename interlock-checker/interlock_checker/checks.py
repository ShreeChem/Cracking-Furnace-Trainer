"""Steps 3 to 5: the three built-in consistency checks.

Each check compares the P&ID tag list with the C&E matrix and returns a list
of Finding objects. None of them change the inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import FAIL_CLOSE, FAIL_LAST, FAIL_OPEN, CeMatrix, Finding, PidData, norm_tag

CHECK_1 = "1. C&E tag missing from P&ID"
CHECK_2 = "2. Trip transmitter missing from C&E"
CHECK_3 = "3. Valve fail position vs trip action"

# Safe-position words in the C&E that agree with each trip action.
_POSITION_WORDS = {"CLOSE": ("CLOSE", "CLOSED"), "OPEN": ("OPEN", "OPENED")}
_FAIL_WORDS = {FAIL_CLOSE: "fail-close (FC)", FAIL_OPEN: "fail-open (FO)", FAIL_LAST: "fail-last (FL)"}


@dataclass
class CheckSettings:
    """Tunable parts of the checks. Read from the 'settings' block of the rules file."""

    # Regular expressions; a P&ID transmitter whose tag matches any of them is a trip transmitter.
    # The default catches ISA-style safety tags with a 'Z' after the first letter (FZT, PZT, BZS ...).
    trip_transmitter_patterns: list[str] = field(default_factory=lambda: [r"^[A-Z]Z[A-Z]*-?\d"])
    # Also treat any transmitter with a safety class on the P&ID (e.g. SIL2) as a trip transmitter.
    treat_safety_class_as_trip: bool = True
    # Which fail position gives the safe state for each trip action.
    action_to_fail_position: dict[str, str] = field(
        default_factory=lambda: {"CLOSE": FAIL_CLOSE, "OPEN": FAIL_OPEN}
    )

    @classmethod
    def from_dict(cls, data: dict | None) -> "CheckSettings":
        data = dict(data or {})
        s = cls()
        if "trip_transmitter_patterns" in data:
            pats = data.pop("trip_transmitter_patterns") or []
            s.trip_transmitter_patterns = [pats] if isinstance(pats, str) else list(pats)
        if "treat_safety_class_as_trip" in data:
            s.treat_safety_class_as_trip = bool(data.pop("treat_safety_class_as_trip"))
        if "action_to_fail_position" in data:
            s.action_to_fail_position = {str(k).upper(): str(v).upper()
                                         for k, v in (data.pop("action_to_fail_position") or {}).items()}
        if data:
            raise ValueError(f"Unknown setting(s) in the rules file: {', '.join(sorted(data))}")
        for p in s.trip_transmitter_patterns:
            try:
                re.compile(p)
            except re.error as exc:
                raise ValueError(f"Trip transmitter pattern '{p}' is not a valid pattern: {exc}") from exc
        return s


def check_ce_tags_on_pid(pid: PidData, ce: CeMatrix) -> list[Finding]:
    """Check 1: every initiator and final element in the C&E must exist on the P&ID."""
    findings = []
    for cause in ce.causes:
        if pid.get(cause.tag) is None:
            findings.append(Finding(
                check=CHECK_1, tags=[cause.tag], severity="HIGH",
                explanation=(
                    f"Cause {cause.cause_id} ({cause.description or 'no description'}) uses initiator "
                    f"{cause.tag}, but no instrument with that tag is on the P&ID. The trip may exist "
                    "only on paper: like a trip test sheet for a transmitter nobody can find in the field."
                ),
                suggested_action=(
                    "Check whether the tag is mistyped in the C&E or missing from the P&ID. If the "
                    "instrument was added later (e.g. after a HAZOP), make sure the MOC updates the P&ID."
                ),
            ))
    for eff in ce.effects:
        if pid.get(eff.tag) is None:
            findings.append(Finding(
                check=CHECK_1, tags=[eff.tag], severity="HIGH",
                explanation=(
                    f"Effect {eff.effect_id} ({eff.description or 'no description'}) acts on final "
                    f"element {eff.tag}, but that tag is not on the P&ID. Nobody can confirm the valve "
                    "or motor exists, or what its fail position is."
                ),
                suggested_action=(
                    "Confirm the final element exists and add it to the P&ID with its fail position, "
                    "or correct the tag in the C&E."
                ),
            ))
    return findings


def is_trip_transmitter(item, settings: CheckSettings) -> bool:
    if item.kind != "transmitter":
        return False
    if settings.treat_safety_class_as_trip and item.safety_class:
        return True
    return any(re.search(p, item.tag, re.IGNORECASE) for p in settings.trip_transmitter_patterns)


def check_trip_transmitters_in_ce(pid: PidData, ce: CeMatrix,
                                  settings: CheckSettings | None = None) -> list[Finding]:
    """Check 2: every trip transmitter on the P&ID must have a cause row in the C&E."""
    settings = settings or CheckSettings()
    ce_tags = {norm_tag(c.tag) for c in ce.causes}
    findings = []
    for item in pid.items.values():
        if not is_trip_transmitter(item, settings) or norm_tag(item.tag) in ce_tags:
            continue
        why = []
        if item.safety_class:
            why.append(f"it is marked {item.safety_class} on the P&ID")
        if any(re.search(p, item.tag, re.IGNORECASE) for p in settings.trip_transmitter_patterns):
            why.append("its tag follows the trip transmitter naming pattern")
        findings.append(Finding(
            check=CHECK_2, tags=[item.tag], severity="HIGH",
            explanation=(
                f"{item.tag} ({item.description or 'no description'}) looks like a trip transmitter "
                f"because {' and '.join(why)}, but no C&E row uses it. Either a trip is missing from "
                "the C&E, or the instrument is wrongly marked as safety related."
            ),
            suggested_action=(
                "Ask the SIS engineer whether this transmitter should initiate a trip. If yes, add "
                "the cause row (setpoint, voting, latching, reset) to the C&E; if no, correct the P&ID."
            ),
        ))
    return findings


def check_fail_positions(pid: PidData, ce: CeMatrix,
                         settings: CheckSettings | None = None) -> list[Finding]:
    """Check 3: a valve's fail position must give the same state as its trip action.

    Most trips work by removing air or power, so the valve goes to its fail
    position. If the C&E asks for CLOSE but the valve fails open, losing the
    instrument air would leave the plant in the unsafe state.
    """
    settings = settings or CheckSettings()
    findings = []
    for eff in ce.effects:
        item = pid.get(eff.tag)
        if item is None:
            continue                      # already reported by check 1
        # Group the causes by the action they ask for at this valve.
        by_action: dict[str, list[str]] = {}
        for cause, action in ce.causes_of(eff):
            by_action.setdefault(action.upper(), []).append(cause.cause_id)
        if not by_action and eff.action:
            by_action[eff.action.upper()] = []

        for action, cause_ids in by_action.items():
            needed = settings.action_to_fail_position.get(action)
            if needed is None:
                continue                  # e.g. STOP on a motor: no fail position to compare
            if not cause_ids:
                who = "the effect column"
            elif len(cause_ids) == len(ce.causes) > 1:
                who = f"all {len(cause_ids)} causes"
            else:
                who = f"cause{'s' if len(cause_ids) > 1 else ''} {', '.join(cause_ids)}"
            fail = item.fail_action
            note = ""
            fix = ("Find out which document is right. Correct the C&E action, or change the "
                   f"actuator to {_FAIL_WORDS[needed]} through MOC, then repeat the trip test.")
            if eff.safe_position and eff.safe_position not in _POSITION_WORDS.get(action, (eff.safe_position,)):
                note = (f" The C&E column itself says the required safe position is "
                        f"{eff.safe_position}, so the '{action}' entry may be the error.")
                fix = (f"The C&E disagrees with itself. Check the '{action}' entry for {who} against the "
                       f"required safe position ({eff.safe_position}) with the SIS engineer and correct it.")
            if fail is None:
                findings.append(Finding(
                    check=CHECK_3, tags=[eff.tag], severity="LOW",
                    explanation=(
                        f"The C&E asks {eff.tag} to {action} ({who}), but the P&ID shows no fail "
                        "position for it, so the fail-safe direction cannot be checked." + note
                    ),
                    suggested_action="Add the fail position (FC / FO / FL) to the P&ID or the valve data sheet.",
                ))
            elif fail == FAIL_LAST:
                findings.append(Finding(
                    check=CHECK_3, tags=[eff.tag], severity="MEDIUM",
                    explanation=(
                        f"The C&E asks {eff.tag} to {action} ({who}), but the P&ID shows it "
                        "fail-last (FL). On loss of air or power the valve stays where it is, so the "
                        "trip only works while the actuator still has energy: it is not fail-safe." + note
                    ),
                    suggested_action=(
                        f"Confirm the design intent. Either change the actuator to {_FAIL_WORDS[needed]}, "
                        "or document how the trip is guaranteed (e.g. accumulator, UPS) in the SRS."
                    ),
                ))
            elif fail != needed:
                findings.append(Finding(
                    check=CHECK_3, tags=[eff.tag], severity="HIGH",
                    explanation=(
                        f"The C&E asks {eff.tag} to {action} on trip ({who}), but the P&ID shows it "
                        f"{_FAIL_WORDS[fail]}. On loss of instrument air or power the valve goes the "
                        "opposite way to the safe state the trip needs." + note
                    ),
                    suggested_action=fix,
                ))
    return findings


def run_builtin_checks(pid: PidData, ce: CeMatrix, settings: CheckSettings | None = None) -> list[Finding]:
    settings = settings or CheckSettings()
    return (check_ce_tags_on_pid(pid, ce)
            + check_trip_transmitters_in_ce(pid, ce, settings)
            + check_fail_positions(pid, ce, settings))
