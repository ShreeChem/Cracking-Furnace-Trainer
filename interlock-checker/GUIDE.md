# Step-by-step guide to the Interlock Consistency Checker

This guide is for process and OTS engineers who are not programmers. It walks through the
code in the order it was built. Each step shows the important lines and then explains two
things: **what it does**, and **why it matters to you**.

You do not need to understand every line to use or check the tool. If you can read a C&E
and a P&ID, you can follow this.

> All example data is **SYNTHETIC – FOR TRAINING ONLY**.

### A few words you will meet

| Code word | Plant meaning |
|---|---|
| *module* (a `.py` file) | one procedure in the binder; each does one job |
| *function* (`def name(...)`) | one step of that procedure, which takes inputs and gives a result |
| *class* / *dataclass* | a blank form with named fields, such as an instrument data sheet |
| *list* `[...]` | a column of entries, e.g. all cause rows |
| *dict* `{key: value}` | an index: look up a tag, get its data |
| *exception* (`raise ...Error`) | stop work and say why: like a permissive that blocks a start |
| *test* (`test_*.py`) | a trip test for the code: set an input, check the output |

---

## Step 0: The idea

```
P&ID (DEXPI XML) ──► Step 1: tag list ──┐
                                        ├──► Steps 3–6: four checks ──► Step 7: report
C&E (Excel)      ──► Step 2: matrix  ───┘          ▲
rules.yaml       ──────────────────────────────────┘
```

Two documents describe the same trips from different sides. The P&ID says what is
installed: transmitters, valves, fail positions. The C&E says what should happen: which
initiator closes which valve. When they disagree, at least one is wrong. Finding that at a
desk is much cheaper than finding it during a trip test, or after a real trip that did not
go to the safe state.

---

## Shared forms: `models.py`

```python
@dataclass
class PidItem:
    tag: str
    kind: str                       # 'transmitter', 'final_element', 'loop' or 'equipment'
    safety_class: str = ""          # e.g. 'SIL2'
    voting: str = ""                # e.g. '2oo3'
    fail_action: str | None = None  # 'FC', 'FO', 'FL' or None
```

**What it does.** Defines the blank forms that every later step fills in. There is a
`PidItem` per tag on the P&ID, a `Cause` per C&E row, an `Effect` per C&E column, and a
`Finding` per report line.

**Why you care.** This is the instrument index. Every check works on these forms, not on
the raw files. To support a new P&ID tool or C&E layout later, only the readers change; the
checks stay the same.

```python
def norm_tag(tag):
    return re.sub(r"[\s\-_/]", "", str(tag)).upper()
```

**What it does.** Strips spaces, hyphens, underscores and slashes and makes the tag
uppercase, so `FZT-101A`, `fzt 101a` and `FZT_101A` all become `FZT101A`.

**Why you care.** Real documents are typed by different people. Without this, every
spelling difference would show up as a false "missing tag". The trade-off is that tags
that differ *only* by a hyphen (e.g. `FV-10A` vs `FV10-A`) count as the same tag, which is
normally what you want.

---

## Step 1: Read the P&ID (`pid_reader.py`)

```python
from pydexpi.loaders import ProteusSerializer
serializer = ProteusSerializer()
model = serializer.load_from_bytes(path.read_bytes())
```

**What it does.** Hands the DEXPI file to **pyDEXPI** (TU Delft), which turns the XML into
Python objects: equipment, instrument loops, actuators and so on.

**Why you care.** DEXPI is the vendor-neutral export of a smart P&ID. Reading it means
working from the drawing's own data, not from a retyped instrument list that may already
be out of date.

```python
    except Exception as exc:
        raise PidReadError(f"Could not read '{path.name}' as a DEXPI (Proteus XML) P&ID: ...")
```

**What it does.** If anything goes wrong (file missing, not XML, not DEXPI, or no tags in
it), the tool stops and says what went wrong.

**Why you care.** A checker that silently reads nothing and then reports "0 findings"
would be worse than no checker: it would be like a bypassed trip that still shows
healthy. This makes sure a broken input can never look like a clean result.

