> **SYNTHETIC – FOR TRAINING ONLY**

# Interlock consistency report

- P&ID: `examples/synthetic_furnace_pid.xml`
- C&E: `examples/synthetic_furnace_ce.xlsx`
- Rules: `rules/rules.yaml`
- Run: 2026-11-02 10:50

## Summary

**18 findings**: 14 HIGH, 4 MEDIUM, 0 LOW, 0 INFO

| Check | Findings |
|---|---|
| 1. C&E tag missing from P&ID | 2 |
| 2. Trip transmitter missing from C&E | 2 |
| 3. Valve fail position vs trip action | 4 |
| 4. Latching / reset rule D-01 | 1 |
| 4. Latching / reset rule D-02 | 1 |
| 4. Latching / reset rule D-03 | 2 |
| 4. Latching / reset rule D-04 | 1 |
| 4. Latching / reset rule D-05 | 1 |
| 4. Latching / reset rule D-06 | 1 |
| 4. Latching / reset rule D-07 | 1 |
| 4. Latching / reset rule D-08 | 1 |
| 4. Latching / reset rule D-09 | 1 |

**DRAFT rules awaiting engineer approval:** D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09. Findings from these rules are proposals until the rules are approved.

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
| F-009 | 4. Latching / reset rule D-01 [DRAFT – pending engineer approval] | PZT-141 | HIGH | Every SIF trip must latch. Cause C07 (Firebox pressure high-high): latching is 'NO' but must be 'YES'. A trip that un-trips by itself when the reading recovers can restart the furnace half-way through an upset, before anyone has found the cause (common IEC 61511 practice). | Set Latching = YES, or record why this SIF may be non-latching. |
| F-010 | 4. Latching / reset rule D-02 [DRAFT – pending engineer approval] | FZT-110 | HIGH | No automatic reset on any SIF. Cause C04 (Steam/ethane ratio low-low): reset is 'AUTO' but must be 'MANUAL'. An operator must confirm the plant is safe before a safety function is re-armed; an AUTO reset skips that check. | Change Reset to MANUAL. |
| F-011 | 4. Latching / reset rule D-03 [DRAFT – pending engineer approval] | FZT-110 | HIGH | No automatic reset on any fuel gas or ethane feed shutoff, SIF or not. Cause C04 (Steam/ethane ratio low-low): reset is 'AUTO' but must be 'MANUAL'. It acts on XV-100. Reopening fuel or feed by itself onto a hot firebox or hot coils is how furnace explosions and coil damage happen, even when the trip is not SIL-rated. | Change Reset to MANUAL for every cause that closes a feed or fuel shutoff. |
| F-012 | 4. Latching / reset rule D-03 [DRAFT – pending engineer approval] | HS-199 | HIGH | No automatic reset on any fuel gas or ethane feed shutoff, SIF or not. Cause C12 (Emergency shutdown push button): reset is 'AUTO' but must be 'MANUAL'. It acts on XV-100, XV-170, XV-171, XV-175, XV-176. Reopening fuel or feed by itself onto a hot firebox or hot coils is how furnace explosions and coil damage happen, even when the trip is not SIL-rated. | Change Reset to MANUAL for every cause that closes a feed or fuel shutoff. |
| F-013 | 4. Latching / reset rule D-04 [DRAFT – pending engineer approval] | TZT-150 | HIGH | Reset is blocked while the initiating cause is still active. Cause C05 (Coil outlet temperature high-high): reset permissive is '2OO3 HEALTHY' but must contain 'CAUSE CLEAR'. If reset is accepted while, say, the COT is still above its trip point, the furnace re-trips at best, or restarts into the hazard at worst. | Add CAUSE CLEAR to the reset permissives for this cause. |
| F-014 | 4. Latching / reset rule D-05 [DRAFT – pending engineer approval] | AZT-140 | HIGH | SIF reset is done at field or console as specified, never by a DCS auto-sequence. Cause C06 (Arch O2 low-low): reset location is 'DCS-AUTO' but must be one of ['FIELD', 'CONSOLE', 'FIELD+CONSOLE']. A DCS sequence that resets the SIS takes the deliberate human step out of the loop and lets the basic control system defeat the safety system. | Set Reset location to FIELD, CONSOLE or FIELD+CONSOLE as the SRS specifies. |
| F-015 | 4. Latching / reset rule D-06 [DRAFT – pending engineer approval] | PZT-170 | HIGH | Any fuel trip needs a purge-complete permissive before relight. Cause C09 (Fuel gas pressure low-low): reset permissive is 'CAUSE CLEAR; 2OO3 HEALTHY' but must contain 'PURGE COMPLETE'. It acts on XV-170, XV-171. After a fuel trip, unburnt gas can sit in the firebox. Relighting without a timed purge is the classic cause of firebox explosions (burner-management practice, e.g. NFPA 86 / EN 746-2). | Add PURGE COMPLETE to the reset permissives for this cause. |
| F-016 | 4. Latching / reset rule D-07 [DRAFT – pending engineer approval] | LZT-130 | MEDIUM | A 2oo3 trip resets only when at least 2 of 3 transmitters are healthy. Cause C08 (Steam drum level low-low): reset permissive is 'CAUSE CLEAR' but must contain '2OO3 HEALTHY'. With two transmitters faulty, the vote can no longer see a real demand; resetting then re-arms a trip that cannot act. | Add 2OO3 HEALTHY to the reset permissives, or document degraded-mode voting. |
| F-017 | 4. Latching / reset rule D-08 [DRAFT – pending engineer approval] | FZT-101B | MEDIUM | Bypassed or overridden initiators are flagged for review. Cause C02 (Pass B flow low-low): bypass is 'BYPASSED – MOS-0423 (synthetic)' but must be one of ['NONE']. While an initiator is bypassed, its trip is not protecting the furnace. Every bypass needs a permit, compensating measures and an end date, and should be visible. | Confirm the bypass permit, its compensating measures and expiry; remove the bypass when done. |
| F-018 | 4. Latching / reset rule D-09 [DRAFT – pending engineer approval] | BZS-171 | MEDIUM | SIL 2 and higher trips must not rely on a single sensor (1oo1). Cause C10 (Flame failure): voting is '1oo1' but must not be '1oo1'. A single sensor gives no redundancy. Whether 1oo1 is acceptable depends on the SIL verification, so this rule asks for a second look rather than declaring it wrong. | Check the SIL verification; add redundancy (1oo2, 2oo3) if it is needed. |
