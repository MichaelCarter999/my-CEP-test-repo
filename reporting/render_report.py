#!/usr/bin/env python3
"""
render_report.py — turn reporting/results.json into a self-contained, dark
NOC-themed HTML report. No build step, no external assets: safe to commit,
attach to a Zabbix problem, or publish to GitHub Pages.

    python -m pytest tests/ -q          # writes reporting/results.json (via conftest)
    python reporting/render_report.py   # writes reporting/report.html
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "results.json")
OUT = os.path.join(HERE, "report.html")
TAU = 2 * 3.14159 * 42


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render():
    d = json.load(open(SRC))
    pass_pct = round(100 * d["passed"] / d["total"]) if d["total"] else 0
    accent = "#2dd4a7" if d["failed"] == 0 else "#f2495c"

    rows = []
    for r in d["results"]:
        ok = r["outcome"] == "passed"
        color = "#2dd4a7" if ok else ("#f2495c" if r["outcome"] == "failed" else "#f5a524")
        glyph = "PASS" if ok else r["outcome"].upper()
        fail = f'<pre class="fail">{esc(r["longrepr"])}</pre>' if r.get("longrepr") else ""
        rows.append(f"""
        <div class="case">
          <div class="case-h">
            <span class="badge" style="background:{color}1a;color:{color};border-color:{color}55">{glyph}</span>
            <span class="name">{esc(r['name'])}</span>
            <span class="dur">{r['duration_ms']:.1f} ms</span>
          </div>
          <div class="sum">{esc(r['summary'])}</div>
          {fail}
        </div>""")

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CEP Correlation — Test Report</title>
<style>
  :root{{--bg:#0b0f17;--panel:#131a26;--line:#1f2a3a;--ink:#e6edf6;--muted:#7c8aa0;--accent:{accent}}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:40px 20px;max-width:860px;margin:0 auto}}
  header{{display:flex;align-items:flex-end;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:20px}}
  h1{{font-size:20px;font-weight:650}} .subt{{color:var(--muted);font-size:13px;margin-top:4px}}
  .ring{{position:relative;width:96px;height:96px}}
  .ring svg{{transform:rotate(-90deg)}}
  .ring .pct{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;color:var(--accent)}}
  .stats{{display:flex;gap:12px;margin:22px 0 28px}}
  .stat{{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
  .stat .v{{font-size:26px;font-weight:700}}
  .stat .l{{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);margin-top:2px}}
  .case{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}}
  .case-h{{display:flex;align-items:center;gap:12px}}
  .badge{{font-size:11px;font-weight:700;letter-spacing:.5px;border:1px solid;border-radius:6px;padding:2px 8px}}
  .name{{font-weight:600;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}}
  .dur{{margin-left:auto;color:var(--muted);font-size:12px}}
  .sum{{color:#aeb9ca;font-size:13.5px;margin-top:8px}}
  pre.fail{{margin-top:10px;background:#1a0e12;border:1px solid #3a2530;border-radius:8px;padding:12px;color:#f7a5b0;font-size:12px;overflow:auto;white-space:pre-wrap}}
  footer{{color:var(--muted);font-size:12px;margin-top:28px;text-align:center}}
</style></head><body>
<header>
  <div><h1>CEP Correlation — Test Report</h1>
    <div class="subt">Executable specification &middot; every sales-pitch claim is asserted here</div></div>
  <div class="ring">
    <svg width="96" height="96"><circle cx="48" cy="48" r="42" fill="none" stroke="#1f2a3a" stroke-width="8"/>
      <circle cx="48" cy="48" r="42" fill="none" stroke="{accent}" stroke-width="8"
        stroke-linecap="round" stroke-dasharray="{TAU:.1f}"
        stroke-dashoffset="{TAU*(1-pass_pct/100):.1f}"/></svg>
    <div class="pct">{pass_pct}%</div>
  </div>
</header>
<div class="stats">
  <div class="stat"><div class="v" style="color:#2dd4a7">{d['passed']}</div><div class="l">Passed</div></div>
  <div class="stat"><div class="v" style="color:#f2495c">{d['failed']}</div><div class="l">Failed</div></div>
  <div class="stat"><div class="v" style="color:#f5a524">{d['skipped']}</div><div class="l">Skipped</div></div>
  <div class="stat"><div class="v">{d['duration_ms']:.0f}<span style="font-size:13px;color:var(--muted)"> ms</span></div><div class="l">Duration</div></div>
</div>
{''.join(rows)}
<footer>Generated {d['generated']} &middot; CEP demo &middot; github.com/mmorrow24work/CEP</footer>
</body></html>"""
    with open(OUT, "w") as f:
        f.write(html)
    print(f"wrote {OUT} ({len(html)} bytes) — {d['passed']}/{d['total']} passed")


if __name__ == "__main__":
    render()