```python
for system in cm.actuatingSystems:
    data.add(PidItem(tag=..., kind="final_element", fail_action=_fail_action(system)))

for pif in cm.processInstrumentationFunctions:      # each instrument bubble/loop
    for sgf in pif.processSignalGeneratingFunctions:  # its transmitters
        data.add(PidItem(tag=..., kind="transmitter", safety_class=..., voting=...))
    for af in pif.actuatingFunctions:                 # its valves
        data.add(PidItem(tag=..., kind="final_element", fail_action=...))
```

**What it does.** Walks the model the way you would read a loop sheet. For every
instrument loop it notes the transmitters (with SIL class and voting) and the valves (with
fail position FC / FO / FL). Equipment tags are collected too.

**Why you care.** These are exactly the facts the checks compare: *is this tag on the
drawing, is it safety related, and which way does the valve fail?*

```python
for entry in serializer.get_loading_errors().get_errors():
    if level in ("error", "critical"):
        data.warnings.append(...)
```

**What it does.** pyDEXPI keeps a log of elements it could not fully read. Serious entries
are copied into the report as "Reader warnings".

**Why you care.** If part of the P&ID was lost while loading, you see it in the report and
do not trust a result based on half a drawing.

---

## Step 2: Read the C&E matrix (`ce_reader.py`)

```python
CAUSE_COLUMNS = {
    "tag": ["Initiator tag", "Initiator", "Tag", "Instrument tag", "Cause tag"],
    "setpoint": ["Trip setpoint", "Setpoint", "Set point", "Trip value"],
    ...
}
```

**What it does.** Lists the heading names the reader accepts for each C&E column. The
reader searches the sheet for these headings instead of expecting fixed cells.

**Why you care.** Every contractor's C&E template looks a little different. If your
template uses a heading that is not listed (say "Trip Point"), add it to the list. That is
a one-word change.

```python
header_row = _find_header_row(ws)            # the row with 'Cause ID' and 'Initiator tag'
... label_col ...                            # the column with 'Final element tag' above it
for col in range(label_col + 1, ws.max_column + 1):   # each effect column
for r in range(header_row + 1, ws.max_row + 1):       # each cause row
```

**What it does.** Finds the heading row, then the effect labels above it (Final element
tag, Action on trip, Required safe position), then reads every effect column and every
cause row. Blank rows are skipped.

```python
ce.links[(cause.cause_id, eff.effect_id)] = eff.action if mark in _DEFAULT_MARKS else mark
```

**What it does.** Reads each intersection. An `X` means "this cause drives this effect
with the column's normal action". A word such as `OPEN` is kept as written.

**Why you care.** This is the matrix itself. Keeping the exact word written in a cell lets
check 3 catch a single cell that contradicts the rest of its column. A typo of that kind is
easy to miss by eye in a 12 × 9 grid.

---

## Step 3: Check 1, C&E tags missing from the P&ID (`checks.py`)

```python
for cause in ce.causes:
    if pid.get(cause.tag) is None:
        findings.append(Finding(check=CHECK_1, tags=[cause.tag], severity="HIGH", ...))
for eff in ce.effects:
    if pid.get(eff.tag) is None:
        ...
```

**What it does.** For every initiator and every final element in the C&E, it looks the
tag up on the P&ID. If it is not there, it writes a HIGH finding.

**Why you care.** It is a walk-down on paper. A trip on the C&E with no matching
instrument on the P&ID usually means one of three things: a typo, an MOC that updated one
document but not the other, or a trip that was never built. In the example, TZT-160 (TMT
high-high) and XV-176 (pilot gas second block valve) are found this way.

---

## Step 4: Check 2, trip transmitters missing from the C&E

```python
def is_trip_transmitter(item, settings):
    if item.kind != "transmitter":
        return False
    if settings.treat_safety_class_as_trip and item.safety_class:
        return True
    return any(re.search(p, item.tag) for p in settings.trip_transmitter_patterns)
```

