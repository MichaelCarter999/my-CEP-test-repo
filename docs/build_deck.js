const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const {
  FaBolt, FaProjectDiagram, FaChartLine, FaShieldAlt, FaCodeBranch,
  FaLayerGroup, FaCheckCircle, FaExclamationTriangle, FaServer, FaRoute
} = require("react-icons/fa");

// ---- palette (dark NOC) ----
const BG = "0B0F17", PANEL = "121826", LINE = "1F2A3D";
const INK = "E6EDF6", MUTED = "8AA0BD";
const ACCENT = "34D399";   // mint/green (suppression / healthy)
const BLUE = "60A5FA";
const ALERT = "F87171";    // red (noise)
const AMBER = "FBBF24";

async function icon(Comp, color = "#" + INK, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color, size: String(size) }));
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}
const shadow = () => ({ type: "outer", color: "000000", blur: 8, offset: 3, angle: 90, opacity: 0.35 });

(async () => {
  const p = new pptxgen();
  p.layout = "LAYOUT_WIDE";          // 13.3 x 7.5
  p.author = "Mick Morrow";
  p.title = "CEP — Deterministic Alarm Correlation";
  const W = 13.3;

  const ic = {};
  for (const [k, C, col] of [
    ["bolt", FaBolt, ALERT], ["diag", FaProjectDiagram, BLUE],
    ["chart", FaChartLine, ACCENT], ["shield", FaShieldAlt, ACCENT],
    ["branch", FaCodeBranch, BLUE], ["layer", FaLayerGroup, AMBER],
    ["check", FaCheckCircle, ACCENT], ["warn", FaExclamationTriangle, AMBER],
    ["server", FaServer, BLUE], ["route", FaRoute, ACCENT],
  ]) ic[k] = await icon(C, "#" + col);

  const title = (s, t, sub) => {
    s.addText(t, { x: 0.7, y: 0.5, w: W - 1.4, h: 0.7, fontSize: 32, bold: true,
      color: INK, fontFace: "Calibri", margin: 0 });
    if (sub) s.addText(sub, { x: 0.7, y: 1.18, w: W - 1.4, h: 0.4, fontSize: 15,
      color: MUTED, fontFace: "Calibri", margin: 0 });
  };
  const card = (s, x, y, w, h, fill) => s.addShape(p.shapes.ROUNDED_RECTANGLE,
    { x, y, w, h, rectRadius: 0.08, fill: { color: fill || PANEL },
      line: { color: LINE, width: 1 }, shadow: shadow() });

  // ===== 1. TITLE =====
  let s = p.addSlide(); s.background = { color: BG };
  s.addImage({ data: ic.diag, x: 0.7, y: 1.6, w: 0.9, h: 0.9 });
  s.addText("Deterministic Alarm Correlation", { x: 0.7, y: 2.6, w: 11.8, h: 1.0,
    fontSize: 46, bold: true, color: INK, fontFace: "Calibri", margin: 0 });
  s.addText("…without the platform tax", { x: 0.7, y: 3.6, w: 11.8, h: 0.7,
    fontSize: 30, italic: true, color: ACCENT, fontFace: "Calibri", margin: 0 });
  s.addText("Topology-aware root-cause suppression on open-source tooling — Zabbix, Nautobot, a small Python CEP sidecar, Grafana.",
    { x: 0.7, y: 4.5, w: 10.5, h: 0.8, fontSize: 16, color: MUTED, fontFace: "Calibri", margin: 0 });
  s.addText("A working demo · alternative to the HPE / OpenText TeMIP route",
    { x: 0.7, y: 6.6, w: 11, h: 0.4, fontSize: 13, color: MUTED, fontFace: "Calibri", margin: 0 });
  s.addNotes("Frame: this is a capability demo, not an anti-vendor rant. The claim is that the *capability* is commodity; the *price* buys carrier-scale runtime and support.");

  // ===== 2. THE PROBLEM =====
  s = p.addSlide(); s.background = { color: BG };
  title(s, "The problem a NOC actually has", "One fault. Hundreds of alarms. Operators drown in symptoms.");
  s.addImage({ data: ic.bolt, x: 0.7, y: 1.9, w: 0.7, h: 0.7 });
  card(s, 0.7, 2.8, 3.7, 3.4);
  s.addText("200", { x: 0.7, y: 3.2, w: 3.7, h: 1.1, fontSize: 72, bold: true,
    color: ALERT, align: "center", fontFace: "Calibri", margin: 0 });
  s.addText("raw alarms from ONE upstream failure", { x: 0.9, y: 4.4, w: 3.3, h: 0.9,
    fontSize: 15, color: MUTED, align: "center", fontFace: "Calibri" });
  s.addText([
    { text: "Every device behind the fault alarms independently", options: { bullet: true, breakLine: true, color: INK } },
    { text: "No way to tell the cause from the consequences", options: { bullet: true, breakLine: true, color: INK } },
    { text: "Alert fatigue → real incidents missed", options: { bullet: true, breakLine: true, color: INK } },
    { text: "This is the gap TeMIP is sold to close", options: { bullet: true, color: ACCENT } },
  ], { x: 4.9, y: 3.0, w: 7.6, h: 3.0, fontSize: 18, fontFace: "Calibri",
       paraSpaceAfter: 14, valign: "middle" });

  // ===== 3. TEMIP vs REALITY =====
  s = p.addSlide(); s.background = { color: BG };
  title(s, "What TeMIP sells — and where it's beatable", null);
  const rows = [
    ["Vendor-neutral normalisation", "An inventory + tagging problem", "Nautobot is the source of truth"],
    ["Topology-aware RCA", "A Drools rule engine over a topology model (UCA EBC)", "networkx graph + windowed rules"],
    ["Carrier scale (millions/s)", "The real reason for the price", "Kafka + FlinkCEP/Drools — open source"],
    ["X.733 lifecycle / state", "Mature", "Deterministic ROOT/SYMPTOM/CLEARED states"],
  ];
  const head = (t, c) => ({ text: t, options: { bold: true, color: c, fill: { color: PANEL }, fontFace: "Calibri", valign: "middle" } });
  const cell = (t, c) => ({ text: t, options: { color: c || INK, fill: { color: BG }, fontFace: "Calibri", valign: "middle" } });
  s.addTable([
    [head("TeMIP claim", INK), head("Reality", MUTED), head("Open-stack answer", ACCENT)],
    ...rows.map(r => [cell(r[0]), cell(r[1], MUTED), cell(r[2], ACCENT)]),
  ], { x: 0.7, y: 1.8, w: 11.9, h: 4.6, colW: [3.6, 4.3, 4.0], rowH: [0.7, 1.0, 1.0, 1.0, 0.9],
       fontSize: 14, border: { pt: 1, color: LINE }, margin: 6, valign: "middle" });

  // ===== 4. ARCHITECTURE =====
  s = p.addSlide(); s.background = { color: BG };
  title(s, "Architecture", "Reuses what you already run; adds one Python container.");
  const box = (x, y, w, label, sub, col) => {
    card(s, x, y, w, 1.0, PANEL);
    s.addText(label, { x: x + 0.15, y: y + 0.12, w: w - 0.3, h: 0.45, fontSize: 16,
      bold: true, color: col || INK, fontFace: "Calibri", margin: 0 });
    s.addText(sub, { x: x + 0.15, y: y + 0.55, w: w - 0.3, h: 0.35, fontSize: 11,
      color: MUTED, fontFace: "Calibri", margin: 0 });
  };
  const arrow = (x, y, w) => s.addShape(p.shapes.LINE, { x, y, w, h: 0,
    line: { color: BLUE, width: 2, endArrowType: "triangle" } });
  box(0.7, 2.2, 3.0, "Nautobot", "topology + dependency (GraphQL)", BLUE);
  box(0.7, 3.7, 3.0, "Zabbix", "problems you already collect", BLUE);
  arrow(3.75, 4.2, 1.1);
  box(5.0, 2.95, 3.3, "CEP sidecar", "windowed topology-keyed RCA", ACCENT);
  arrow(8.35, 3.0, 1.0);
  box(9.5, 2.2, 3.1, "Grafana", "throughput · latency · ratio", AMBER);
  arrow(8.35, 3.9, 1.0);
  box(9.5, 3.7, 3.1, "React Flow UI", "live correlation visual", AMBER);
  s.addShape(p.shapes.LINE, { x: 2.2, y: 3.7, w: 0, h: 0, line: { color: LINE } });
  s.addText("Same deterministic rule, three runtimes — pure Python (lab) → +Redis (mid) → Kafka+Flink/Drools (carrier).",
    { x: 0.7, y: 6.5, w: 11.9, h: 0.5, fontSize: 14, italic: true, color: MUTED, fontFace: "Calibri", margin: 0 });

  // ===== 5. DEMO NETWORK =====
  s = p.addSlide(); s.background = { color: BG };
  title(s, "The demo network — 32 nodes", "RSTP-protected rings (mstpd) + long routed spurs (FRR/OSPF).");
  const stat = (x, n, l, c, ico) => {
    card(s, x, 2.1, 2.7, 2.0, PANEL);
    s.addImage({ data: ico, x: x + 0.2, y: 2.3, w: 0.5, h: 0.5 });
    s.addText(n, { x: x + 0.1, y: 2.85, w: 2.5, h: 0.8, fontSize: 40, bold: true,
      color: c, align: "center", fontFace: "Calibri", margin: 0 });
    s.addText(l, { x: x + 0.1, y: 3.6, w: 2.5, h: 0.4, fontSize: 12, color: MUTED,
      align: "center", fontFace: "Calibri", margin: 0 });
  };
  stat(0.7, "18", "RSTP ring switches (3x6)", ACCENT, ic.shield);
  stat(3.6, "3", "FRR distribution", BLUE, ic.route);
  stat(6.5, "9", "spur routers (chains)", BLUE, ic.server);
  stat(9.4, "2", "redundant cores", AMBER, ic.layer);
  s.addText([
    { text: "Ring members have no RCA parent — RSTP protects them, so a single ring-link break must NOT cascade. The correlator proves that contrast.", options: { bullet: true, breakLine: true, color: INK } },
    { text: "Spurs are single-threaded — losing the head cascades down the whole chain, producing the high suppression ratios that sell the story.", options: { bullet: true, color: INK } },
  ], { x: 0.7, y: 4.5, w: 11.9, h: 2.0, fontSize: 16, fontFace: "Calibri", paraSpaceAfter: 12 });

  // ===== 6. THE MONEY METRIC =====
  s = p.addSlide(); s.background = { color: BG };
  title(s, "The number that lands", "One root cause absorbs the storm — measured live in Grafana.");
  card(s, 0.7, 2.1, 3.6, 4.1, PANEL);
  s.addImage({ data: ic.chart, x: 0.95, y: 2.35, w: 0.55, h: 0.55 });
  s.addText("99.5%", { x: 0.7, y: 3.1, w: 3.6, h: 1.1, fontSize: 60, bold: true,
    color: ACCENT, align: "center", fontFace: "Calibri", margin: 0 });
  s.addText("noise reduction", { x: 0.7, y: 4.2, w: 3.6, h: 0.4, fontSize: 16,
    color: MUTED, align: "center", fontFace: "Calibri" });
  s.addText("sub-millisecond per alarm · on a laptop", { x: 0.8, y: 4.7, w: 3.4, h: 0.8,
    fontSize: 13, color: MUTED, align: "center", fontFace: "Calibri" });
  s.addChart(p.charts.BAR, [{
    name: "Alarms operators see", labels: ["Before correlation", "After correlation"], values: [200, 1],
  }], { x: 4.7, y: 2.2, w: 7.9, h: 3.9, barDir: "col",
    chartColors: [ALERT, ACCENT], chartArea: { fill: { color: BG } },
    plotArea: { fill: { color: BG } },
    catAxisLabelColor: MUTED, valAxisLabelColor: MUTED,
    valGridLine: { color: LINE, size: 0.5 }, catGridLine: { style: "none" },
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: INK,
    dataLabelFontSize: 16, showLegend: false, showTitle: false,
    barGapWidthPct: 60 });

  // ===== 7. SAME RULE, THREE RUNTIMES =====
  s = p.addSlide(); s.background = { color: BG };
  title(s, "Same rule, three runtimes", "Capability is constant. Only the engine changes with scale.");
  const tier = (x, name, eng, vol, col, ico) => {
    card(s, x, 2.2, 3.85, 3.7, PANEL);
    s.addImage({ data: ico, x: x + 0.25, y: 2.45, w: 0.55, h: 0.55 });
    s.addText(name, { x: x + 0.25, y: 3.15, w: 3.4, h: 0.5, fontSize: 20, bold: true,
      color: col, fontFace: "Calibri", margin: 0 });
    s.addText(eng, { x: x + 0.25, y: 3.75, w: 3.4, h: 0.8, fontSize: 14, color: INK,
      fontFace: "Calibri", margin: 0 });
    s.addText(vol, { x: x + 0.25, y: 4.7, w: 3.4, h: 0.8, fontSize: 13, color: MUTED,
      fontFace: "Calibri", margin: 0 });
  };
  tier(0.7, "Lab / regional", "Pure Python sidecar", "1000s alarms/s · the demo · most real needs", ACCENT, ic.check);
  tier(4.72, "Mid", "Python + Redis (N workers)", "10k+/s · national network", BLUE, ic.branch);
  tier(8.74, "Carrier", "Kafka + FlinkCEP / Drools", "millions/s · the only tier that may justify TeMIP — still open source", AMBER, ic.layer);
  s.addText("TeMIP / UCA EBC is literally a Drools rule engine over a topology model. We demonstrate the same architecture.",
    { x: 0.7, y: 6.25, w: 11.9, h: 0.6, fontSize: 14, italic: true, color: MUTED, fontFace: "Calibri", margin: 0 });

  // ===== 8. HONEST CAVEATS =====
  s = p.addSlide(); s.background = { color: BG };
  title(s, "Honest caveats", "Say these in the room — they build credibility.");
  const cav = [
    ["TeMIP is mature & carrier-grade", "At true telco volumes with strict SLAs and 24/7 vendor support, it earns its place."],
    ["This demo's engine is lab-tier", "The production equivalent is Kafka + FlinkCEP/Drools — real engineering, not a weekend."],
    ["The hard part isn't the engine", "It's keeping the dependency graph accurate — a data discipline you need regardless of vendor."],
  ];
  let cy = 2.1;
  for (const [h, d] of cav) {
    card(s, 0.7, cy, 11.9, 1.25, PANEL);
    s.addImage({ data: ic.warn, x: 0.95, y: cy + 0.35, w: 0.5, h: 0.5 });
    s.addText(h, { x: 1.7, y: cy + 0.18, w: 10.6, h: 0.45, fontSize: 18, bold: true,
      color: INK, fontFace: "Calibri", margin: 0 });
    s.addText(d, { x: 1.7, y: cy + 0.63, w: 10.6, h: 0.5, fontSize: 14, color: MUTED,
      fontFace: "Calibri", margin: 0 });
    cy += 1.45;
  }

  // ===== 9. RECOMMENDATION =====
  s = p.addSlide(); s.background = { color: BG };
  s.addImage({ data: ic.check, x: 0.7, y: 1.5, w: 0.9, h: 0.9 });
  s.addText("Recommendation", { x: 0.7, y: 2.5, w: 11.8, h: 0.8, fontSize: 38, bold: true,
    color: INK, fontFace: "Calibri", margin: 0 });
  s.addText([
    { text: "Adopt the open stack for the regional / mid tier — it covers the majority of real correlation needs.", options: { bullet: true, breakLine: true, color: INK } },
    { text: "Reserve a carrier-grade evaluation for the specific contracts that genuinely run at millions-of-alarms scale.", options: { bullet: true, breakLine: true, color: INK } },
    { text: "Prove the capability first with this demo. Let the scale requirement — not the vendor pitch — drive any spend.", options: { bullet: true, color: ACCENT } },
  ], { x: 0.7, y: 3.5, w: 11.6, h: 2.6, fontSize: 19, fontFace: "Calibri", paraSpaceAfter: 16 });
  s.addText("github.com/mmorrow24work/CEP", { x: 0.7, y: 6.6, w: 11, h: 0.4, fontSize: 14,
    color: MUTED, fontFace: "Calibri", margin: 0 });

  await p.writeFile({ fileName: "CEP-Sales-Pitch.pptx" });
  console.log("wrote CEP-Sales-Pitch.pptx");
})();
