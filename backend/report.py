"""Printable HTML reports: one-page advisor report and a portfolio overview.

Open the downloaded file in a browser and use Print -> Save as PDF.
"""
from __future__ import annotations

import html
from datetime import date

from . import config

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


# ---------------------------------------------------------------------------
# Advisor report: one printable A4 page for the mortgage talk
# ---------------------------------------------------------------------------
# Everything below only READS the engine's JSON answer; no figure is calculated here
# except text and the choice of which rows, talking points and next steps to show.

ADVISOR_CSS = """
html{background:transparent} body{margin:0;max-width:none}
.page{background:#fff;padding:28px} .sheet{max-width:820px}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.who{text-align:right;font-size:11px;line-height:1.7;color:#444;white-space:nowrap}
.who b{display:inline-block;min-width:150px;border-bottom:1px solid #bbb;text-align:left;
  font-weight:normal;color:#1d1d1d;padding-left:4px}
.kicker{font-size:10px;letter-spacing:.08em;color:#666;margin-bottom:4px}
.box .lbl{font-size:11px;color:#555} .box .drv{font-size:11px;color:#555;margin-top:2px}
.unknown{color:#757575;font-style:italic}
.note{background:#fff8e1;border-left:3px solid #ef6c00;padding:6px 8px;margin:8px 0;font-size:11px}
.check{background:#f4f4f4;border-left:3px solid #757575;padding:6px 8px;margin:10px 0;font-size:11px}
.check ul{margin:2px 0 0 16px;padding:0}
ul.pts{margin:4px 0 0 18px;padding:0} ul.pts li{margin-bottom:4px}
ul.steps{list-style:none;margin:4px 0 0;padding:0} ul.steps li{margin-bottom:4px}
ul.steps li:before{content:"\\2610";margin-right:8px;font-size:13px}
td.num{text-align:right;white-space:nowrap}
.printbtn{display:block;margin:0 0 14px;padding:8px 16px;border:1px solid #c62828;border-radius:6px;
  background:#c62828;color:#fff;font-size:14px;cursor:pointer}
.printbtn:hover{background:#b71c1c}
@page{size:A4;margin:0}
@media print{body{margin:0}.page{padding:12mm}.printbtn{display:none}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""

_LEVEL_TEXT = {"high": "High", "medium": "Medium", "low": "Low", "unknown": "No data"}
_FOSSIL = ("oil", "gas")
_GOOD_ROOF = ("good", "very good", "excellent")


def fmt_num(v, unit="") -> str:
    if v is None:
        return "–"
    return f"{v:,.0f}".replace(",", "'") + (f" {unit}" if unit else "")


def cap_first(x) -> str:
    return "–" if not x else str(x)[0].upper() + str(x)[1:]


def building_insurer(canton: str | None) -> str | None:
    """Who insures the building against natural hazards, e.g. 'GVB (cantonal, BE)'."""
    if not canton:
        return None
    if canton in config.CANTONAL_BUILDING_INSURER:
        return f"{config.CANTONAL_BUILDING_INSURER[canton]} (cantonal, {canton})"
    if canton in config.PRIVATE_BUILDING_INSURANCE_CANTONS:
        return f"Private insurer ({canton}, no cantonal building insurance)"
    return None


def finding_text(key: str, h: dict) -> str:
    """Plain-language finding for one hazard, as in the mockup."""
    f = h.get("finding") or ""
    if h["level"] == "unknown":
        return "No data: source could not be read"
    inside = f == "inside zone"
    if key == "river_flood_100":
        return "Inside flood area (indicative federal map)" if inside else "Outside flood area"
    if key == "extreme_flood_300plus":
        return "Inside flood area" if inside else "Outside flood area"
    if key == "surface_runoff":
        return "Inside runoff zone (no flow depth)" if inside else "Outside runoff zone"
    if key in ("rockfall", "avalanche"):
        return "Inside hazard area" if inside else "Outside hazard areas"
    if key == "hail_50y":
        return f"{f} hailstones expected every 50 years"
    if key == "storm_50y":
        return f"{f} gusts expected every 50 years"
    return f


def _lvl(r: dict, key: str) -> str:
    return r["hazards"].get(key, {}).get("level", "unknown")


def _flood_relevant(r: dict) -> bool:
    return _lvl(r, "river_flood_100") == "high" or _lvl(r, "surface_runoff") in ("medium", "high")


def _building_line(b: dict, egid) -> str:
    parts = []
    flats = b.get("flats")
    cat = b.get("category")
    kind = "residential building" if cat in ("residential only", "residential with other use") \
        else (f"{cat} building" if cat else "building")
    if flats:
        parts.append(f"{flats}-flat {kind}" if flats > 1 else f"single-flat {kind}")
    elif cat:
        parts.append(cap_first(kind))
    if b.get("period_label"):
        parts.append(f"built {b['period_label'].replace('-', '–')}")
    if egid:
        parts.append(f"EGID {egid}")
    return " · ".join(parts) or "No building found in the federal building register"


def _drivers(r: dict) -> tuple[str, str]:
    """Main driver text for the physical and the transition box."""
    b = r["building"]
    src = b.get("energy_source")
    phys = [d for d in r["scores"].get("main_drivers", []) if not d.endswith(" heating")]
    if phys:
        p = "Main driver: " + ", ".join(phys)
    elif r["scores"].get("physical"):
        p = "No high or medium hazard"
    else:
        p = "Hazard data missing"
    if not src:
        t = "No heating entry in the register"
    else:
        t = f"Main driver: {src} heating"
        if (b.get("period_end_year") or 9999) < 1946:
            t += ", built before 1946"
    return p, t


def _talking_points(r: dict) -> list[str]:
    pts = []
    b, en = r["building"], r["energy"]
    src = b.get("energy_source")
    insurer = config.CANTONAL_BUILDING_INSURER.get(r.get("canton") or "")
    cover = (f"The cantonal building insurance ({insurer}) covers structural damage"
             if insurer else "The building insurance covers structural damage")
    if _lvl(r, "river_flood_100") == "high":
        pts.append("The building is in the 100-year river flood area (indicative federal map). "
                   f"{cover}; check contents insurance and basement use.")
    elif _lvl(r, "extreme_flood_300plus") == "high":
        pts.append("The building is outside the 100-year but inside the extreme (300-year+) flood "
                   "area: rare, but costly if it happens. Check basement use and contents insurance.")
    if _lvl(r, "surface_runoff") in ("medium", "high"):
        pts.append("The address is in a surface-runoff zone: check entrances, light wells and "
                   "basement protection against heavy rain.")
    mountain = [h for h in ("rockfall", "avalanche") if _lvl(r, h) == "high"]
    if mountain:
        pts.append(f"The address is in a federal {' and '.join(mountain)} hazard area. Check the "
                   "cantonal hazard map and any protective structures.")
    strong = [n for k, n in (("hail_50y", "hail"), ("storm_50y", "storm")) if _lvl(r, k) == "high"]
    if strong:
        pts.append(f"High {' and '.join(strong)} exposure: check the resistance of roof, "
                   "facade, blinds and solar panels.")
    if src in _FOSSIL:
        pts.append(f"The {src} heating will likely need replacing during the mortgage term. "
                   "A renovation tranche or green-mortgage rate can fund a heat pump.")
    if en.get("roof_class") in _GOOD_ROOF:
        pts.append(f"The roof is rated {en['roof_class']} for solar. Solar income and lower "
                   "energy costs improve affordability.")
    if _lvl(r, "river_flood_100") == "high" or mountain:
        pts.append("Check the binding cantonal hazard map and any local flood protection "
                   "before purchase.")
    if not pts:
        pts.append("No major climate or transition risk found in the federal data that could be "
                   "read; see the points to check above." if _data_gaps(r) else
                   "No major climate or transition risk found with the federal open data.")
    return pts


def _next_steps(r: dict) -> list[str]:
    b, en, c = r["building"], r["energy"], r["chf"]
    src = b.get("energy_source")
    old = (b.get("period_end_year") or 9999) <= 1980
    steps = []
    if src in _FOSSIL or (r["scores"].get("transition") or 0) >= 3 or (src and old):
        steps.append("Order a GEAK Plus energy report")
    quote = [x for x, ok in (("heat pump", src in _FOSSIL),
                             ("solar", en.get("roof_class") in _GOOD_ROOF)) if ok]
    if quote:
        steps.append(f"Get a {' and '.join(quote)} quote")
    if _flood_relevant(r):
        steps.append("Review flood protection with the building insurer")
    if any(_lvl(r, h) == "high" for h in ("rockfall", "avalanche")):
        steps.append("Check the cantonal hazard map and protective structures")
    if src in _FOSSIL or c.get("heat_pump_cost"):
        steps.append("Discuss a renovation tranche in the mortgage offer")
    if _data_gaps(r):
        steps.append("Fill the data gaps listed above (site visit, owner, cantonal maps)")
    if not steps:
        steps.append("No specific follow-up from the federal data; standard credit checks apply")
    return steps


def missing_building_fields(b: dict) -> list[str]:
    """Key register fields that are empty for a building that was found."""
    if not b:
        return []
    names = {"period_label": "year built", "floors": "floors", "energy_source": "heating"}
    return [n for k, n in names.items() if not b.get(k)]


def _data_gaps(r: dict) -> list[str]:
    """Everything the advisor must check by hand, so nothing passes silently."""
    gaps = [f"{h['label']}: no data" for h in r["hazards"].values() if h["level"] == "unknown"]
    if not r["building"]:
        gaps.append("Building not found in the federal building register: building, heating "
                    "and transition score are missing")
    elif missing_building_fields(r["building"]):
        gaps.append("Building register has no entry for "
                    + ", ".join(missing_building_fields(r["building"]))
                    + ": ask the owner or check the building documents")
    gaps += [str(w) for w in r["meta"].get("warnings") or []]
    gaps += [f"{k}: could not be loaded" for k in (r["meta"].get("errors") or {})]
    return gaps


def advisor_report(r: dict, client: str = "", advisor: str = "",
                   property_value: float | None = None, mortgage: float | None = None) -> str:
    s, c, b, en, meta = r["scores"], r["chf"], r["building"], r["energy"], r["meta"]
    src = b.get("energy_source")

    rows = "".join(
        f"<tr><td>{_e(h['label'])}</td><td>{_e(finding_text(k, h))}</td>"
        f"<td class='{h['level']}'>{_LEVEL_TEXT.get(h['level'], _e(h['level']))}</td></tr>"
        for k, h in r["hazards"].items())

    ltv, after = c["ltv_today_pct"], c["ltv_after_pct"]
    if ltv:
        ltv_big = f"{ltv:g}%" + (f" → {after[0]:g}–{after[1]:g}%" if after and after[1] != ltv else "")
        ltv_sub = "after flood-zone discount" if after and after[1] != ltv else "no flood-zone discount"
        if property_value and mortgage:
            ltv_sub += f" · {_chf(mortgage)} on {_chf(property_value)}"
    else:
        ltv_big, ltv_sub = "–", "enter property value and mortgage"
    p_drv, t_drv = _drivers(r)

    def score_txt(v, label):
        return f"{v} / 5 · {label}" if v else "– · No data"

    energy = [("Heating", cap_first(src) if src else "No entry in the register")]
    if en.get("heat_demand_kwh"):
        energy.append(("Heating demand", fmt_num(en["heat_demand_kwh"], "kWh/yr")))
    if c.get("co2_t_per_year"):
        energy.append(("CO₂ emissions (est.)", f"{c['co2_t_per_year']:g} t/yr"))
    if c.get("co2_levy_per_year"):
        energy.append(("CO₂ levy (est.)", f"CHF ~{fmt_num(c['co2_levy_per_year'])}/yr"))
    if en.get("roof_class"):
        roof = (f"Rooftop solar ({fmt_num(en['roof_area_m2'])} m²)" if en.get("roof_area_m2")
                else "Rooftop solar")
        energy.append((roof, f"{en['roof_class']}" + (f", {fmt_num(en['solar_kwh'], 'kWh/yr')}"
                                                      if en.get("solar_kwh") else "")))
    energy_rows = "".join(f"<tr><td>{_e(a)}</td><td class='num'>{_e(v)}</td></tr>" for a, v in energy)

    costs = []
    if c.get("heat_pump_cost"):
        costs.append(("Heat pump replacement", _rng(c["heat_pump_cost"])))
    if _flood_relevant(r):
        costs.append(("Flood protection (door barriers, basement)", "get a quote"))
    if c.get("value_discount") and any(c["value_discount"]):
        costs.append(("Value discount, flood zone (2–5%)", _rng(c["value_discount"])))
    if c.get("co2_levy_per_year"):
        costs.append(("CO₂ levy", f"{_chf(c['co2_levy_per_year'])}/yr"))
    if c.get("solar_income_per_year"):
        costs.append(("Solar income", f"+{_chf(c['solar_income_per_year'])}/yr"))
    cost_rows = "".join(f"<tr><td>{_e(a)}</td><td class='num'>{_e(v)}</td></tr>" for a, v in costs) \
        or "<tr><td colspan='2'>No cost items from the federal data.</td></tr>"

    fossil_note = ("<div class='note'>Fossil heating: when the boiler reaches end of life, cantonal "
                   "energy rules may require a renewable replacement. Plan for it in the financing."
                   "</div>") if src in _FOSSIL else ""

    trend = " · ".join(f"+{t['extra_warming_c']:g} °C: about +{t['heavy_rain_intensity_change_pct']:g}%"
                       for t in r.get("trend_50y") or [])
    trend_html = (f"<p class='muted' style='margin:6px 0 0'>Outlook, heavy-rain intensity if warming "
                  f"rises: {_e(trend)}. A simple rule, not a forecast for this address.</p>") \
        if trend else ""

    gaps = _data_gaps(r)
    example = meta.get("mode") == "example"
    check_items = (["Example mode: stored values from the group's manual query, not a live lookup"]
                   if example else []) + gaps
    check_html = ("<div class='check'><b>Please check before the talk</b><ul>"
                  + "".join(f"<li>{_e(g)}</li>" for g in check_items) + "</ul></div>") \
        if check_items else ""

    pts = "".join(f"<li>{_e(p)}</li>" for p in _talking_points(r))
    steps = "".join(f"<li>{_e(p)}</li>" for p in _next_steps(r))

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>HypoClimate advisor report · {_e(r['address'])}</title><style>{CSS}{ADVISOR_CSS}</style></head><body>
<button class="printbtn" onclick="window.print()">Print / save as PDF</button>
<div class="page"><div class="sheet">
<div class="head"><div>
<div class="kicker">HYPOCLIMATE · ADVISOR REPORT</div>
<h1>{_e(r['address'])}</h1>
<div class="muted">{_e(_building_line(b, r.get('egid')))}</div>
</div><div class="who">
Client: <b>{_e(client) if client else '&nbsp;'}</b><br>
Advisor: <b>{_e(advisor) if advisor else '&nbsp;'}</b><br>
Date: <b>{date.today():%d.%m.%Y}</b></div></div>
<div class="row" style="margin-top:12px">
 <div class="box"><div class="lbl">Physical risk</div>
  <div class="big">{_e(score_txt(s['physical'], s['physical_label']))}</div><div class="drv">{_e(p_drv)}</div></div>
 <div class="box"><div class="lbl">Transition risk</div>
  <div class="big">{_e(score_txt(s['transition'], s['transition_label']))}</div><div class="drv">{_e(t_drv)}</div></div>
 <div class="box"><div class="lbl">Loan-to-value</div>
  <div class="big">{_e(ltv_big)}</div><div class="drv">{_e(ltv_sub)}</div></div>
</div>
{check_html}
<h2>Natural hazards</h2><table><tr><th>Hazard</th><th>Finding</th><th>Level</th></tr>{rows}</table>
{trend_html}
<div class="row"><div style="flex:1"><h2>Energy efficiency</h2><table>{energy_rows}</table>{fossil_note}</div>
<div style="flex:1"><h2>Costs to plan for (estimates)</h2><table>{cost_rows}</table></div></div>
<h2>Talking points for the client</h2><ul class="pts">{pts}</ul>
<h2>Next steps</h2><ul class="steps">{steps}</ul>
<div class="foot">Data: swisstopo, FOEN (Aquaprotect, surface runoff, storm, SilvaProtect), MeteoSwiss
(hail), FSO building register, Swiss Federal Office of Energy (sonnendach.ch); open government data,
queried {_e(meta.get('queried_at'))}, assumptions {_e(meta.get('assumptions_version'))}.
Information, not advice. Federal flood maps are indicative; the cantonal hazard map is binding.
Cost figures are model estimates.</div>
</div></div>
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
