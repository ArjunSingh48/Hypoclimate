"""Printable HTML reports: one-page advisor report and a portfolio overview.

Open the downloaded file in a browser and use Print -> Save as PDF.
"""
from __future__ import annotations

import html
from datetime import date

CSS = """
body{font-family:Arial,Helvetica,sans-serif;color:#1d1d1d;margin:28px;font-size:12px}
h1{font-size:20px;margin:0 0 2px} h2{font-size:14px;margin:18px 0 6px;border-bottom:1px solid #ccc}
.muted{color:#666} .row{display:flex;gap:12px} .box{flex:1;border:1px solid #ddd;border-radius:6px;padding:10px}
.big{font-size:22px;font-weight:bold} table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid #eee;padding:4px 6px;text-align:left} th{background:#f4f4f4}
.high{color:#c62828;font-weight:bold}.medium{color:#ef6c00;font-weight:bold}.low{color:#2e7d32}
.foot{margin-top:18px;font-size:10px;color:#666}
@media print{body{margin:12mm}}
"""


def _e(x) -> str:
    return html.escape("–" if x is None else str(x))


def _chf(v) -> str:
    return "–" if v is None else f"CHF {v:,.0f}".replace(",", "'")


def _rng(r) -> str:
    if not r:
        return "–"
    a, b = sorted(r, key=abs)
    return f"CHF {a:,.0f} to {b:,.0f}".replace(",", "'")


def _talking_points(r: dict) -> list[str]:
    pts = []
    hz, b, en = r["hazards"], r["building"], r["energy"]
    if hz["river_flood_100"]["level"] == "high":
        pts.append("The building lies in the 100-year river flood area (indicative federal map). "
                   "The cantonal building insurance covers structural damage; check contents "
                   "insurance and basement use, and the binding cantonal hazard map.")
    if hz["surface_runoff"]["level"] in ("medium", "high"):
        pts.append("The address is in a surface-runoff zone: check entrances, light wells and "
                   "basement protection against heavy rain.")
    if b.get("energy_source") in ("oil", "gas"):
        pts.append(f"The {b['energy_source']} heating will likely need replacing during the "
                   "mortgage term. A renovation tranche or green-mortgage rate can fund a heat pump.")
    if en.get("roof_class") in ("good", "very good", "excellent"):
        pts.append(f"The roof is rated {en['roof_class']} for solar. Solar income and lower "
                   "energy costs improve affordability.")
    if not pts:
        pts.append("No major climate or transition risk found with the federal open data.")
    return pts


def advisor_report(r: dict, client: str = "", advisor: str = "") -> str:
    s, c, b, en = r["scores"], r["chf"], r["building"], r["energy"]
    rows = "".join(
        f"<tr><td>{_e(h['label'])}</td><td>{_e(h['finding'])}</td>"
        f"<td class='{h['level']}'>{_e(h['level'].capitalize())}</td></tr>"
        for h in r["hazards"].values())
    ltv = c["ltv_today_pct"]
    after = c["ltv_after_pct"]
    ltv_txt = f"{ltv}%" + (f" → {after[0]}–{after[1]}%" if after and after[1] != ltv else "") \
        if ltv else "–"
    pts = "".join(f"<li>{_e(p)}</li>" for p in _talking_points(r))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>HypoClimate advisor report</title><style>{CSS}</style></head><body>
<div class="muted">HYPOCLIMATE · ADVISOR REPORT · {date.today():%d.%m.%Y}
{(' · Client: ' + _e(client)) if client else ''}{(' · Advisor: ' + _e(advisor)) if advisor else ''}</div>
<h1>{_e(r['address'])}</h1>
<div class="muted">Built {_e(b.get('period_label'))} · {_e(b.get('flats'))} flat(s) ·
heating: {_e(b.get('energy_source'))} · EGID {_e(r.get('egid'))}</div>
<div class="row" style="margin-top:12px">
 <div class="box">Physical risk<div class="big">{_e(s['physical'])} / 5</div>{_e(s['physical_label'])}</div>
 <div class="box">Transition risk<div class="big">{_e(s['transition'])} / 5</div>{_e(s['transition_label'])}</div>
 <div class="box">Loan-to-value<div class="big">{_e(ltv_txt)}</div>after flood-zone discount</div>
