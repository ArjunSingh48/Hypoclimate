"""HypoClimate prototype (Streamlit).

Start (on your laptop, in the hypoclimate folder):  streamlit run frontend/app.py
Five screens: Address check · Advisor report · Bank portfolio · Method & data · Tests
"""
import io
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import config, disaster_test, engine, portfolio, report  # noqa: E402
from frontend import maps  # noqa: E402

st.set_page_config(page_title="HypoClimate", layout="wide")
st.title("HypoClimate")
st.caption("Climate risk of a Swiss address, in CHF, for mortgages. "
           "Built only on free, official Swiss open data.")

mode = st.sidebar.radio(
    "Data mode", ["live", "example"],
    help="live: queries the federal geodata API for any Swiss address (needs internet). "
         "example: works offline with two addresses the group queried by hand.")
st.sidebar.markdown("**Example-mode addresses**\n\n- Gerberngasse 20, 3011 Bern\n"
                    "- Zürichbergstrasse 221, Zürich")
st.sidebar.caption("The bank portfolio always offers an invented example book, "
                   "or your own CSV scored in the selected mode.")

tab_check, tab_report, tab_book, tab_method, tab_tests = st.tabs(
    ["Address check", "Advisor report", "Bank portfolio", "Method & data", "Tests"])



def chf(v):
    return "–" if v is None else f"CHF {v:,.0f}".replace(",", "'")


def chf_range(r):
    if not r:
        return "–"
    a, b = sorted(r, key=abs)
    return f"CHF {a:,.0f} to {b:,.0f}".replace(",", "'")


# Address-check helpers: how the hazards, building and location are shown (no calculations)
LEVEL_BADGE = {"high": ":red[**High**]", "medium": ":orange[**Medium**]",
               "low": ":green[**Low**]", "unknown": ":gray[No data]"}
LEVEL_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
HAZARD_SOURCE = {
    "river_flood_100": "FOEN Aquaprotect 100 · indicative",
    "extreme_flood_300plus": "FOEN Aquaprotect 500 · indicative",
    "surface_runoff": "FOEN surface runoff map",
    "hail_50y": "MeteoSwiss hail climatology",
    "storm_50y": "FOEN storm hazard map",
    "rockfall": "FOEN SilvaProtect-CH",
}
CATEGORY_TEXT = {"residential only": "Purely residential",
                 "residential with other use": "Residential with other use",
                 "partly residential": "Partly residential"}
HAZARD_TITLE = {"hail_50y": "Hail", "storm_50y": "Storm", "rockfall": "Rockfall & avalanche"}


def hazard_cards(hz: dict) -> list[dict]:
    """One card per hazard as in the mockup; rockfall and avalanche share one card."""
    cards = []
    for key, h in hz.items():
        if key == "avalanche":
            continue
        if key == "rockfall":
            pair = {"rockfall": h, "avalanche": hz["avalanche"]}
            level = max((x["level"] for x in pair.values()), key=LEVEL_ORDER.get)
            inside = [k for k, x in pair.items() if x["finding"] == "inside zone"]
            missing = [k for k, x in pair.items() if x["level"] == "unknown"]
            if inside:
                finding = f"Inside {' and '.join(inside)} hazard area"
            elif len(missing) == 2:
                finding = report.finding_text(key, h)
            else:
                finding = "Outside hazard areas" + (f" ({missing[0]}: no data)" if missing else "")
        else:
            level, finding = h["level"], report.finding_text(key, h)
        cards.append({"title": HAZARD_TITLE.get(key, h["label"]), "level": level,
                      "finding": finding, "source": HAZARD_SOURCE.get(key, h["source"])})
    return cards


def kv_grid(items: list[tuple], ncols: int = 2):
    """Label above value, in a grid (like the building box in the mockup)."""
    for i in range(0, len(items), ncols):
        for col, (label, val) in zip(st.columns(ncols), items[i:i + ncols]):
            col.caption(label)
            col.markdown(f"{val}")