**What it does.** Decides which P&ID transmitters are trip transmitters. There are two
ways to qualify. The P&ID gives the transmitter a safety class (e.g. SIL2), or its tag
matches a pattern. The default pattern is a first letter followed by `Z`, the ISA letter
for safety: `PZT`, `FZT`, `BZS`. Then it checks that each one has a C&E row.

**Why you care.** This is check 1 in the other direction: something installed as a safety
instrument that the C&E never uses. Either a trip is missing or the drawing is wrong. In
the example, FZT-101D (pass D) is caught by its tag, and PT-172 is caught only by its SIL2
marking, because its tag has no `Z`.

**Your tagging standard.** If your site tags trip transmitters differently (e.g. `PT-1234S`),
change `trip_transmitter_patterns` in `rules/rules.yaml`. These are *regular expressions*:
`^` means "starts with", `\d` means "a digit", `[A-Z]` means "any capital letter", and `*`
means "zero or more of the previous character".

---

## Step 5: Check 3, valve fail position vs trip action

```python
needed = settings.action_to_fail_position.get(action)   # CLOSE -> FC, OPEN -> FO
fail = item.fail_action                                  # from the P&ID
if fail is None:        -> LOW    (cannot verify)
elif fail == "FL":      -> MEDIUM (stays put on loss of air: not fail-safe)
elif fail != needed:    -> HIGH   (goes the wrong way on loss of air)
```

**What it does.** For every valve column, it collects the actions the causes ask for and
compares each one with the fail position drawn on the P&ID.

**Why you care.** Most trips work by *removing* air or power: the solenoid de-energises and
the spring drives the valve to its fail position. If the C&E says CLOSE but the valve is
fail-open, losing instrument air, which is often the very event that starts the upset,
drives the valve the wrong way. In the example:

- **XV-172**, the fuel gas vent between the two block valves (double block and bleed),
  must OPEN on trip but is drawn FC;
- **FV-110**, dilution steam, must stay OPEN to protect the coils but is drawn FC;
- **XV-100**, the ethane feed shutoff, is FL, so it closes only while the actuator still
  has energy;
- **TV-150** has one cell saying OPEN where its own column says the safe position is CLOSED.
  The tool flags that the C&E disagrees with itself and points at the cell, not the valve.

---

## Step 6: Latching and reset rules (`rules.py` and `rules/rules.yaml`)

This step is built so that **you write the rules**, not a programmer.

### How a rule is written

A rule in your site's safety philosophy reads like:

> "For every C&E row that closes a fuel gas shutoff valve, latching must be YES and reset
> must be MANUAL."

In `rules/rules.yaml` the same rule is:

```yaml
  - id: R-PH-01
    placeholder: true
    title: "Every trip of a fuel gas shutoff valve must be latched with manual reset"
    severity: HIGH
    when:                       # WHICH rows the rule looks at
      acts_on:
        tag_matches: "^XV-17\\d$"
        action: CLOSE
    require:                    # WHAT must be true for those rows
      latching: "YES"
      reset: MANUAL
    explanation: >-
      If the trip clears by itself ... (shown in the report)
    suggested_action: >-
      Set Latching = YES and Reset = MANUAL ... (shown in the report)
```

**What it does.** For each C&E row, the tool first asks whether the `when` part applies.
If it does, every line under `require` must hold. If one fails, the tool writes a finding
using your title, explanation, suggested action and severity. It also says exactly which
field failed, for example *"latching is 'NO' but must be 'YES'"*.

**Why you care.** Latching and reset philosophy varies between sites and licensors. Keeping
it in a plain file means you can maintain it the way you maintain a C&E: under MOC, with
revisions and without touching code.

### The keys of a rule

| Key | Needed? | Meaning |
|---|---|---|
| `id` | yes | short unique name, e.g. `R-SITE-04` |
| `title` | recommended | one sentence; starts the explanation in the report |
| `severity` | no (default MEDIUM) | `HIGH`, `MEDIUM`, `LOW` or `INFO` |
| `when` | no (default: all rows) | which C&E rows the rule looks at |
| `require` | yes | what must be true for those rows |
| `explanation` | recommended | why the rule exists |
| `suggested_action` | recommended | what to do when it is broken |
| `placeholder` | no | `true` marks it as an example in the report |
| `enabled` | no (default true) | `false` switches the rule off without deleting it |

