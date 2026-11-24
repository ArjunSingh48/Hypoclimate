"""HypoClimate prototype (Streamlit).

Start (on your laptop, in the hypoclimate folder):  streamlit run frontend/app.py
Four screens: Address check · Bank portfolio · Method & data · Tests
"""
import io
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
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

tab_check, tab_book, tab_method, tab_tests = st.tabs(
    ["Address check", "Bank portfolio", "Method & data", "Tests"])

LEVEL_ICON = {"high": "🔴 High", "medium": "🟠 Medium", "low": "🟢 Low", "unknown": "⚪ No data"}


def chf(v):
    return "–" if v is None else f"CHF {v:,.0f}".replace(",", "'")


def chf_range(r):
    if not r:
        return "–"
    a, b = sorted(r, key=abs)
    return f"CHF {a:,.0f} to {b:,.0f}".replace(",", "'")


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
        except Exception as exc:
            st.session_state.pop("result", None)
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
        if r["meta"].get("errors"):
            st.warning("Some data could not be loaded (shown as 'No data'):\n\n" + "\n\n".join(
                f"- {k}: {v}" for k, v in r["meta"]["errors"].items()))

        left, right = st.columns([1.1, 1])
        with left:
            if r.get("wgs84"):
                st.markdown("**Map** (switch hazard layers on the right of the map)")
                st_folium(maps.address_map(r["wgs84"]["lat"], r["wgs84"]["lon"], r["address"]),
                          height=380, use_container_width=True, returned_objects=[])
            st.markdown("**Natural hazards at this address**")
            st.dataframe(pd.DataFrame([
                {"Hazard": h["label"], "Level": LEVEL_ICON[h["level"]],
                 "Finding": h["finding"], "Source layer": h["source"]}
                for h in r["hazards"].values()]), hide_index=True, use_container_width=True)
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
            b, en = r["building"], r["energy"]
            st.markdown("**Building and energy**")
            st.dataframe(pd.DataFrame([
                {"Item": "Built", "Value": b.get("period_label") or "–"},
                {"Item": "Floors / flats", "Value": f"{b.get('floors') or '–'} / {b.get('flats') or '–'}"},
                {"Item": "Heating", "Value": b.get("energy_source") or "–"},
                {"Item": "Heating demand", "Value": f"{en['heat_demand_kwh']:,.0f} kWh/yr"
                    if en.get("heat_demand_kwh") else "–"},
                {"Item": "Best roof for solar", "Value": f"{en['roof_area_m2']:g} m², {en['roof_class']}"
                    if en.get("roof_area_m2") else (en.get("roof_class") or "–")},
                {"Item": "Solar yield", "Value": f"{en['solar_kwh']:,.0f} kWh/yr"
                    if en.get("solar_kwh") else "–"},
            ]).astype(str), hide_index=True, use_container_width=True)
            st.markdown("**Trend: heavy rain if warming rises**")
            st.dataframe(pd.DataFrame([
                {"Extra warming": f"+{t['extra_warming_c']:g} °C",
                 "Heavy-rain intensity": f"about +{t['heavy_rain_intensity_change_pct']:g}%"}
                for t in r["trend_50y"]]), hide_index=True, use_container_width=True)

        st.markdown("**Advisor report**")
        a1, a2, a3 = st.columns([1, 1, 1])
        client = a1.text_input("Client name (optional)")
        advisor = a2.text_input("Advisor name (optional)")
        a3.download_button("Download advisor report (print to PDF)",
                           report.advisor_report(r, client, advisor),
                           file_name="hypoclimate_advisor_report.html", mime="text/html")
        st.download_button("Download JSON (the format every screen uses)",
                           json.dumps({k: v for k, v in r.items()}, indent=2, ensure_ascii=False),
                           file_name="hypoclimate_result.json")
        st.caption(f"Mode: {r['meta']['mode']} · data as of {r['meta']['queried_at']} · "
                   f"assumptions {r['meta']['assumptions_version']} · {r['meta']['note']}")

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