def location_line(r: dict) -> str:
    parts = []
    if r.get("lv95"):
        parts.append(f"LV95 E {report.fmt_num(r['lv95']['e'])} · N {report.fmt_num(r['lv95']['n'])}")
    if r.get("egid"):
        parts.append(f"EGID {r['egid']}")
    if r.get("canton"):
        parts.append(f"canton {r['canton']}")
    return " · ".join(parts) + (" · " if parts else "") + "base map and hazard layers: swisstopo, FOEN, MeteoSwiss, SFOE"


# ---------------------------------------------------------------- Address check
with tab_check:
    c1, c2, c3 = st.columns([3, 1, 1])
    address = c1.text_input("Swiss address", "Gerberngasse 20, 3011 Bern")
    value = c2.number_input("Property value (CHF)", 0, step=50_000, value=1_250_000)
    mortgage = c3.number_input("Mortgage (CHF)", 0, step=50_000, value=800_000)

    if st.button("Check address", type="primary"):
        try:
            with st.spinner("Querying federal open data …"):
                st.session_state["result"] = engine.score(
                    address, value or None, mortgage or None, mode=mode)
                st.session_state["inputs"] = (value or None, mortgage or None)
        except Exception as exc:
            st.session_state.pop("result", None)
            st.session_state.pop("inputs", None)
            st.error(str(exc))

    r = st.session_state.get("result")
    if r:
        st.subheader(r["address"])
        s = r["scores"]
        m1, m2, m3 = st.columns(3)
        m1.metric("Physical risk", f"{s['physical'] or '–'} / 5")
        m1.caption(s["physical_label"])
        m2.metric("Transition risk", f"{s['transition'] or '–'} / 5")
        m2.caption(s["transition_label"])
        ltv, after = r["chf"]["ltv_today_pct"], r["chf"]["ltv_after_pct"]
        m3.metric("Loan-to-value", f"{ltv}%" if ltv else "–")
        if after and after[1] != ltv:
            m3.caption(f"{after[0]}–{after[1]}% after flood-zone discount")
        st.info(r["summary"])
        src = r["meta"].get("address_source")
        if src:
            st.caption(f"Address found via: {src}"
                       + (f" · {r['meta']['match_note']}" if r["meta"].get("match_note") else ""))
        if r["meta"]["mode"] == "example":
            st.caption("Example mode: stored values from the group's manual query, not a live lookup.")
        if r["meta"].get("warnings"):
            st.warning("Please check:\n\n" + "\n\n".join(f"- {w}" for w in r["meta"]["warnings"]))
        if r["meta"].get("errors"):
            st.warning("Some data could not be loaded (shown as 'No data'):\n\n" + "\n\n".join(
                f"- {k}: {v}" for k, v in r["meta"]["errors"].items()))

        left, right = st.columns([1.1, 1])
        with left:
            if r.get("wgs84"):
                st.markdown("**Map** (switch hazard layers on the right of the map)")
                st_folium(maps.address_map(r["wgs84"]["lat"], r["wgs84"]["lon"], r["address"]),
                          height=380, use_container_width=True, returned_objects=[])
                with st.expander("Map legend: what the colours mean"):
                    st.markdown(maps.legend_html(), unsafe_allow_html=True)
                    st.caption("Official legends from geo.admin.ch. Layers are shown at 60% opacity, "
                               "so colours on the map look lighter.")
            st.caption(location_line(r))
        with right:
            c = r["chf"]
            st.markdown("**What it means for the mortgage** (illustrative estimates)")
            st.dataframe(pd.DataFrame([
                {"Item": "Value discount, flood zone (2–5%)", "CHF": chf_range(c["value_discount"])},
                {"Item": f"CO₂ levy ({c['co2_t_per_year'] or '–'} t/yr)",
                 "CHF": chf(c["co2_levy_per_year"]) + (" / yr" if c["co2_levy_per_year"] else "")},
                {"Item": "Heat pump replacement", "CHF": chf_range(c["heat_pump_cost"])},
                {"Item": "Rooftop solar income",
                 "CHF": chf(c["solar_income_per_year"]) + (" / yr" if c["solar_income_per_year"] else "")},
            ]), hide_index=True, use_container_width=True)
            if r["hazards"]["river_flood_100"]["level"] == "high":
                gv = config.CANTONAL_BUILDING_INSURER.get(r.get("canton") or "")
                who = f"the cantonal building insurance ({gv})" if gv else "the building insurance"
                st.caption(f"Flood damage to the building is covered by {who}. "
                           "Contents, deductibles and downtime are not.")
            st.markdown("**Trend: heavy rain if warming rises**")
            st.dataframe(pd.DataFrame([
                {"Extra warming": f"+{t['extra_warming_c']:g} °C",
                 "Heavy-rain intensity": f"about +{t['heavy_rain_intensity_change_pct']:g}%"}
                for t in r["trend_50y"]]), hide_index=True, use_container_width=True)

        st.markdown("**Natural hazards at this address**")
        cards = hazard_cards(r["hazards"])
        for i in range(0, len(cards), 3):
            for col, card in zip(st.columns(3), cards[i:i + 3]):
                with col.container(border=True):
                    st.markdown(f"**{card['title']}** &nbsp; {LEVEL_BADGE[card['level']]}")
                    st.markdown(card["finding"])
                    st.caption(card["source"])

        b, en = r["building"], r["energy"]
        bcol, ecol = st.columns(2)
        with bcol.container(border=True):
            st.markdown("**The building** · federal building register (GWR)")
            if b:
                kv_grid([
                    ("Type", CATEGORY_TEXT.get(b.get("category"), report.cap_first(b.get("category")))),
                    ("Built", (b.get("period_label") or "–").replace("-", "–")),
                    ("Floors", b.get("floors") or "–"),
                    ("Flats", b.get("flats") or "–"),
                    ("Footprint", f"{b['footprint_m2']:,} m²".replace(",", "'")
                        if b.get("footprint_m2") else "–"),
                    ("Heating", report.cap_first(b.get("energy_source")) if b.get("energy_source")
                        else "No entry in the register"),
                    ("Building insurer", report.building_insurer(r.get("canton")) or "–"),
                ] + ([("Heated area", f"{b['energy_area_m2']:,} m²".replace(",", "'"))]
                     if b.get("energy_area_m2") else []))
                gap = report.missing_building_fields(b)
                if gap:
                    st.caption(f"The register has no entry for {', '.join(gap)}. This is common for "
                               "non-residential and some older buildings: ask the owner or check "
                               "the building documents.")
            else:
                st.caption("No building found in the federal building register for this address.")
        with ecol.container(border=True):
            st.markdown("**Energy and transition** · Swiss Federal Office of Energy")
            if en.get("roof_class") or en.get("heat_demand_kwh"):
                kv_grid([
                    ("Heating demand", report.fmt_num(en.get("heat_demand_kwh"), "kWh/yr")),
                    ("Hot water demand", report.fmt_num(en.get("hot_water_kwh"), "kWh/yr")),
                    ("Roof for solar", (f"{report.fmt_num(en['roof_area_m2'])} m², rated {en['roof_class']}"
                                        if en.get("roof_area_m2") else en.get("roof_class") or "–")),
                    ("Solar power yield", report.fmt_num(en.get("solar_kwh"), "kWh/yr")),
                ])
            else:
                st.caption("No solar roof or heat demand found for this building.")
            if b and not en.get("heat_demand_kwh"):
                st.caption("Heating demand is estimated only when the register records the "
                           "heating and the building size.")
            if b.get("energy_source") in ("oil", "gas"):
                st.warning("Fossil heating: when the boiler reaches end of life, cantonal energy "
                           "rules may require a renewable replacement. Plan for it in the financing.")

        st.info("The one-page report for the mortgage talk is ready in the **Advisor report** tab.")
        st.download_button("Download JSON (the format every screen uses)",
                           json.dumps({k: v for k, v in r.items()}, indent=2, ensure_ascii=False),
                           file_name="hypoclimate_result.json")
        st.caption(f"Mode: {r['meta']['mode']} · data as of {r['meta']['queried_at']} · "
                   f"assumptions {r['meta']['assumptions_version']} · {r['meta']['note']}")

