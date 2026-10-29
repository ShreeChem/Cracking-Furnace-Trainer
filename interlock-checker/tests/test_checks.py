import pytest

from interlock_checker.checks import (
    CheckSettings, check_ce_tags_on_pid, check_fail_positions, check_trip_transmitters_in_ce,
    run_builtin_checks,
)
from interlock_checker.models import Cause, Effect, PidItem

from conftest import make_pid


def test_clean_pair_gives_no_findings(clean_pair):
    pid, ce = clean_pair
    assert run_builtin_checks(pid, ce) == []


# ---- Check 1 ---------------------------------------------------------------

def test_check1_missing_cause_and_effect_tags(clean_pair):
    pid, ce = clean_pair
    ce.causes.append(Cause("C02", "TZT-404", "Temp high-high"))
    ce.effects.append(Effect("E03", "XV-404", "Missing valve", "CLOSE", "CLOSED"))
    found = check_ce_tags_on_pid(pid, ce)
    assert [f.tags for f in found] == [["TZT-404"], ["XV-404"]]
    assert all(f.severity == "HIGH" for f in found)
    assert "MOC" in found[0].suggested_action


def test_check1_matches_despite_spelling(clean_pair):
    pid, ce = clean_pair
    ce.causes[0].tag = "pzt 1"
    assert check_ce_tags_on_pid(pid, ce) == []


# ---- Check 2 ---------------------------------------------------------------

def test_check2_pattern_and_safety_class(clean_pair):
    pid, ce = clean_pair
    pid.add(PidItem("LZT-7", "transmitter"))                       # by tag pattern
    pid.add(PidItem("PT-8", "transmitter", safety_class="SIL1"))   # by SIL marking
    pid.add(PidItem("XZV-1", "final_element"))                     # valves are never trip transmitters
    tags = sorted(f.tags[0] for f in check_trip_transmitters_in_ce(pid, ce))
    assert tags == ["LZT-7", "PT-8"]


def test_check2_settings_can_switch_off_routes(clean_pair):
    pid, ce = clean_pair
    pid.add(PidItem("PT-8", "transmitter", safety_class="SIL1"))
    s = CheckSettings(trip_transmitter_patterns=[r"^PT-"], treat_safety_class_as_trip=False)
    tags = sorted(f.tags[0] for f in check_trip_transmitters_in_ce(pid, ce, s))
    assert tags == ["PT-8", "PT-9"]


# ---- Check 3 ---------------------------------------------------------------

def test_check3_contradiction_is_high(clean_pair):
    pid, ce = clean_pair
    pid.get("XV-2").fail_action = "FC"           # vent must OPEN but fails closed
    (f,) = check_fail_positions(pid, ce)
    assert f.severity == "HIGH" and f.tags == ["XV-2"]
    assert "fail-close (FC)" in f.explanation
    assert "fail-open (FO)" in f.suggested_action


def test_check3_fail_last_is_medium(clean_pair):
    pid, ce = clean_pair
    pid.get("XV-1").fail_action = "FL"
    (f,) = check_fail_positions(pid, ce)
    assert f.severity == "MEDIUM" and "not fail-safe" in f.explanation


def test_check3_unknown_fail_position_is_low(clean_pair):
    pid, ce = clean_pair
    pid.get("XV-1").fail_action = None
    (f,) = check_fail_positions(pid, ce)
    assert f.severity == "LOW"


def test_check3_matrix_disagrees_with_itself(clean_pair):
    pid, ce = clean_pair
    ce.links[("C01", "E01")] = "OPEN"            # column says safe position CLOSED
    (f,) = check_fail_positions(pid, ce)
    assert "disagrees with itself" in f.suggested_action
    assert "required safe position is CLOSED" in f.explanation


def test_check3_skips_motors_and_missing_tags(clean_pair):
    pid, ce = clean_pair
    pid.add(PidItem("K-1", "equipment"))
    ce.effects.append(Effect("E03", "K-1", "Fan", "STOP", "STOPPED"))
    ce.effects.append(Effect("E04", "XV-404", "Not on P&ID", "CLOSE", "CLOSED"))
    ce.links[("C01", "E03")] = "STOP"
    ce.links[("C01", "E04")] = "CLOSE"
    assert check_fail_positions(pid, ce) == []


def test_check3_uses_column_action_when_no_cause_links(clean_pair):
    pid, ce = clean_pair
    ce.links.clear()
    pid.get("XV-1").fail_action = "FO"
    (f,) = check_fail_positions(pid, ce)
    assert "the effect column" in f.explanation


def test_check3_lists_all_causes_briefly(clean_pair):
    pid, ce = clean_pair
    ce.causes.append(Cause("C02", "PZT-1", ""))
    ce.links[("C02", "E01")] = "CLOSE"
    pid.get("XV-1").fail_action = "FO"
    (f,) = check_fail_positions(pid, ce)
    assert "all 2 causes" in f.explanation


# ---- Settings --------------------------------------------------------------

def test_settings_from_dict():
    s = CheckSettings.from_dict({"trip_transmitter_patterns": "^X", "treat_safety_class_as_trip": False,
                                 "action_to_fail_position": {"close": "fc"}})
    assert s.trip_transmitter_patterns == ["^X"]
    assert s.action_to_fail_position == {"CLOSE": "FC"}


@pytest.mark.parametrize("bad, msg", [({"nonsense": 1}, "Unknown setting"),
                                      ({"trip_transmitter_patterns": ["("]}, "not a valid pattern")])
def test_settings_errors(bad, msg):
    with pytest.raises(ValueError, match=msg):
        CheckSettings.from_dict(bad)


def test_pid_add_merges_duplicate_tags():
    pid = make_pid(PidItem("XV-1", "final_element", fail_action="FC"),
                   PidItem("XV-1", "loop", description="Shutoff", safety_class="SIL2"),
                   PidItem("", "loop"))
    item = pid.get("XV-1")
    assert (item.kind, item.fail_action, item.description, item.safety_class) == \
        ("final_element", "FC", "Shutoff", "SIL2")
    assert len(pid.items) == 1
