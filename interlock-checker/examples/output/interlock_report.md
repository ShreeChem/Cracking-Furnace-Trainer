> **SYNTHETIC – FOR TRAINING ONLY**

# Interlock consistency report

- P&ID: `examples/synthetic_furnace_pid.xml`
- C&E: `examples/synthetic_furnace_ce.xlsx`
- Rules: `rules/rules.yaml`
- Run: 2026-10-29 11:09

## Summary

**11 findings**: 9 HIGH, 2 MEDIUM, 0 LOW, 0 INFO

| Check | Findings |
|---|---|
| 1. C&E tag missing from P&ID | 2 |
| 2. Trip transmitter missing from C&E | 2 |
| 3. Valve fail position vs trip action | 4 |
| 4. Latching / reset rule R-PH-01 | 1 |
| 4. Latching / reset rule R-PH-02 | 1 |
| 4. Latching / reset rule R-PH-03 | 1 |

**Placeholder rules still in use:** R-PH-01, R-PH-02, R-PH-03. Replace them with your site's latching and reset rules.

## Findings

| Finding ID | Check | Tag(s) | Severity | Explanation | Suggested action |
|---|---|---|---|---|---|
| F-001 | 1. C&E tag missing from P&ID | TZT-160 | HIGH | Cause C11 (Tube metal temperature high-high) uses initiator TZT-160, but no instrument with that tag is on the P&ID. The trip may exist only on paper: like a trip test sheet for a transmitter nobody can find in the field. | Check whether the tag is mistyped in the C&E or missing from the P&ID. If the instrument was added later (e.g. after a HAZOP), make sure the MOC updates the P&ID. |
| F-002 | 1. C&E tag missing from P&ID | XV-176 | HIGH | Effect E09 (Pilot gas second shutoff valve) acts on final element XV-176, but that tag is not on the P&ID. Nobody can confirm the valve or motor exists, or what its fail position is. | Confirm the final element exists and add it to the P&ID with its fail position, or correct the tag in the C&E. |
| F-003 | 2. Trip transmitter missing from C&E | FZT-101D | HIGH | FZT-101D (Pass D flow, low-low trip) looks like a trip transmitter because it is marked SIL1 on the P&ID and its tag follows the trip transmitter naming pattern, but no C&E row uses it. Either a trip is missing from the C&E, or the instrument is wrongly marked as safety related. | Ask the SIS engineer whether this transmitter should initiate a trip. If yes, add the cause row (setpoint, voting, latching, reset) to the C&E; if no, correct the P&ID. |
| F-004 | 2. Trip transmitter missing from C&E | PT-172 | HIGH | PT-172 (Fuel gas pressure, high-high trip) looks like a trip transmitter because it is marked SIL2 on the P&ID, but no C&E row uses it. Either a trip is missing from the C&E, or the instrument is wrongly marked as safety related. | Ask the SIS engineer whether this transmitter should initiate a trip. If yes, add the cause row (setpoint, voting, latching, reset) to the C&E; if no, correct the P&ID. |
| F-005 | 3. Valve fail position vs trip action | FV-110 | HIGH | The C&E asks FV-110 to OPEN on trip (all 12 causes), but the P&ID shows it fail-close (FC). On loss of instrument air or power the valve goes the opposite way to the safe state the trip needs. | Find out which document is right. Correct the C&E action, or change the actuator to fail-open (FO) through MOC, then repeat the trip test. |
| F-006 | 3. Valve fail position vs trip action | TV-150 | HIGH | The C&E asks TV-150 to OPEN on trip (cause C05), but the P&ID shows it fail-close (FC). On loss of instrument air or power the valve goes the opposite way to the safe state the trip needs. The C&E column itself says the required safe position is CLOSED, so the 'OPEN' entry may be the error. | The C&E disagrees with itself. Check the 'OPEN' entry for cause C05 against the required safe position (CLOSED) with the SIS engineer and correct it. |
| F-007 | 3. Valve fail position vs trip action | XV-172 | HIGH | The C&E asks XV-172 to OPEN on trip (causes C06, C07, C09, C10, C11, C12), but the P&ID shows it fail-close (FC). On loss of instrument air or power the valve goes the opposite way to the safe state the trip needs. | Find out which document is right. Correct the C&E action, or change the actuator to fail-open (FO) through MOC, then repeat the trip test. |
| F-008 | 3. Valve fail position vs trip action | XV-100 | MEDIUM | The C&E asks XV-100 to CLOSE (all 12 causes), but the P&ID shows it fail-last (FL). On loss of air or power the valve stays where it is, so the trip only works while the actuator still has energy: it is not fail-safe. | Confirm the design intent. Either change the actuator to fail-close (FC), or document how the trip is guaranteed (e.g. accumulator, UPS) in the SRS. |
| F-009 | 4. Latching / reset rule R-PH-01 [PLACEHOLDER RULE – replace with your own] | PZT-141 | HIGH | Every trip of a fuel gas shutoff valve must be latched with manual reset. Cause C07 (Firebox pressure high-high): latching is 'NO' but must be 'YES'. It acts on XV-170, XV-171. If the trip clears by itself when the reading recovers, the fuel valves could reopen onto a hot firebox without an operator checking it is safe to relight. | Set Latching = YES and Reset = MANUAL for this cause, or record the approved exception. |
| F-010 | 4. Latching / reset rule R-PH-02 [PLACEHOLDER RULE – replace with your own] | FZT-110 | HIGH | No auto-reset on any safety instrumented function (SIF). Cause C04 (Steam/ethane ratio low-low): reset is 'AUTO' but must not be 'AUTO'. An automatic reset lets the plant restart without anyone confirming why it tripped. | Change the reset to MANUAL, or remove the SIL rating if this is not a SIF. |
| F-011 | 4. Latching / reset rule R-PH-03 [PLACEHOLDER RULE – replace with your own] | BZS-171 | MEDIUM | SIL 2 and higher trips must not use 1oo1 voting. Cause C10 (Flame failure): voting is '1oo1' but must not be '1oo1'. A single sensor gives no redundancy. Whether 1oo1 is acceptable depends on the SIL verification, so this rule only asks for a second look. | Check the SIL verification for this SIF; add redundancy (1oo2, 2oo3) if it is needed. |
