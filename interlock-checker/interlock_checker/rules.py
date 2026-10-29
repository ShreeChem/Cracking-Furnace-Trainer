"""Step 6: latching and reset rules, written by the user in a YAML (or JSON) file.

A rule reads like a line in a site philosophy document:

    "For every C&E row that acts on a fuel gas shutoff valve,
     latching must be YES and reset must be MANUAL."

In the file that becomes a 'when' part (which C&E rows the rule looks at) and a
'require' part (what must be true for those rows). See rules/rules.yaml and the
GUIDE for the full list of fields and tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .checks import CheckSettings
from .models import SEVERITIES, Cause, CeMatrix, Finding

CHECK_4 = "4. Latching / reset rule"

# C&E cause fields a rule may test (the column names of the C&E, in snake_case).
CAUSE_FIELDS = ("cause_id", "tag", "description", "setpoint", "units", "trip_type",
                "voting", "sil", "latching", "reset", "notes")


class RulesError(Exception):
    """Raised when the rules file has a mistake. The message points to it."""


def _number(text: str) -> float | None:
    """First number in a text: 'SIL2' -> 2, '0.5 barg' -> 0.5, '2oo3' -> 2."""
    m = re.search(r"-?\d+(\.\d+)?", text or "")
    return float(m.group()) if m else None


def _word(value) -> str:
    """YAML reads an unquoted YES / NO as true / false; turn those back into words."""
    if isinstance(value, bool):
        return "YES" if value else "NO"
    return str(value).strip()


def _as_list(arg) -> list[str]:
    return [_word(a).upper() for a in (arg if isinstance(arg, (list, tuple)) else [arg])]


# ---------------------------------------------------------------------------
# Tests that can be used in 'when' and 'require'. To add one, write a small
# function (value, argument) -> True/False and register it here.
# ---------------------------------------------------------------------------
OPERATORS = {
    "equals": lambda v, a: v.upper() == _word(a).upper(),
    "not": lambda v, a: v.upper() != _word(a).upper(),
    "one_of": lambda v, a: v.upper() in _as_list(a),
    "not_one_of": lambda v, a: v.upper() not in _as_list(a),
    "matches": lambda v, a: re.search(str(a), v, re.IGNORECASE) is not None,
    "not_matches": lambda v, a: re.search(str(a), v, re.IGNORECASE) is None,
    "min": lambda v, a: _number(v) is not None and _number(v) >= float(a),
    "max": lambda v, a: _number(v) is not None and _number(v) <= float(a),
    "empty": lambda v, a: (v.strip() == "") == bool(a),
}

_OPERATOR_WORDS = {
    "equals": "be '{a}'", "not": "not be '{a}'", "one_of": "be one of {a}",
    "not_one_of": "not be any of {a}", "matches": "match the pattern '{a}'",
    "not_matches": "not match the pattern '{a}'", "min": "be at least {a}",
    "max": "be at most {a}", "empty": "be empty",
}


def _normalise_test(test) -> dict:
    """Turn the short forms into {operator: argument}.

    'YES'           -> {'equals': 'YES'}
    ['A', 'B']      -> {'one_of': ['A', 'B']}
    {'not': 'AUTO'} -> unchanged
    """
    if isinstance(test, dict):
        return test
    if isinstance(test, (list, tuple)):
        return {"one_of": list(test)}
    return {"equals": test}


def _describe(test: dict) -> str:
    parts = []
    for op, arg in test.items():
        if op == "empty" and not arg:
            parts.append("not be empty")
        else:
            shown = [_word(x) for x in arg] if isinstance(arg, (list, tuple)) else _word(arg)
            parts.append(_OPERATOR_WORDS.get(op, op + " {a}").format(a=shown))
    return " and ".join(parts)


@dataclass
class Rule:
    rule_id: str
    title: str
    severity: str
    require: dict[str, dict]
    when: dict[str, dict] = field(default_factory=dict)
    acts_on: dict = field(default_factory=dict)   # optional filter on the effects a cause drives
    explanation: str = ""
    suggested_action: str = ""
    placeholder: bool = False
    enabled: bool = True


@dataclass
class RuleSet:
    settings: CheckSettings
    rules: list[Rule]
    source: str = ""

    @property
    def placeholders(self) -> list[Rule]:
        return [r for r in self.rules if r.placeholder and r.enabled]


def _check_tests(where: str, tests: dict) -> dict[str, dict]:
    out = {}
    for fld, test in (tests or {}).items():
        if fld not in CAUSE_FIELDS:
            raise RulesError(f"{where}: unknown C&E field '{fld}'. Allowed fields: {', '.join(CAUSE_FIELDS)}")
        test = _normalise_test(test)
        for op, arg in test.items():
            if op not in OPERATORS:
                raise RulesError(f"{where}, field '{fld}': unknown test '{op}'. "
                                 f"Allowed tests: {', '.join(OPERATORS)}")
            if op in ("matches", "not_matches"):
                try:
                    re.compile(str(arg))
                except re.error as exc:
                    raise RulesError(f"{where}, field '{fld}': bad pattern '{arg}': {exc}") from exc
            if op in ("min", "max"):
                try:
                    float(arg)
                except (TypeError, ValueError) as exc:
                    raise RulesError(f"{where}, field '{fld}': '{op}' needs a number, got '{arg}'") from exc
        out[fld] = test
    return out


def parse_rules(data: dict, source: str = "") -> RuleSet:
    """Check and convert the content of a rules file. Errors name the rule and field."""
    if not isinstance(data, dict):
        raise RulesError("The rules file must contain 'settings' and/or 'rules' at the top level.")
    unknown = set(data) - {"settings", "rules"}
    if unknown:
        raise RulesError(f"Unknown top-level section(s): {', '.join(sorted(unknown))}. "
                         "Use 'settings' and 'rules'.")
    try:
        settings = CheckSettings.from_dict(data.get("settings"))
    except ValueError as exc:
        raise RulesError(str(exc)) from exc

    rules, seen = [], set()
    for i, raw in enumerate(data.get("rules") or [], start=1):
        where = f"Rule #{i}"
        if not isinstance(raw, dict):
            raise RulesError(f"{where} must be a set of 'key: value' lines.")
        rid = str(raw.get("id") or "").strip()
        if not rid:
            raise RulesError(f"{where} has no 'id'.")
        where = f"Rule {rid}"
        if rid in seen:
            raise RulesError(f"{where}: the id is used twice.")
        seen.add(rid)
        allowed = {"id", "title", "severity", "when", "require", "explanation",
                   "suggested_action", "placeholder", "enabled"}
        extra = set(raw) - allowed
        if extra:
            raise RulesError(f"{where}: unknown key(s) {', '.join(sorted(extra))}. "
                             f"Allowed: {', '.join(sorted(allowed))}")
        severity = str(raw.get("severity", "MEDIUM")).upper()
        if severity not in SEVERITIES:
            raise RulesError(f"{where}: severity must be one of {', '.join(SEVERITIES)}")
        if not raw.get("require"):
            raise RulesError(f"{where}: needs a 'require' section (what must be true).")

        when = dict(raw.get("when") or {})
        acts_on = when.pop("acts_on", {}) or {}
        if not isinstance(acts_on, dict) or set(acts_on) - {"tag_matches", "action"}:
            raise RulesError(f"{where}: 'acts_on' takes 'tag_matches' and/or 'action'.")
        if "tag_matches" in acts_on:
            try:
                re.compile(str(acts_on["tag_matches"]))
            except re.error as exc:
                raise RulesError(f"{where}: bad pattern in acts_on.tag_matches: {exc}") from exc

        rules.append(Rule(
            rule_id=rid,
            title=str(raw.get("title") or rid),
            severity=severity,
            when=_check_tests(f"{where} 'when'", when),
            acts_on=acts_on,
            require=_check_tests(f"{where} 'require'", raw["require"]),
            explanation=str(raw.get("explanation") or "").strip(),
            suggested_action=str(raw.get("suggested_action") or "").strip(),
            placeholder=bool(raw.get("placeholder", False)),
            enabled=bool(raw.get("enabled", True)),
        ))
    return RuleSet(settings=settings, rules=rules, source=source)


def load_rules(path: str | Path | None) -> RuleSet:
    """Load a rules file (.yaml, .yml or .json). No file -> default settings, no rules."""
    if path is None:
        return RuleSet(settings=CheckSettings(), rules=[])
    path = Path(path)
    if not path.is_file():
        raise RulesError(f"Rules file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            import yaml
            data = yaml.safe_load(text)
    except Exception as exc:
        raise RulesError(f"Could not read '{path.name}': {exc}") from exc
    return parse_rules(data or {}, source=str(path))


def _passes(cause: Cause, tests: dict[str, dict]) -> list[str]:
    """Return a list of failed fields (empty list = all tests pass)."""
    failed = []
    for fld, test in tests.items():
        value = getattr(cause, fld) or ""
        if not all(OPERATORS[op](value, arg) for op, arg in test.items()):
            failed.append(fld)
    return failed


def _acts_on(ce: CeMatrix, cause: Cause, acts_on: dict) -> list[str]:
    """Tags of the effects this cause drives that match the 'acts_on' filter."""
    hits = []
    for eff, action in ce.effects_of(cause):
        if "tag_matches" in acts_on and not re.search(str(acts_on["tag_matches"]), eff.tag, re.IGNORECASE):
            continue
        if "action" in acts_on and action.upper() not in _as_list(acts_on["action"]):
            continue
        hits.append(eff.tag)
    return hits


def check_rules(ce: CeMatrix, ruleset: RuleSet) -> list[Finding]:
    """Check 4: apply every enabled rule to every C&E cause row."""
    findings = []
    for rule in ruleset.rules:
        if not rule.enabled:
            continue
        for cause in ce.causes:
            if _passes(cause, rule.when):
                continue                     # rule does not apply to this row
            targets = []
            if rule.acts_on:
                targets = _acts_on(ce, cause, rule.acts_on)
                if not targets:
                    continue
            failed = _passes(cause, rule.require)
            if not failed:
                continue
            found = "; ".join(
                f"{f.replace('_', ' ')} is '{getattr(cause, f) or '(blank)'}' but must {_describe(rule.require[f])}"
                for f in failed)
            via = f" It acts on {', '.join(targets)}." if targets else ""
            label = " [PLACEHOLDER RULE – replace with your own]" if rule.placeholder else ""
            findings.append(Finding(
                check=f"{CHECK_4} {rule.rule_id}{label}",
                tags=[cause.tag],
                severity=rule.severity,
                explanation=(f"{rule.title}. Cause {cause.cause_id} ({cause.description or cause.tag}): "
                             f"{found}.{via} {rule.explanation}").strip(),
                suggested_action=rule.suggested_action or "Correct the C&E row or record why the exception is accepted.",
            ))
    return findings
