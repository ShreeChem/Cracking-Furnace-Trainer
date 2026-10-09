/* ProcessGuard cracking furnace trainer: simulation, scenarios and scoring.
   Simplified dynamic model on synthetic, illustrative values. Not a certified training model. */
(function (root) {
  'use strict';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lag = (y, u, tau, dt) => y + (u - y) * (1 - Math.exp(-dt / tau));

  // ---------- design point (synthetic) ----------
  const D = {
    F0: 32, R0: 0.32, XO: 640, COT0: 850, LHV0: 47, FUEL0: 6.4,
    DAMP0: 60, DSCAP0: 14, LVL0: 52, TMT0: 1015
  };
  D.TOT0 = D.F0 * (1 + D.R0);
  D.E0 = D.FUEL0 * D.LHV0;

  // ---------- limits ----------
  const LIM = {
    dsLow: 9.2, ratioLow: 0.25, ratioLL: 0.20, cotHigh: 865, cotLow: 830, cotHH: 880, tmtHigh: 1045,
    passLow: 0.85, passLL: 0.62, o2Low: 1.5, o2LL: 0.5, coHigh: 300, drfHigh: -1.0, drfHH: 2.0,
    lvlLow: 35, lvlLL: 20
  };

  // ---------- physics core: radiant coil (one lumped coil per pass) ----------
  // Plug flow along the coil, uniform heat flux, three molecular reactions of the
  // Sundaram & Froment (1977) ethane scheme with their published A and E:
  //   R1  C2H6 <=> C2H4 + H2          A 4.65e13 1/s     E 65 210 cal/mol
  //   R2  2 C2H6 -> C3H8 + CH4        A 3.85e11 L/mol/s E 65 250 cal/mol
  //   R3  C2H4 + C2H6 -> C3H6 + CH4   A 7.08e13 L/mol/s E 60 430 cal/mol
  // Heats of reaction and heat capacities are constant approximations; R1 equilibrium uses
  // an approximate Kp(T). Coil volume and design heat duty are calibrated once so that the
  // design point gives COT 850 °C at 65 % ethane conversion (typical published range).
  const RG = 8.314, CAL = 4.184, PB = 2.4e5;               // gas constant, cal->J, mean coil pressure (Pa)
  const MW = { e: 30.07, y: 28.05, h: 2.016, m: 16.04, p: 44.1, r: 42.08, w: 18.02 }; // g/mol
  const CP = { e: 122, y: 94, h: 30.2, m: 72, p: 174, r: 150, w: 41.3 };              // J/mol/K near 1000 K
  const RX = [
    { A: 4.65e13, E: 65210 * CAL, dH: 144e3 },
    { A: 3.85e11 * 1e-3, E: 65250 * CAL, dH: -11.6e3 },
    { A: 7.08e13 * 1e-3, E: 60430 * CAL, dH: -22.9e3 }
  ];
  const NCELL = 40, TXO = 640;                               // cells per coil, crossover (coil inlet) temperature °C
  function solveCoil(nE, nW, Q, V){
    // nE, nW: ethane and steam mol/s into the coil; Q: absorbed heat W; V: coil volume m3
    const n = { e: nE, y: 0, h: 0, m: 0, p: 0, r: 0, w: nW };
    let T = TXO + 273.15;
    if (nE + nW < 1e-3) return { cot: TXO + Q / 2000, X: 0, y: 0, n };
    const dV = V / NCELL, dQ = Q / NCELL;
    for (let c = 0; c < NCELL; c++) {
      for (let sub = 0; sub < 3; sub++) {
        const nt = n.e + n.y + n.h + n.m + n.p + n.r + n.w;
        const Cf = PB / (RG * T) / nt;                       // mol/m3 per (mol/s) of a species
        const k1 = RX[0].A * Math.exp(-RX[0].E / (RG * T)), k2 = RX[1].A * Math.exp(-RX[1].E / (RG * T)), k3 = RX[2].A * Math.exp(-RX[2].E / (RG * T));
        const Kp = Math.exp(-(144e3 - T * 136) / (RG * T)) * 1e5, Kc = Kp / (RG * T);
        const Ce = n.e * Cf, Cy = n.y * Cf, Ch = n.h * Cf;
        const tau = dV / 3 / (nt * RG * T / PB);             // residence time in this sub-cell (s) x volumetric flow
        const vol = dV / 3;
        let x1 = Math.max(-0.5 * n.y, k1 * (Ce - Cy * Ch / Kc) * vol), x2 = k2 * Ce * Ce * vol, x3 = k3 * Ce * Cy * vol;
        const use = x1 + 2 * x2 + x3; if (use > 0.5 * n.e) { const f = 0.5 * n.e / use; x1 *= f; x2 *= f; x3 *= f; }
        n.e -= x1 + 2 * x2 + x3; n.y += x1 - x3; n.h += x1; n.p += x2; n.m += x2 + x3; n.r += x3;
        const cpTot = n.e * CP.e + n.y * CP.y + n.h * CP.h + n.m * CP.m + n.p * CP.p + n.r * CP.r + n.w * CP.w;
        T += (dQ / 3 - x1 * RX[0].dH - x2 * RX[1].dH - x3 * RX[2].dH) / cpTot;
        void tau;
      }
    }
    return { cot: T - 273.15, X: nE > 0 ? 1 - n.e / nE : 0, y: n.y, n };
  }
  // per-pass design flows (mol/s)
  const nE0 = D.F0 * 1e6 / 3600 / 4 / MW.e, nW0 = D.F0 * D.R0 * 1e6 / 3600 / 4 / MW.w;
  function calibrate(){
    const qFor = V => { let lo = 1e6, hi = 4e7; for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (solveCoil(nE0, nW0, m, V).cot < D.COT0) lo = m; else hi = m; } return (lo + hi) / 2; };
    let lo = 0.05, hi = 20;
    for (let i = 0; i < 40; i++) { const V = Math.sqrt(lo * hi); const X = solveCoil(nE0, nW0, qFor(V), V).X; if (X < 0.65) lo = V; else hi = V; }
    const V = Math.sqrt(lo * hi), Q = qFor(V), r = solveCoil(nE0, nW0, Q, V);
    return { V, Q, X: r.X, Y0: r.y };
  }
  const CAL0 = calibrate();
  D.VPASS = CAL0.V; D.QPASS = CAL0.Q; D.YIELD0 = CAL0.Y0 * 4 * MW.y * 3.6e-3;   // design ethylene t/h
  D.EFF = 4 * D.QPASS / (D.FUEL0 * D.LHV0 / 3.6 * 1e6);    // radiant efficiency implied by the design point
  D.DTF = D.TMT0 - D.COT0;                                   // tube wall minus process at design (film + metal)

  // ---------- alarm definitions ----------
  const ALARMS = [
    { id: 'ds_hdr', pri: 'INFO', text: 'DS HEADER PRESSURE LOW', on: s => s.ev.dsHdr },
    { id: 'ds_low', pri: 'MED', tag: 'FIC-110', text: 'FIC-110 DILUTION STEAM LOW FLOW', on: s => s.ds < LIM.dsLow && s.feed > 1 },
    { id: 'ratio_low', pri: 'HIGH', tag: 'FIC-110', text: 'STEAM / ETHANE RATIO LOW', on: s => s.ratio < LIM.ratioLow && s.feed > 1 },
    { id: 'pass_low', pri: 'MED', tag: 'FIC-101C', text: 'FIC-101C PASS C LOW FLOW', on: s => Math.min(...s.pf) < LIM.passLow },
    { id: 'cot_high', pri: 'MED', tag: 'TIC-150', text: 'PASS COIL OUTLET TEMP HIGH', on: s => Math.max(...s.cotM) > LIM.cotHigh },
    { id: 'cot_low', pri: 'MED', tag: 'TIC-150', text: 'PASS COIL OUTLET TEMP LOW', on: s => Math.min(...s.cotM) < LIM.cotLow && s.feed > 1 },
    { id: 'tmt_high', pri: 'HIGH', tag: 'TI-160', text: 'TUBE METAL TEMPERATURE HIGH', on: s => Math.max(...s.tmt) > LIM.tmtHigh },
    { id: 'o2_low', pri: 'HIGH', tag: 'AIC-140', text: 'ARCH O₂ LOW', on: s => s.o2 < LIM.o2Low },
    { id: 'co_high', pri: 'MED', tag: 'AIC-140', text: 'FLUE GAS CO HIGH', on: s => s.co > LIM.coHigh },
    { id: 'fg_hv', pri: 'INFO', text: 'FUEL GAS DENSITY HIGH', on: s => s.lhv > 50 },
    { id: 'fan_trip', pri: 'HIGH', tag: 'K-101', text: 'ID FAN K-101 TRIPPED', on: s => !s.fanRun },
    { id: 'drf_high', pri: 'HIGH', tag: 'AIC-140', text: 'FIREBOX PRESSURE HIGH', on: s => s.draft > LIM.drfHigh },
    { id: 'pump_trip', pri: 'HIGH', tag: 'P-131A', text: 'BFW PUMP P-131A TRIPPED', on: s => s.ev.pumpA === false },
    { id: 'lvl_low', pri: 'HIGH', tag: 'LIC-130', text: 'STEAM DRUM LEVEL LOW', on: s => s.lvl < LIM.lvlLow }
  ];

  const TRIPS = [
    // kind 'process': partial trip (feed cut, firing reduced, dilution steam kept on the coils)
    // kind 'combustion': full fuel trip. Real trip actions depend on the furnace design.
    { id: 'ratio', kind: 'process', text: 'S/HC LOW-LOW · FEED CUT', val: s => s.ratio, lim: LIM.ratioLL, dir: -1, hold: 3, fmt: v => v.toFixed(2) },
    { id: 'pass', kind: 'process', text: 'PASS FLOW LOW-LOW', val: s => Math.min(...s.pf) * 100, lim: LIM.passLL * 100, dir: -1, hold: 3, fmt: v => v.toFixed(0) + ' %' },
    { id: 'cot', kind: 'process', text: 'COT HIGH-HIGH (SIS)', val: s => Math.max(...s.cot), lim: LIM.cotHH, dir: 1, hold: 60, fmt: v => v.toFixed(0) },
    { id: 'o2', kind: 'combustion', text: 'ARCH O₂ LOW-LOW', val: s => s.o2, lim: LIM.o2LL, dir: -1, hold: 10, fmt: v => v.toFixed(1) },
    { id: 'drf', kind: 'combustion', text: 'FIREBOX PRESS HIGH-HIGH', val: s => s.draft, lim: LIM.drfHH, dir: 1, hold: 5, fmt: v => v.toFixed(1) },
    { id: 'lvl', kind: 'process', text: 'DRUM LEVEL LOW-LOW', val: s => s.lvl, lim: LIM.lvlLL, dir: -1, hold: 3, fmt: v => v.toFixed(0) + ' %' }
  ];

  // ---------- state ----------
  function initState(scn) {
    const s = {
      t: 0, feedSP: D.F0, feed: D.F0, ratioSP: D.R0, ds: D.F0 * D.R0, dsCap: D.DSCAP0, ratio: D.R0,
      pf: [1, 1, 1, 1], stuck: null, fieldEta: null,
      ticMode: 'AUTO', cotSP: D.COT0, fuel: D.FUEL0, fuelOP: 100, ticI: 0, ticBias: 0, aicBias: 0, fanStartAt: null, lhv: D.LHV0,
      qAbs: D.QPASS * 4, X: [0.65, 0.65, 0.65, 0.65], yld: D.YIELD0, cot: [850, 850, 850, 850], cotM: [850, 850, 850, 850], avgIn: [true, true, true, true], tcFail: null, mode: 'CRACKING', tmt: [1015, 1015, 1015, 1015],
      aicMode: 'AUTO', o2SP: 2.0, damper: D.DAMP0, aicI: 0, o2: 2.07, o2True: 2.07, co: 25,
      fanRun: true, fanSpeed: 1, fanAvail: null, draft: -4.8,
      lvl: D.LVL0, lvlM: D.LVL0, stAvg: 1, lvlSP: 52, bfwCap: 1.6, bfw: 1.0, steam: 1.0, licI: 0, pumpB: false, pumpBEta: null,
      tleOut: 395, drumP: 118,
      ev: { dsHdr: false, pumpA: true },
      coke: 0, ethylene: 0, base: 0, tripped: null, tripHold: {}, done: false
    };
    if (scn && scn.init) scn.init(s);
    return s;
  }

  // controller PV: average of the pass thermocouples selected into TIC-150
  function cotPV(s) {
    let n = 0, sum = 0;
    for (let i = 0; i < 4; i++) if (s.avgIn[i]) { sum += s.cotM[i]; n++; }
    return n ? sum / n : s.cotM.reduce((a, b) => a + b, 0) / 4;
  }

  function step(s, dt, scn) {
    if (s.tripped || s.done) return;
    s.t += dt;
    if (scn && scn.event) scn.event(s, s.t);

    // feed and dilution steam
    s.feed = lag(s.feed, clamp(s.feedSP, 0, 40), 8, dt);
    const dsSP = s.ratioSP * s.feed;
    s.ds = lag(s.ds, Math.min(dsSP, s.dsCap), 6, dt);
    s.ratio = s.feed > 0.5 ? s.ds / s.feed : D.R0;
    const tot = s.feed + s.ds;

    // pass flow distribution
    let fC = 1;
    if (s.stuck) {
      if (s.fieldEta != null && s.t >= s.fieldEta) s.stuck.target = 1.0;
      s.stuck.f = lag(s.stuck.f, s.stuck.target, s.stuck.target >= 1 ? 6 : 1e9, dt);
      if (s.stuck.target < 1) s.stuck.f = Math.max(0.55, s.stuck.f - s.stuck.drift * dt);
      fC = s.stuck.f;
      if (s.stuck.target >= 1 && s.stuck.f > 0.995) { s.stuck = null; fC = 1; }
    }
    const fO = (4 - fC) / 3;
    s.pf = [fO, fO, fC, fO];

    // combustion air, O2, draft
    const E = s.fuel * s.lhv;
    const air = (s.fanRun ? s.fanSpeed : 0) * (s.damper / D.DAMP0) + (1 - (s.fanRun ? s.fanSpeed : 0)) * 0.75 * Math.sqrt(s.damper / D.DAMP0);
    const ex = air * 1.11 * D.E0 / Math.max(E, 1) - 1;
    s.o2True = ex > 0 ? 20.9 * ex / (1 + ex) * 0.9 : 0;
    s.o2 = lag(s.o2, s.o2True, 12, dt);
    s.co = lag(s.co, 25 + Math.max(0, 1.2 - s.o2True) * 900, 8, dt);
    const fan = s.fanRun ? s.fanSpeed : 0;
    const drfSS = -8.3 * fan * Math.sqrt(s.damper / D.DAMP0) - 4.55 * (s.damper / 100) + 6.23 * (E / D.E0);
    s.draft = lag(s.draft, drfSS, 15, dt);

    // fired duty -> heat absorbed by the coils (firebox and tube inertia lag); incomplete combustion releases less heat
    const burnFrac = ex >= 0 ? 1 : clamp(1 + ex * 1.5, 0.5, 1);
    const qTarget = D.EFF * s.fuel * s.lhv / 3.6 * 1e6 * burnFrac;
    s.qAbs = lag(s.qAbs, qTarget, 30, dt);
    // each pass: same heat, its own flow -> coil model gives COT, conversion and ethylene
    let yld = 0;
    for (let i = 0; i < 4; i++) {
      const share = s.pf[i] / 4;
      const nE = s.feed * 1e6 / 3600 * share / MW.e, nW = s.ds * 1e6 / 3600 * share / MW.w;
      const r = solveCoil(nE, nW, s.qAbs / 4, D.VPASS);
      s.cot[i] = lag(s.cot[i], Math.min(r.cot, 1000), 4, dt);
      s.X[i] = r.X; yld += r.y * MW.y * 3.6e-3;
      // tube wall = process + film/metal drop, scaled with heat flux and mass velocity (h ~ G^0.8), plus coke layer
      const g = Math.max(0.05, (nE * MW.e + nW * MW.w) / (nE0 * MW.e + nW0 * MW.w));
      s.tmt[i] = lag(s.tmt[i], s.cot[i] + D.DTF * (s.qAbs / 4 / D.QPASS) / Math.pow(g, 0.8) + s.coke * 0.6, 20, dt);
    }
    s.yld = yld;
    const cotAvg = s.cot.reduce((a, b) => a + b, 0) / 4;   // true average (process side)
    // DCS thermocouples TI-151A..D: what the operator and TIC-150 see
    for (let i = 0; i < 4; i++) s.cotM[i] = s.cot[i] + (s.tcFail && s.tcFail.i === i ? s.tcFail.off : 0);

    // COT controller TIC-150 → fuel, on the average of the passes selected into it
    if (s.ticMode === 'AUTO') {
      const e = s.cotSP - cotPV(s);
      s.ticI = clamp(s.ticI + e * dt / 120, -100, 100);
      s.fuelOP = clamp(100 + 1.0 * (e + s.ticI) * 1.0 + s.ticBias, 10, 140);
    }
    s.fuel = lag(s.fuel, D.FUEL0 * s.fuelOP / 100, 4, dt);

    // O2 controller AIC-140 → damper
    if (s.aicMode === 'AUTO') {
      const e = s.o2SP - s.o2;
      s.aicI = clamp(s.aicI + e * dt / 30, -40, 40);
      s.damper = clamp(D.DAMP0 + 6 * (e + s.aicI) + s.aicBias, 20, 100);
    }

    // ID fan restart
    if (!s.fanRun && s.fanStartAt != null && s.t >= s.fanStartAt) { s.fanRun = true; s.fanSpeed = 0.2; s.fanStartAt = null; }
    if (s.fanRun && s.fanSpeed < 1) s.fanSpeed = Math.min(1, s.fanSpeed + dt / 10);

    // steam drum
    if (s.pumpBEta != null && s.t >= s.pumpBEta) { s.pumpB = true; s.pumpBEta = null; }
    s.bfwCap = (s.ev.pumpA ? 1.3 : 0.3) + (s.pumpB ? 1.3 : 0);
    // TLE steam generation follows the heat removed from the cracked gas (cooled to about 395 °C)
    s.steam = ((s.feed + s.ds) / D.TOT0) * Math.max(0, cotAvg - 395) / (D.COT0 - 395);
    const le = s.lvlSP - s.lvl;
    s.licI = clamp(s.licI + le * dt / 40, -20, 20);
    s.bfw = clamp(s.steam + 0.04 * (le + s.licI), 0, s.bfwCap);
    s.lvlM = clamp(s.lvlM + (s.bfw - s.steam) * 0.305 * dt, 0, 100);
    // shrink and swell: a step up in steaming swells the apparent level, a step down shrinks it
    s.stAvg = lag(s.stAvg, s.steam, 40, dt);
    s.lvl = clamp(s.lvlM + 6 * (s.steam - s.stAvg), 0, 100);
    s.tleOut = lag(s.tleOut, 395 + (s.lvl < 25 ? (25 - s.lvl) * 6 : 0) + (cotAvg - 850) * 0.3, 15, dt);

    // coking and production
    s.coke += (Math.max(0, 0.28 - s.ratio) * 2 + Math.max(0, Math.max(...s.tmt) - 1045) * 0.01) * dt;
    s.ethylene += s.yld * dt / 3600;
    s.base += D.YIELD0 * dt / 3600;

    // safety instrumented trips
    for (const tr of TRIPS) {
      const v = tr.val(s);
      const bad = tr.dir < 0 ? v < tr.lim : v > tr.lim;
      if (tr.id === 'ratio' && s.feed < 1) continue;
      s.tripHold[tr.id] = bad ? (s.tripHold[tr.id] || 0) + dt : 0;
      if (s.tripHold[tr.id] >= tr.hold) {
        s.tripped = { id: tr.id, kind: tr.kind, text: tr.text, t: s.t };
        s.feedSP = 0; s.feed = 0;
        if (tr.kind === 'combustion') { s.fuelOP = 0; s.fuel = 0; s.mode = 'FUEL TRIP'; }
        else { s.fuelOP = 25; s.fuel = D.FUEL0 * 0.25; s.mode = 'PARTIAL TRIP · STEAM ON'; }
        return;
      }
    }
    if (scn && s.t >= scn.dur) s.done = true;
  }

  // ---------- scenarios ----------
  const SCN = {
    s1: {
      id: 's1', n: '01', name: 'Dilution steam loss', dur: 480, diff: 2, key: 'ratio',
      teaser: 'Steam-to-ethane ratio falls. Coking starts and the ratio trip gets close.',
      state: 'Normal operation at 32 t/h ethane. All loops in AUTO. FIC-110 runs in ratio control at 0.32.',
      cause: 'Dilution steam header pressure drops (upstream boiler problem). FIC-110 runs out of valve capacity; utilities restore the header later.',
      objectives: ['Keep steam/ethane ratio above the trip (0.20)', 'Limit coking: keep the ratio at or above 0.25', 'Avoid an unplanned furnace trip'],
      init(s) {},
      event(s, t) {
        if (t >= 20 && t < 330) { s.ev.dsHdr = true; s.dsCap = Math.max(6.2, D.DSCAP0 - (t - 20) * 0.039); }
        else if (t >= 330) { s.ev.dsHdr = t < 390; s.dsCap = Math.min(D.DSCAP0, 6.2 + (t - 330) * 0.13); }
      },
      steps: [
        { id: 'ack', text: 'Acknowledge the alarms and check the DS header pressure', target: 60, eval: c => c.within(c.action(a => a.kind === 'ack'), c.firstAlarm(), 60) },
        { id: 'feed', key: true, text: 'Cut ethane feed so the ratio stays at or above 0.25 (≤ 24 t/h)', target: 60, eval: c => c.within(c.action(a => a.tag === 'FIC-100' && a.kind === 'sp' && a.to <= 24.5), c.alarm('ratio_low'), 60) },
        { id: 'cot', text: 'Lower the COT setpoint by at least 5 °C while steam is short', eval: c => c.byDeadline(c.action(a => a.tag === 'TIC-150' && a.kind === 'sp' && a.to <= 845, 20), 330) },
        { id: 'util', text: 'Notify utilities about the steam header', eval: c => c.byDeadline(c.action(a => a.kind === 'comm' && a.tag === 'utilities', 20), null) },
        { id: 'ramp', text: 'After steam recovers, ramp feed back to ≥ 30 t/h at ≤ 2 t/h per minute', eval: c => c.atEnd(() => c.final.feedSP >= 30 && !c.fastRamp('FIC-100', 2, 60, 330), 'Feed not restored, or ramped faster than 2 t/h per minute') }
      ],
      harmful: [
        { text: 'Raised ethane feed while the steam ratio was low', test: (a, s) => a.tag === 'FIC-100' && a.kind === 'sp' && a.to > a.from && s.ratio < 0.28 },
        { text: 'Lowered the steam ratio setpoint during a steam shortage', test: a => a.tag === 'FIC-110' && a.kind === 'sp' && a.to < a.from }
      ],
      coach: {
        feed: 'Cutting feed is the move that protects the coils: with less ethane, the steam you still have keeps the ratio up. Every minute below 0.25 builds coke you pay for at the next decoke.',
        cot: 'At low steam ratio, a slightly lower COT slows coke formation. It is the second line of defence after the feed cut.',
        ramp: 'Ramp back slowly once steam returns. A fast feed increase can overshoot the ratio controller and dip the ratio again.',
        trip: 'The ratio trip cut the feed. Watch the low-flow alarm on FIC-110: it comes first and gives you the time to act.'
      }
    },
    s2: {
      id: 's2', n: '02', name: 'One pass starving', dur: 480, diff: 2, key: 'tmtMax',
      teaser: 'A pass flow valve sticks. Its outlet and tube-metal temperatures climb.',
      state: 'Normal operation. Pass flows FIC-101A to D in AUTO, balanced at about 10.6 t/h each.',
      cause: 'Pass control valve FV-101C sticks and slowly creeps closed. It does not respond from the control room; only a field operator can free it.',
      objectives: ['Keep every pass above the low-low flow trip (62 %)', 'Keep tube-metal temperatures below 1045 °C', 'Avoid an unplanned furnace trip'],
      init(s) {},
      event(s, t) { if (t >= 20 && !s.stuckDone) { s.stuck = { f: 0.95, target: 0.5, drift: 0.0016 }; s.stuckDone = true; } },
      steps: [
        { id: 'look', text: 'Open the FIC-101C faceplate and check the valve', target: 120, eval: c => c.within(c.action(a => a.kind === 'select' && a.tag === 'FIC-101C'), c.alarm('pass_low'), 120) },
        { id: 'field', key: true, text: 'Send a field operator to FV-101C', target: 150, eval: c => c.within(c.action(a => a.kind === 'comm' && a.tag === 'field' && a.at === 'FIC-101C'), c.alarm('pass_low'), 150) },
        { id: 'sev', text: 'Lower COT setpoint ≥ 5 °C or cut feed while tube metal is high', target: 90, eval: c => c.within(c.action(a => (a.tag === 'TIC-150' && a.kind === 'sp' && a.to <= 845) || (a.tag === 'FIC-100' && a.kind === 'sp' && a.to <= 30), 20), c.alarm('tmt_high'), 90, true) },
        { id: 'sup', text: 'Inform the shift supervisor', eval: c => c.byDeadline(c.action(a => a.kind === 'comm' && a.tag === 'supervisor', 20), null) },
        { id: 'rest', text: 'Restore COT and feed setpoints once the pass flow is back', eval: c => c.atEnd(() => c.final.cotSP >= 848 && c.final.feedSP >= 31 && Math.min(...c.final.pf) > 0.95, 'Pass flow not restored or setpoints left reduced') }
      ],
      harmful: [{ text: 'Raised the COT setpoint while tube metal was high', test: (a, s) => a.tag === 'TIC-150' && a.kind === 'sp' && a.to > a.from && Math.max(...s.tmt) > 1040 }],
      coach: {
        field: 'A sticking valve is a field problem. The fastest fix is a person at the valve. Call early; the control room cannot stroke a stuck valve.',
        sev: 'While one pass runs hot, lowering COT or feed buys time for the coil. Tube metal is what limits run length.',
        look: 'Start from the alarm: the faceplate shows the valve output is not matching the flow. That tells you it is mechanical.',
        trip: 'The pass kept starving until a trip acted on high outlet temperature or low-low flow. Only the field fix stops the drift.'
      }
    },
    s3: {
      id: 's3', n: '03', name: 'Rich fuel gas', dur: 360, diff: 3, key: 'o2',
      teaser: 'Fuel heating value jumps. Arch O₂ falls and CO rises. Fuel or air first?',
      state: 'Normal operation. O₂ controller AIC-140 left in MANUAL after an analyzer calibration, damper at 60 %.',
      cause: 'Heavier components enter the fuel gas header. Heating value rises by about 13 % within a minute.',
      objectives: ['Keep arch O₂ above 1.5 % (trip below 0.5 %)', 'Keep COT within 845–865 °C', 'Avoid an unplanned furnace trip'],
      init(s) { s.aicMode = 'MAN'; },
      event(s, t) { if (t >= 15) s.lhv = Math.min(58.5, D.LHV0 + (t - 15) * 0.22); },
      // Fuel-rich firebox: the safe first move is to cut fuel, not to add air (Control Talk, Kenexis).
      steps: [
        { id: 'ack', text: 'Acknowledge the alarms', target: 60, eval: c => c.within(c.action(a => a.kind === 'ack'), c.firstAlarm(), 60) },
        { id: 'cut', key: true, text: 'Cut fuel first: lower the COT setpoint by at least 10 °C, or put TIC-150 in MANUAL and reduce fuel to 90 % or less', target: 45, eval: c => c.within(c.action(a => a.tag === 'TIC-150' && ((a.kind === 'sp' && a.to <= 840) || (a.kind === 'op' && a.to <= 90))), c.alarm('o2_low'), 45) },
        { id: 'auto', text: 'Return AIC-140 to AUTO only after O₂ is back above 1.5 % and CO is normal', eval: c => c.byDeadline(c.action(a => a.tag === 'AIC-140' && a.kind === 'mode' && a.to === 'AUTO' && a.o2 >= 1.5 && a.co < 300), null) },
        { id: 'util', text: 'Notify utilities about the fuel gas quality', eval: c => c.byDeadline(c.action(a => a.kind === 'comm' && a.tag === 'utilities', 15), null) }
      ],
      harmful: [
        { text: 'Added air to a fuel-rich firebox (opened the damper or put AIC-140 in AUTO while O₂ was below 1 % or CO was high)', test: (a, s) => a.tag === 'AIC-140' && ((a.kind === 'op' && a.to > a.from) || (a.kind === 'mode' && a.to === 'AUTO')) && (s.o2 < 1.0 || s.co > 300) },
        { text: 'Closed the damper while O₂ was low', test: (a, s) => a.tag === 'AIC-140' && a.kind === 'op' && a.to < a.from && s.o2 < 1.5 },
        { text: 'Raised firing while O₂ was low', test: (a, s) => a.tag === 'TIC-150' && (a.kind === 'sp' || a.kind === 'op') && a.to > a.from && s.o2 < 1.5 }
      ],
      coach: {
        cut: 'Low O₂ with rising CO means unburned fuel is already in the firebox. Cut fuel first and let O₂ recover. Opening the damper fast can let fresh air meet that hot fuel: the usual reflex, and the dangerous one.',
        auto: 'Hand air back to the O₂ controller only once O₂ and CO are back to normal, so the air comes back gradually into a clean firebox.',
        util: 'The cause is upstream. Utilities need to know the fuel gas changed.',
        trip: 'O₂ fell below the low-low limit and the fuel was cut. Cutting fuel early is what keeps the furnace out of this state.'
      }
    },
    s4: {
      id: 's4', n: '04', name: 'ID fan trip', dur: 240, diff: 3, key: 'draft',
      teaser: 'Draft is lost in seconds. Firebox pressure heads positive.',
      state: 'Normal operation. ID fan K-101 running, damper in AUTO via AIC-140, draft about −5 mmH₂O.',
      cause: 'The ID fan motor trips. The fan can be restarted after a 60-second motor cool-down.',
      objectives: ['Keep firebox pressure below +2 mmH₂O', 'Keep arch O₂ above the trip', 'Restart the fan and recover the furnace'],
      init(s) {},
      event(s, t) { if (t >= 15 && !s.fanTripped) { s.fanTripped = true; s.fanRun = false; s.fanSpeed = 0; s.fanAvail = t + 60; } },
      steps: [
        { id: 'damp', key: true, text: 'Open the stack damper fully (≥ 95 %)', target: 20, eval: c => c.within(c.stateTime(st => st.damper >= 95, 15), c.alarm('fan_trip'), 20) },
        { id: 'fire', text: 'Cut firing: COT setpoint −15 °C or fuel ≤ 70 % in manual', target: 40, eval: c => c.within(c.action(a => a.tag === 'TIC-150' && ((a.kind === 'sp' && a.to <= 835) || (a.kind === 'op' && a.to <= 70)), 15), c.alarm('fan_trip'), 40) },
        { id: 'feed', text: 'Reduce ethane feed to match firing (≤ 26 t/h)', target: 90, eval: c => c.within(c.action(a => a.tag === 'FIC-100' && a.kind === 'sp' && a.to <= 26, 15), c.alarm('fan_trip'), 90) },
        { id: 'fan', text: 'Restart the ID fan when available', target: 60, eval: c => c.within(c.action(a => a.kind === 'btn' && a.tag === 'K-101'), 75, 60) },
        { id: 'rest', text: 'Restore feed and COT after the fan is back', eval: c => c.atEnd(() => c.final.fanRun && c.final.feedSP >= 30 && c.final.cotSP >= 845, 'Furnace not brought back to rate') }
      ],
      harmful: [{ text: 'Raised firing while the fan was down', test: (a, s) => a.tag === 'TIC-150' && (a.kind === 'sp' || a.kind === 'op') && a.to > a.from && !s.fanRun }],
      coach: {
        damp: 'Without the fan, only natural draft is left. A fully open damper is worth more than anything else in the first seconds.',
        fire: 'Less fuel means less flue gas to remove. Cutting firing is what brings the pressure back under the trip.',
        fan: 'Restart as soon as the cool-down ends, then bring the furnace back in steps.',
        trip: 'Firebox pressure or O₂ hit the trip. In this scenario you have about 20 seconds: damper first, then firing.'
      }
    },
    s5: {
      id: 's5', n: '05', name: 'Steam drum level low', dur: 360, diff: 2, key: 'lvl',
      teaser: 'A boiler-feed pump stops. The TLE needs water before the level trip.',
      state: 'Normal operation. Steam drum V-130 at 52 %, LIC-130 in AUTO. BFW pump P-131A running, P-131B on auto-standby.',
      cause: 'BFW pump P-131A trips and the auto-start of standby P-131B fails.',
      objectives: ['Keep drum level above the trip (20 %)', 'Protect the TLE from running dry', 'Avoid an unplanned furnace trip'],
      init(s) {},
      event(s, t) { if (t >= 10 && s.ev.pumpA) s.ev.pumpA = false; },
      steps: [
        { id: 'ack', text: 'Acknowledge the alarms', target: 60, eval: c => c.within(c.action(a => a.kind === 'ack'), c.firstAlarm(), 60) },
        { id: 'pump', key: true, text: 'Start standby BFW pump P-131B', target: 45, eval: c => c.within(c.action(a => a.kind === 'btn' && a.tag === 'P-131B'), c.alarm('pump_trip'), 45) },
        { id: 'feed', text: 'If level falls below 30 %, cut feed to ≤ 27 t/h', target: 30, eval: c => c.minState('lvl') >= 30 ? { status: 'na' } : c.within(c.action(a => a.tag === 'FIC-100' && a.kind === 'sp' && a.to <= 27), c.stateTime(st => st.lvl < 30), 30) },
        { id: 'mnt', text: 'Notify maintenance about P-131A and the failed auto-start', eval: c => c.byDeadline(c.action(a => a.kind === 'comm' && a.tag === 'maintenance', 10), null) }
      ],
      harmful: [{ text: 'Raised feed while drum level was low', test: (a, s) => a.tag === 'FIC-100' && a.kind === 'sp' && a.to > a.from && s.lvl < 35 }],
      coach: {
        pump: 'The standby pump is the fix. When an auto-start fails, start it by hand straight away.',
        feed: 'Less feed means less steam generated in the TLE, which slows the level drop.',
        mnt: 'A failed auto-start is a hidden failure. Maintenance must know before the next demand.',
        trip: 'The drum level reached the low-low trip, which shuts the furnace to protect the TLE tubes.'
      }
    },
    s6: {
      id: 's6', n: '06', name: 'Is it real?', dur: 420, diff: 3, key: 'fuel',
      teaser: 'One reading jumps while the rest of the furnace says otherwise. Process upset or bad instrument?',
      state: 'Normal operation at 32 t/h ethane. TIC-150 controls the average of the four pass outlet thermocouples TI-151A to D.',
      cause: 'Pass B outlet thermocouple TI-151B drifts high (time-compressed here: about +90 °C in two and a half minutes) but stays inside its range, so the DCS shows no BAD status. TIC-150 sees a false rise in the average and cuts fuel, so the real coil outlet temperature falls. The process itself is healthy.',
      note: 'Why drift and not burnout: a burnt-out thermocouple drives its transmitter outside 4–20 mA (NAMUR NE 43). The DCS then marks the signal BAD and TIC-150 can shed to manual by itself. A drifting thermocouple gives no such flag, so only a cross-check catches it.',
      objectives: ['Tell a real upset from a bad measurement', 'Keep the real coil outlet temperature near 850 °C', 'Avoid unnecessary feed or firing cuts'],
      init(s) {},
      // time-compressed drift: +90 °C over about 150 s, then holds. Stays in range, so no BAD status.
      event(s, t) { if (t >= 25) s.tcFail = { i: 1, off: Math.min(90, (t - 25) * 0.6) }; },
      steps: [
        { id: 'look', text: 'Cross-check pass B against the other passes and its tube metal temperature (TIC-150 faceplate)', target: 90, eval: c => c.within(c.action(a => a.tag === 'TIC-150' && (a.kind === 'select' || a.kind === 'avg' || a.kind === 'mode'), 20), c.alarm('cot_high'), 90) },
        { id: 'remove', key: true, text: 'Take TI-151B out of the COT average, or put TIC-150 in MANUAL', target: 90, eval: c => c.within(c.action(a => a.tag === 'TIC-150' && ((a.kind === 'avg' && a.pass === 1 && a.to === false) || (a.kind === 'mode' && a.to === 'MAN')), 20), c.alarm('cot_high'), 90) },
        { id: 'inst', text: 'Call instrumentation about TI-151B', eval: c => c.byDeadline(c.action(a => a.kind === 'comm' && a.tag === 'instrument', 20), null) },
        { id: 'rest', text: 'Bring the real coil outlet temperature back above 840 °C by the end', eval: c => c.atEnd(() => { const v = c.final.cot.reduce((a, b) => a + b, 0) / 4; return v >= 840 && v <= 860; }, 'Real COT left away from 850 °C, so ethylene was lost') }
      ],
      harmful: [
        { text: 'Cut ethane feed because of the pass B reading', test: (a, s) => a.tag === 'FIC-100' && a.kind === 'sp' && a.to < a.from && !!s.tcFail },
        { text: 'Lowered the COT setpoint because of the pass B reading', test: (a, s) => a.tag === 'TIC-150' && a.kind === 'sp' && a.to < a.from && !!s.tcFail && s.avgIn[1] },
        { text: 'Took a healthy pass out of the COT average', test: a => a.tag === 'TIC-150' && a.kind === 'avg' && a.to === false && a.pass !== 1 }
      ],
      coach: {
        look: 'Pass B read about 90 °C above the others while its tube metal temperature, its flow and the SIS sensors stayed normal, and the other three passes fell. A reading that disagrees with everything around it is usually the instrument.',
        remove: 'Take the bad signal out of control first: deselect TI-151B from the average or put TIC-150 in manual. Every minute it stays in, the controller keeps cutting fuel for a temperature that does not exist.',
        inst: 'The fix is a new thermocouple. Instrumentation needs to know so the signal is repaired and not just bypassed.',
        rest: 'With the drifting thermocouple in the average, the real COT fell by more than 20 °C. Nothing tripped, but conversion and ethylene dropped. Bad data costs production quietly.',
        trip: 'The furnace tripped. In this scenario nothing in the process required a trip: check which action drove it there.'
      }
    }
  };

  // ---------- evaluation ----------
  function makeCtx(run, final) {
    const log = run.log, end = final.done || final.tripped ? true : false;
    const now = final.t;
    const c = {
      final, end, now,
      action(pred, after) { return log.find(a => (after == null || a.t >= after) && pred(a)) || null; },
      alarm(id) { return run.alarmFirst[id] != null ? run.alarmFirst[id] : null; },
      firstAlarm() { const v = Object.entries(run.alarmFirst).filter(([k]) => k !== 'ds_hdr' && k !== 'fg_hv').map(([, t]) => t); return v.length ? Math.min(...v) : null; },
      stateTime(pred, after) { const h = run.hist.find(x => (after == null || x.t >= after) && pred(x)); return h ? { t: h.t } : null; },
      minState(k) { return run.hist.length ? Math.min(...run.hist.map(x => x[k])) : final[k]; },
      fastRamp(tag, maxUp, win, after) {
        const ups = log.filter(a => a.tag === tag && a.kind === 'sp' && a.t >= after && a.to > a.from);
        for (const a of ups) { const sum = ups.filter(b => b.t >= a.t && b.t < a.t + win).reduce((x, b) => x + (b.to - b.from), 0); if (sum > maxUp + 1e-6) return true; }
        return false;
      },
      // action relative to a reference time (alarm), with a window in seconds
      within(act, ref, win, creditIfNoRef) {
        const refT = typeof ref === 'number' ? ref : (ref && ref.t != null ? ref.t : ref);
        if (act) {
          if (refT == null || act.t <= refT + win) return { status: 'done', t: act.t, late: 0 };
          return { status: 'late', t: act.t, late: Math.round(act.t - refT - win) };
        }
        if (refT == null) return creditIfNoRef ? { status: end ? 'na' : 'pending' } : { status: end ? 'missed' : 'pending' };
        if (!end) return { status: now > refT + win ? 'overdue' : 'pending', due: refT + win };
        return { status: 'missed' };
      },
      byDeadline(act, deadline) {
        if (act) return { status: 'done', t: act.t };
        if (!end && (deadline == null || now < deadline)) return { status: 'pending' };
        return { status: end || now >= deadline ? 'missed' : 'pending' };
      },
      atEnd(fn, failNote) { if (!end) return { status: 'pending' }; return fn() ? { status: 'done' } : { status: 'missed', note: failNote }; }
    };
    return c;
  }

  function evaluate(run, final, scn) {
    const c = makeCtx(run, final);
    const steps = scn.steps.map(st => Object.assign({ id: st.id, text: st.text, key: !!st.key, target: st.target }, st.eval(c)));
    return { steps };
  }

  function score(run, final, scn) {
    const { steps } = evaluate(run, final, scn);
    const counted = steps.filter(s => s.status !== 'na');
    const done = counted.filter(s => s.status === 'done').length + 0.5 * counted.filter(s => s.status === 'late').length;
    const procedure = Math.round(30 * done / Math.max(1, counted.length));
    const highSec = run.highAlarmSec || 0;
    let safety = final.tripped ? 0 : Math.round(40 * clamp(1 - highSec / (scn.dur * 0.6), 0, 1));
    const key = steps.find(s => s.key);
    let response = 0;
    if (key) {
      if (key.status === 'done') response = 15;
      else if (key.status === 'late') response = Math.round(15 * clamp(1 - key.late / (2 * (key.target || 60)), 0, 1));
    }
    const prodRatio = final.base > 0 ? final.ethylene / final.base : 1;
    let production = Math.round(clamp(15 * prodRatio - Math.min(6, final.coke * 0.5), 0, 15));
    const harmful = run.harmful.slice();
    const hints = run.hints || 0;
    let total = safety + procedure + response + production - 5 * harmful.length - 3 * hints;
    if (final.tripped) total = Math.min(total, 40);
    total = clamp(Math.round(total), 0, 100);
    const verdict = final.tripped ? 'FURNACE TRIPPED' : total >= 85 ? 'EXCELLENT' : total >= 70 ? 'COMPETENT' : total >= 50 ? 'NEEDS PRACTICE' : 'NOT YET';
    return { total, safety, procedure, response, production, steps, harmful, hints, verdict, prodRatio, coke: final.coke };
  }

  // ---------- run wrapper (alarms, log, history) ----------
  // opts.pre: quiet seconds before the scenario clock reaches 0 (used for surprise shifts)
  function createRun(scnId, opts) {
    const scn = SCN[scnId], pre = (opts && opts.pre) || 0;
    const run = { scn, s: initState(scn), log: [], alarmFirst: {}, alarms: {}, hist: [], harmful: [], highAlarmSec: 0, hints: 0, lastHist: -Infinity, pre };
    run.s.t = -pre;
    return run;
  }
  function tick(run, dt) {
    const s = run.s;
    const sub = Math.max(1, Math.ceil(dt / 0.25));
    for (let i = 0; i < sub; i++) {
      step(s, dt / sub, run.scn);
      updateAlarms(run, dt / sub);
      if (s.tripped || s.done) break;
    }
    if (Math.floor(s.t) > run.lastHist) {
      run.lastHist = Math.floor(s.t);
      run.hist.push({ t: s.t, feed: s.feed, feedSP: s.feedSP, ratio: s.ratio, cot: s.cot.reduce((a, b) => a + b, 0) / 4, cotpv: cotPV(s), fuel: s.fuelOP, cotC: s.cot[2], tmtC: s.tmt[2], tmtMax: Math.max(...s.tmt), o2: s.o2, draft: s.draft, lvl: s.lvl, damper: s.damper, pfC: s.pf[2] });
    }
  }
  function updateAlarms(run, dt) {
    const s = run.s;
    let high = false;
    for (const a of ALARMS) {
      const on = !!a.on(s);
      const cur = run.alarms[a.id];
      if (on && !cur) { run.alarms[a.id] = { id: a.id, t: s.t, ack: false, active: true }; if (run.alarmFirst[a.id] == null) run.alarmFirst[a.id] = s.t; }
      else if (on && cur) cur.active = true;
      else if (!on && cur) { cur.active = false; if (cur.ack) delete run.alarms[a.id]; }
      if (on && a.pri === 'HIGH' && a.id !== 'fan_trip' && a.id !== 'pump_trip') high = true;
    }
    if (high) run.highAlarmSec += dt;
  }
  function act(run, a) {
    const s = run.s;
    a.t = s.t; a.o2 = s.o2; a.co = s.co;
    for (const h of run.scn.harmful) if (h.test(a, s) && !run.harmful.find(x => x.text === h.text)) run.harmful.push({ text: h.text, t: s.t });
    run.log.push(a);
  }
  function ackAll(run) {
    let n = 0;
    for (const k of Object.keys(run.alarms)) { const al = run.alarms[k]; if (!al.ack) { al.ack = true; n++; } if (!al.active) delete run.alarms[k]; }
    act(run, { kind: 'ack', tag: 'ALL', n });
  }

  root.Furnace = { solveCoil, CAL0, createRun, tick, act, ackAll, D, LIM, ALARMS, TRIPS, SCN, initState, step, evaluate, score, clamp, cotPV };
})(typeof window !== 'undefined' ? window : globalThis);
