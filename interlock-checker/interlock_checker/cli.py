"""Step 8: the command line that ties the steps together.

    python -m interlock_checker --pid P&ID.xml --ce C&E.xlsx --rules rules.yaml --out report_folder
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .ce_reader import CeReadError, read_ce
from .checks import run_builtin_checks
from .models import SEVERITIES, Finding
from .pid_reader import PidReadError, read_pid
from .report import ReportContext, number_findings, write_reports
from .rules import RulesError, check_rules, load_rules
from .synthetic import SYNTHETIC_LABEL


def run(pid_path, ce_path, rules_path=None, sheet=None) -> tuple[list[Finding], ReportContext]:
    """Read the inputs, run all four checks and return numbered findings plus report facts."""
    ruleset = load_rules(rules_path)
    pid = read_pid(pid_path)
    ce = read_ce(ce_path, sheet=sheet)
    findings = run_builtin_checks(pid, ce, ruleset.settings) + check_rules(ce, ruleset)
    synthetic = "SYNTHETIC" in Path(pid_path).read_text(encoding="utf-8", errors="ignore")[:4000]
    ctx = ReportContext(
        pid_source=str(pid_path), ce_source=str(ce_path), rules_source=str(rules_path or ""),
        banner=SYNTHETIC_LABEL if synthetic else "",
        placeholder_rules=[r.rule_id for r in ruleset.placeholders],
        warnings=list(pid.warnings),
    )
    return number_findings(findings), ctx


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m interlock_checker",
        description="Compare a DEXPI P&ID with a cause-and-effect matrix and report mismatches.",
    )
    parser.add_argument("--pid", required=True, help="P&ID as DEXPI Proteus XML (.xml)")
    parser.add_argument("--ce", required=True, help="cause-and-effect matrix (.xlsx)")
    parser.add_argument("--rules", help="settings and latching/reset rules (.yaml or .json)")
    parser.add_argument("--out", default="output", help="folder for the reports (default: output)")
    parser.add_argument("--sheet", help="C&E sheet name (default: first sheet with a 'Cause ID' heading)")
    parser.add_argument("--fail-on", choices=SEVERITIES,
                        help="exit with code 1 if any finding is this severe or worse (useful in CI)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    try:
        findings, ctx = run(args.pid, args.ce, args.rules, args.sheet)
    except (PidReadError, CeReadError, RulesError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for path in write_reports(findings, ctx, args.out):
        print(f"wrote {path}")
    counts = {s: sum(f.severity == s for f in findings) for s in SEVERITIES}
    print(f"{len(findings)} findings: " + ", ".join(f"{n} {s}" for s, n in counts.items()))
    for w in ctx.warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    if ctx.placeholder_rules:
        print(f"NOTE: placeholder rules still in use: {', '.join(ctx.placeholder_rules)}")

    if args.fail_on:
        worst = SEVERITIES[: SEVERITIES.index(args.fail_on) + 1]
        if any(f.severity in worst for f in findings):
            return 1
    return 0
