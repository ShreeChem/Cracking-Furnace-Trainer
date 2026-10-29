import json

import pytest

from interlock_checker.models import Cause, Effect
from interlock_checker.rules import RulesError, check_rules, load_rules, parse_rules

from conftest import RULES


def test_placeholder_file_loads():
    rs = load_rules(RULES)
    assert [r.rule_id for r in rs.rules] == ["R-PH-01", "R-PH-02", "R-PH-03"]
    assert all(r.placeholder for r in rs.rules)
    assert [r.rule_id for r in rs.placeholders] == ["R-PH-01", "R-PH-02", "R-PH-03"]
    assert rs.settings.action_to_fail_position == {"CLOSE": "FC", "OPEN": "FO"}


def test_placeholder_rules_pass_on_clean_pair(clean_pair):
    _, ce = clean_pair
    assert check_rules(ce, load_rules(RULES)) == []


def test_each_placeholder_rule_fires(clean_pair):
    _, ce = clean_pair
    ce.effects[0].tag = "XV-170"                 # make it a fuel gas shutoff for R-PH-01
    c = ce.causes[0]
    c.latching, c.reset, c.voting = "NO", "AUTO", "1oo1"
    found = check_rules(ce, load_rules(RULES))
    ids = sorted(f.check.split()[5] for f in found)
    assert ids == ["R-PH-01", "R-PH-02", "R-PH-03"]
    r1 = next(f for f in found if "R-PH-01" in f.check)
    assert "PLACEHOLDER" in r1.check
    assert "latching is 'NO' but must be 'YES'" in r1.explanation
    assert "reset is 'AUTO' but must be 'MANUAL'" in r1.explanation
    assert "It acts on XV-170" in r1.explanation


def _one_rule(**kw):
    rule = {"id": "R1", "require": {"reset": "MANUAL"}}
    rule.update(kw)
    return parse_rules({"rules": [rule]})


def _cause(**kw):
    base = dict(cause_id="C1", tag="PZT-1", sil="SIL2", voting="2oo3", latching="YES",
                reset="MANUAL", trip_type="LL", setpoint="0.5")
    base.update(kw)
    return Cause(**base)


@pytest.mark.parametrize("test, value, ok", [
    ("YES", "YES", True), ("yes", "YES", True), (True, "YES", True), (False, "NO", True),
    (["A", "B"], "B", True), (["A", "B"], "C", False),
    ({"not": "AUTO"}, "AUTO", False), ({"not_one_of": ["X", "Y"]}, "Z", True),
    ({"matches": "^SIL"}, "SIL3", True), ({"not_matches": "^SIL"}, "SIL3", False),
    ({"min": 2}, "SIL2", True), ({"min": 2}, "SIL1", False), ({"max": 1}, "SIL1", True),
    ({"min": 2}, "", False), ({"empty": True}, "", True), ({"empty": False}, "", False),
])
def test_operators(clean_pair, test, value, ok):
    _, ce = clean_pair
    ce.causes = [_cause(notes=value)]
    rs = parse_rules({"rules": [{"id": "R1", "require": {"notes": test}}]})
    assert (check_rules(ce, rs) == []) is ok


def test_when_filters_rows(clean_pair):
    _, ce = clean_pair
    ce.causes = [_cause(cause_id="C1", trip_type="LL", reset="AUTO"),
                 _cause(cause_id="C2", trip_type="HH", reset="AUTO")]
    rs = _one_rule(when={"trip_type": "HH"})
    assert [f.tags for f in check_rules(ce, rs)] == [["PZT-1"]]
    assert "C2" in check_rules(ce, rs)[0].explanation


def test_acts_on_filters_by_effect(clean_pair):
    _, ce = clean_pair
    ce.causes[0].reset = "AUTO"
    assert check_rules(ce, _one_rule(when={"acts_on": {"tag_matches": "^XV-2$", "action": "OPEN"}}))
    assert not check_rules(ce, _one_rule(when={"acts_on": {"tag_matches": "^XV-2$", "action": "CLOSE"}}))
    assert not check_rules(ce, _one_rule(when={"acts_on": {"tag_matches": "^ZZ"}}))


def test_disabled_rule_is_skipped(clean_pair):
    _, ce = clean_pair
    ce.causes[0].reset = "AUTO"
    assert check_rules(ce, _one_rule(enabled=False)) == []
    assert check_rules(ce, _one_rule())[0].severity == "MEDIUM"   # default severity


def test_json_rules_file(tmp_path, clean_pair):
    _, ce = clean_pair
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"rules": [{"id": "J1", "severity": "low", "require": {"latching": "NO"},
                                        "suggested_action": "Do X"}]}))
    (f,) = check_rules(ce, load_rules(p))
    assert f.severity == "LOW" and f.suggested_action == "Do X"


def test_no_rules_file_means_defaults():
    rs = load_rules(None)
    assert rs.rules == [] and rs.settings.treat_safety_class_as_trip


@pytest.mark.parametrize("data, msg", [
    ([1, 2], "top level"),
    ({"rule": []}, "Unknown top-level"),
    ({"settings": {"bogus": 1}}, "Unknown setting"),
    ({"rules": ["text"]}, "key: value"),
    ({"rules": [{"require": {"reset": "X"}}]}, "no 'id'"),
    ({"rules": [{"id": "A", "require": {"reset": "X"}}, {"id": "A", "require": {"reset": "X"}}]}, "used twice"),
    ({"rules": [{"id": "A", "require": {"reset": "X"}, "colour": "red"}]}, "unknown key"),
    ({"rules": [{"id": "A", "require": {"reset": "X"}, "severity": "huge"}]}, "severity"),
    ({"rules": [{"id": "A"}]}, "needs a 'require'"),
    ({"rules": [{"id": "A", "require": {"colour": "X"}}]}, "unknown C&E field"),
    ({"rules": [{"id": "A", "require": {"reset": {"bigger": 1}}}]}, "unknown test"),
    ({"rules": [{"id": "A", "require": {"reset": {"matches": "("}}}]}, "bad pattern"),
    ({"rules": [{"id": "A", "require": {"sil": {"min": "two"}}}]}, "needs a number"),
    ({"rules": [{"id": "A", "require": {"reset": "X"}, "when": {"acts_on": {"colour": 1}}}]}, "acts_on"),
    ({"rules": [{"id": "A", "require": {"reset": "X"}, "when": {"acts_on": {"tag_matches": "("}}}]}, "bad pattern"),
])
def test_rule_file_mistakes_are_explained(data, msg):
    with pytest.raises(RulesError, match=msg):
        parse_rules(data)


def test_missing_and_broken_files(tmp_path):
    with pytest.raises(RulesError, match="not found"):
        load_rules(tmp_path / "none.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules: [unclosed")
    with pytest.raises(RulesError, match="Could not read"):
        load_rules(bad)
    empty = tmp_path / "empty.yaml"
    empty.write_text("# nothing here\n")
    assert load_rules(empty).rules == []


def test_effect_helpers(clean_pair):
    _, ce = clean_pair
    assert [e.tag for e, _ in ce.effects_of(ce.causes[0])] == ["XV-1", "XV-2"]
    assert [c.tag for c, _ in ce.causes_of(Effect("E01", "XV-1"))] == ["PZT-1"]