### Fields you can test (in `when` and `require`)

These are the C&E columns: `cause_id`, `tag`, `description`, `setpoint`, `units`,
`trip_type`, `voting`, `sil`, `latching`, `reset`, `notes`.

In `when` only, `acts_on` selects rows by the effects they drive:
`tag_matches` (a pattern on the final element tag) and/or `action` (e.g. `CLOSE`).

### Tests you can use

| Written as | Means | Example |
|---|---|---|
| `field: VALUE` | equals (case ignored) | `reset: MANUAL` |
| `field: [A, B]` | one of | `reset: [MANUAL, MANUAL-FIELD]` |
| `field: {not: X}` | anything but X | `reset: {not: AUTO}` |
| `field: {not_one_of: [A, B]}` | none of these | `voting: {not_one_of: [1oo1]}` |
| `field: {matches: "pattern"}` | matches a pattern | `sil: {matches: "^SIL ?[1-4]$"}` |
| `field: {not_matches: "pattern"}` | does not match | `tag: {not_matches: "^HS-"}` |
| `field: {min: N}` | first number in the text is at least N | `sil: {min: 2}` (SIL2, SIL3) |
| `field: {max: N}` | first number is at most N | `sil: {max: 1}` |
| `field: {empty: true}` / `{empty: false}` | blank / filled in | `notes: {empty: false}` |

Several lines under `require` must **all** hold. Several lines under `when` must **all**
match for the rule to apply.

### Adding your own rule: step by step

1. Open `rules/rules.yaml` in a text editor (Notepad++, VS Code; not Word).
2. Scroll to the **TEMPLATE** at the bottom. Copy the block and paste it under the last rule.
3. Remove the `#` at the start of each line of your copy. Keep the indentation exactly:
   the `-` of each rule sits two spaces in from `rules:`.
4. Fill in `id`, `title`, `severity`, `when`, `require`, `explanation` and
   `suggested_action`. Set `placeholder: false`.
5. Run the checker. If the file has a mistake, the tool stops and names the rule and the
   field, for example *"Rule R-SITE-01 'require': unknown C&E field 'resett'"*.
6. Prove the rule works, like a trip test: change one cell in a **copy** of the C&E so that
   it breaks the rule, run again, and check that the finding appears.
7. When your own rules are in place, delete the placeholder rules or set
   `enabled: false` on them. The report stops printing "placeholder rules still in use".

### YAML traps to avoid

- **Tabs**: YAML refuses them. Use spaces.
- **YES / NO / ON / OFF** without quotes are read as true/false. The tool converts true/false
  back to YES/NO, but quoting them (`"YES"`) is clearer.