</div>
<h2>Natural hazards</h2><table><tr><th>Hazard</th><th>Finding</th><th>Level</th></tr>{rows}</table>
<div class="row"><div style="flex:1"><h2>Energy</h2><table>
<tr><td>Heating</td><td>{_e(b.get('energy_source'))}</td></tr>
<tr><td>Heating demand</td><td>{_e(en.get('heat_demand_kwh'))} kWh/yr</td></tr>
<tr><td>CO₂ (est.)</td><td>{_e(c['co2_t_per_year'])} t/yr</td></tr>
<tr><td>Best roof for solar</td><td>{_e(en.get('roof_class'))}, {_e(en.get('solar_kwh'))} kWh/yr</td></tr>
</table></div><div style="flex:1"><h2>Costs to plan for (estimates)</h2><table>
<tr><td>Value discount, flood zone</td><td>{_rng(c['value_discount'])}</td></tr>
<tr><td>CO₂ levy</td><td>{_chf(c['co2_levy_per_year'])} / yr</td></tr>
<tr><td>Heat pump replacement</td><td>{_rng(c['heat_pump_cost'])}</td></tr>
<tr><td>Solar income</td><td>{_chf(c['solar_income_per_year'])} / yr</td></tr>
</table></div></div>
<h2>Talking points for the client</h2><ul>{pts}</ul>
<div class="foot">Data: swisstopo, FOEN, MeteoSwiss, FSO building register, Swiss Federal Office of
Energy (open government data), data as of {_e(r['meta']['queried_at'])}, assumptions
{_e(r['meta']['assumptions_version'])}. Information, not advice. Federal flood maps are indicative;
the cantonal hazard map is binding. Cost figures are model estimates.</div>
</body></html>"""


def portfolio_report(summary: dict, example: bool) -> str:
    k = summary["kpis"]
    kp = "".join(
        f"<div class='box'>{t}<div class='big'>{k[key]['pct']}%</div>"
        f"{k[key]['loans']} loans · {_chf(k[key]['chf'])}</div>"
        for key, t in [("flood_100", "In river flood area (100-yr)"),
                       ("runoff", "In surface-runoff zone"),
                       ("fossil", "Oil or gas heating"), ("high_overall", "High overall risk")])
    lv = "".join(f"<tr><td>{_e(h)}</td><td>{v['low']}%</td><td>{v['medium']}%</td>"
                 f"<td>{v['high']}%</td><td>{v['unknown']}%</td></tr>"
                 for h, v in summary["hazard_levels"].items())
    heat = "".join(f"<tr><td>{_e(h)}</td><td>{p}%</td></tr>"
                   for h, p in summary["heating_mix"].items())
    top = "".join(f"<tr><td>{_e(t['loan'])}</td><td>{_e(t['where'])}</td>"
                  f"<td>{_chf(t['exposure_chf'])}</td><td>{_e(t['ltv_pct'])}%</td>"
                  f"<td>{_e(t['physical'])}</td><td>{_e(t['transition'])}</td>"
                  f"<td>{_e(t['main_driver'])}</td></tr>" for t in summary["top_risk"])
    warn = ("<p class='high'>EXAMPLE DATA: all loans in this report are invented for the demo."
            "</p>") if example else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>HypoClimate portfolio overview</title><style>{CSS}</style></head><body>
<div class="muted">HYPOCLIMATE · CLIMATE-RISK OVERVIEW OF THE MORTGAGE BOOK · {date.today():%d.%m.%Y}</div>
<h1>Draft input for the materiality assessment (FINMA Circular 2026/1)</h1>{warn}
<p>{summary['scored']} of {summary['loans']} loans scored ({summary['coverage_pct']}%),
exposure {_chf(summary['exposure_chf'])}.</p>
<div class="row">{kp}</div>
<h2>Share of loans by hazard level</h2><table><tr><th>Hazard</th><th>Low</th><th>Medium</th>
<th>High</th><th>No data</th></tr>{lv}</table>
<div class="row"><div style="flex:1"><h2>Heating systems (transition risk)</h2><table>{heat}</table></div></div>
<h2>Highest-risk loans</h2><table><tr><th>Loan</th><th>Where</th><th>Exposure</th><th>LTV</th>
<th>Physical</th><th>Transition</th><th>Main driver</th></tr>{top}</table>
<h2>Method and limits</h2><p>Every address is scored with official open data (FOEN, MeteoSwiss,
FSO building register, SFOE). Federal flood maps are indicative and ignore flood protection; the
runoff layer shows only "in zone or not". CHF figures are model estimates. Information, not advice.</p>
</body></html>"""