# ---------------------------------------------------------------- Advisor report
with tab_report:
    r = st.session_state.get("result")
    if not r:
        st.info("Check an address in the **Address check** tab first. The one-page report for "
                "the mortgage talk then appears here.")
    else:
        pv, mg = st.session_state.get("inputs", (None, None))
        st.caption("One A4 page for the client talk: scores, hazards, energy, costs to plan for, "
                   "talking points and next steps. Every figure comes from the address check.")
        a1, a2 = st.columns(2)
        client = a1.text_input("Client name (optional)", key="report_client")
        advisor = a2.text_input("Advisor name (optional)", key="report_advisor")
        # the "Print / save as PDF" button sits inside the report and prints only the report
        components.html(report.advisor_report(r, client, advisor, pv, mg), height=1360,
                        scrolling=True)

# ---------------------------------------------------------------- Bank portfolio
with tab_book:
    src = st.radio("Mortgage book", ["Example book (invented loans)", "Upload CSV"],
                   horizontal=True)
    up = None
    if src == "Upload CSV":
        st.caption("CSV columns: loan_id (optional), address, property_value, mortgage. "
                   f"Scored in **{mode}** mode.")
        up = st.file_uploader("Mortgage book (CSV)", type="csv")
    if st.button("Score portfolio", type="primary"):
        with st.spinner("Scoring every loan …"):
            if src.startswith("Example"):
                book, is_example = portfolio.score_example_book(), True
            elif up is not None:
                rows = pd.read_csv(io.StringIO(up.getvalue().decode("utf-8")),
                                   dtype=str).fillna("").to_dict("records")
                book, is_example = portfolio.score_csv_rows(rows, mode), mode == "example"
            else:
                book = None
                st.error("Please upload a CSV first.")
        if book:
            st.session_state["book"] = (book, is_example)

    if "book" in st.session_state:
        book, is_example = st.session_state["book"]
        sm = portfolio.summarize(book)
        if is_example:
            st.warning("Example data: all loans and figures on this screen are invented for the demo.")
        st.caption(f"{sm['scored']} of {sm['loans']} loans scored ({sm['coverage_pct']}%) · "
                   f"exposure {chf(sm['exposure_chf'])}"
                   + (f" · avg {sm['avg_seconds']} s per address" if sm["avg_seconds"] else ""))
        k = sm["kpis"]
        cols = st.columns(4)
        for col, (key, title) in zip(cols, [("flood_100", "In river flood area (100-yr)"),
                                            ("runoff", "In surface-runoff zone"),
                                            ("fossil", "Oil or gas heating"),
                                            ("high_overall", "High overall risk")]):
            col.metric(title, f"{k[key]['pct']}%")
            col.caption(f"{k[key]['loans']} loans · {chf(k[key]['chf'])}")

        left, right = st.columns([1.1, 1])
        with left:
            pts = [{"lat": b["result"]["wgs84"]["lat"], "lon": b["result"]["wgs84"]["lon"],
                    "label": f"{b['loan_id']} · physical {b['result']['scores']['physical']}",
                    "physical": b["result"]["scores"]["physical"]}
                   for b in book if b["status"] == "ok" and b["result"].get("wgs84")]
            if pts:
                st.markdown("**Where the risk sits** (colour = physical risk)")
                st_folium(maps.portfolio_map(pts), height=380, use_container_width=True,
                          returned_objects=[])
        with right:
            st.markdown("**Share of loans by hazard level (%)**")
            lv = pd.DataFrame(sm["hazard_levels"]).T[["low", "medium", "high"]]
            st.bar_chart(lv, color=["#2e7d32", "#ef6c00", "#c62828"], horizontal=True, height=220)
            st.markdown("**Heating systems in the book (%)**")
            st.bar_chart(pd.Series(sm["heating_mix"], name="% of loans"), horizontal=True,
                         height=220)

        st.markdown("**Highest-risk loans**")
        st.dataframe(pd.DataFrame(sm["top_risk"]), hide_index=True, use_container_width=True)
        flat = [{"loan_id": b["loan_id"], "status": b["status"],
                 "address": b["result"]["address"] if b["result"] else b.get("address"),
                 "physical": b["result"]["scores"]["physical"] if b["result"] else None,
                 "transition": b["result"]["scores"]["transition"] if b["result"] else None,
                 "exposure_chf": b["exposure"], "error": b.get("error", "")} for b in book]
        d1, d2 = st.columns(2)
        d1.download_button("Export portfolio report (print to PDF)",
                           report.portfolio_report(sm, is_example),
                           file_name="hypoclimate_portfolio_report.html", mime="text/html")
        d2.download_button("Export scored loans (CSV)", pd.DataFrame(flat).to_csv(index=False),
                           file_name="hypoclimate_scored_loans.csv")