- **Special characters** (`: # [ ] { } ^ $ \`) need double quotes. Inside double quotes a
  backslash is written twice: `"^XV-17\\d$"`.

### When YAML is not enough

If a rule needs something the tests above cannot express (for example *"reset must be
MANUAL if the setpoint is above 800 °C"*, which compares a number with units), a
programmer adds one small function to the `OPERATORS` list in `rules.py`:

```python
OPERATORS = {
    "equals": lambda v, a: v.upper() == _word(a).upper(),
    ...
}
```

Each test takes the cell text `v` and the value from your rule `a` and answers True or
False. After it is added, the new test can be used in `rules.yaml` like any other.

---

## Step 7: The report (`report.py`)

```python
def number_findings(findings):
    ordered = sorted(findings, key=lambda f: (check number, severity, ...))
    for i, f in enumerate(ordered, start=1):
        f.finding_id = f"F-{i:03d}"
```

**What it does.** Sorts the findings by check and then by severity, and numbers them
F-001, F-002 and so on. It writes the same list three ways:

- **Excel** (`interlock_report.xlsx`): filterable, colour-coded by severity, with a summary
  sheet. Use it as an action tracker: add columns for owner, due date and MOC number;
- **Markdown** (`interlock_report.md`): plain text that displays nicely on GitHub;
- **HTML** (`interlock_report.html`): opens in any browser and prints well.

If the P&ID is a synthetic file, every report carries the "SYNTHETIC – FOR TRAINING ONLY"
banner.

**Why you care.** A finding needs an owner and a close-out, like a HAZOP action. Stable IDs
and a filterable sheet make that possible.

---

## Step 8: The command line (`cli.py`, `__main__.py`)

```python
findings = run_builtin_checks(pid, ce, ruleset.settings) + check_rules(ce, ruleset)
```

**What it does.** Ties the steps together: load rules → read P&ID → read C&E → run checks
1–3 → run the rules (check 4) → write the reports. `python -m interlock_checker ...` runs
this.

```python
    except (PidReadError, CeReadError, RulesError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
```

**Why you care.** The exit code tells an automated job what happened. `0` = report
written; `1` = findings at or above `--fail-on`; `2` = an input could not be read. With
`--fail-on HIGH`, a CI job can refuse a C&E revision that still has HIGH findings, like a
start permissive.

---

## Step 9: The synthetic example (`synthetic.py`)

```python
dict(cat="F", mod="IC", num="110", desc="Dilution steam flow control",
     transmitters=["FT-110"],
     # SEEDED: dilution steam valve drawn fail-close; the trip wants it OPEN.
     valves=[("FV-110", "FailClose" if seeded else "FailOpen")]),
```

**What it does.** Describes an invented ethane cracking furnace once, then writes it out
twice: as a DEXPI P&ID and as a C&E workbook. The trips follow the trainer in this
repository (`src/engine.js`); four typical furnace trips were added. Every deliberate
mistake is marked `SEEDED` and controlled by one switch. `seeded=False` gives a clean pair.

**Why you care.** A checker is only trustworthy if you have seen it catch known faults
*and* stay quiet on good data. It is the same idea as a proof test with a simulated input.
The README lists all 11 seeded mismatches.

Why hand-written XML? pyDEXPI 1.2 can *read* instrumentation from DEXPI files, but its
exporter only *writes* equipment and metadata. So the generator writes the XML in the same
structure as the DEXPI reference P&ID, and the checker reads it back through pyDEXPI like
any real export.

---

## Step 10: The tests (`tests/`)

```python
def test_seeded_example_finds_every_planted_mismatch(seeded_files):
    findings, ctx = cli.run(*seeded_files, RULES)
    got = {(f.check.split(".")[0], f.tags[0]) for f in findings}
    assert got == EXPECTED

def test_clean_example_has_zero_findings(clean_files):
    findings, _ = cli.run(*clean_files, RULES)
    assert findings == []
```

**What it does.** Each test sets up an input, runs part of the tool and checks the result.
This is a FAT for the software. There are 88 tests:

- `test_pid_reader.py`: reads the synthetic P&ID and the public DEXPI example; broken,
  non-DEXPI and empty files give clear errors;
- `test_ce_reader.py`: the C&E layout, alternative headings and every error message;
- `test_checks.py`: each check on a tiny clean case (zero findings), then with one fault
  added at a time;
- `test_rules.py`: every test operator and every rules-file mistake message;
- `test_end_to_end.py`: the full synthetic example. All 11 seeded mismatches are found, the
  clean variant gives zero, and the CLI exit codes and all three report formats work.

Run them with:

```bash
python -m pytest --cov --cov-report=term-missing
```

**Why you care.** When you or anyone else changes the code (a new heading alias, a new
rule test), the tests show straight away whether something that used to work is broken. It
is the regression test after an MOC.

---

## Step 11: Continuous integration (`.github/workflows/interlock-checker.yml`)

```yaml
on:
  pull_request:
    paths:
      - "interlock-checker/**"
```

**What it does.** On GitHub, every change to this folder automatically installs the tool,
downloads the public DEXPI example, runs all tests (failing if coverage drops below 80 %)
and runs the checker on the synthetic example.

**Why you care.** Nobody has to remember to run the tests. The workflow runs only for
changes in `interlock-checker/`, so the furnace trainer's own build is unaffected.