# ---------------------------------------------------------------- Method & data
with tab_method:
    st.markdown("**How every score is made**: locate the address → read hazard layers → "
                "read the building register → score → translate to CHF → explain.")
    st.markdown("**Data sources** (open government data, geo.admin.ch)")
    st.dataframe(pd.DataFrame(
        [{"Data": config.HAZARD_LABELS[k], "Layer": v} for k, v in config.HAZARD_LAYERS.items()]
        + [{"Data": "Federal building register", "Layer": config.BUILDING_LAYER},
           {"Data": "Solar roofs and heat demand", "Layer": config.SOLAR_LAYER}]),
        hide_index=True, use_container_width=True)
    st.markdown(f"**Assumptions** (all in config.py, version {config.ASSUMPTIONS_VERSION})")
    st.dataframe(pd.DataFrame([
        {"Assumption": "Value discount in 100-year flood area", "Value": "2–5%"},
        {"Assumption": "CO₂ factor, natural gas / heating oil", "Value": "0.198 / 0.265 kg/kWh"},
        {"Assumption": "CO₂ levy on heating fuels", "Value": "CHF 120/t"},
        {"Assumption": "Heat pump cost per flat", "Value": "CHF 12'000–18'000"},
        {"Assumption": "Solar income", "Value": "CHF 0.10/kWh"},
        {"Assumption": "Heavy-rain intensity per °C warming", "Value": "about +7%"},
        {"Assumption": "Hail levels (50-yr stone size)", "Value": "< 3 cm low, 3–5 cm medium, ≥ 5 cm high"},
        {"Assumption": "Storm levels (50-yr gusts)", "Value": "< 100 low, 100–140 medium, ≥ 140 km/h high"},
        {"Assumption": "Physical score", "Value": "worst hazard (low 1, medium 3, high 4), +1 if two perils high"},
        {"Assumption": "Transition score", "Value": "oil 4, gas 3, electric 3, wood 2, district 2, "
                                                    "heat pump 1; +1 if built before 1946"},
        {"Assumption": "High overall risk (portfolio)", "Value": "physical ≥ 4 and transition ≥ 3"},
    ]), hide_index=True, use_container_width=True)
    st.caption("Limits: federal flood maps are indicative and ignore flood protection; the runoff "
               "layer shows only 'in zone or not'; property value is entered by the user; the "
               "50-year trend is a simple rule, not yet the CH2025 dataset. Information, not advice.")

# ---------------------------------------------------------------- Tests
with tab_tests:
    st.markdown("**Disaster test**: does HypoClimate flag places where real disasters happened? "
                "Edit `data/disaster_tests.csv` to add addresses (e.g. Misox/Valais 2024, Blatten 2025).")
    if st.button("Run disaster test", type="primary"):
        rows = pd.read_csv(ROOT / "data" / "disaster_tests.csv", dtype=str).fillna("").to_dict("records")
        with st.spinner("Running …"):
            res = disaster_test.run(rows, mode)
        passed = sum(x["result"] == "PASS" for x in res)
        st.metric("Passed", f"{passed} of {len(res)}")
        st.dataframe(pd.DataFrame(res), hide_index=True, use_container_width=True)
