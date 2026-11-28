import html

from backend import engine, report

BERN = "Gerberngasse 20, 3011 Bern"
ZURICH = "Zürichbergstrasse 221, Zürich"


def _bern(**kw):
    r = engine.score(BERN, 1_250_000, 800_000, mode="example")
    return r, report.advisor_report(r, **kw)


def test_advisor_report():
    _, adv = _bern(client="Client A", advisor="Advisor B")
    assert "Gerberngasse 20" in adv and "100-year river flood area" in adv
    assert "Information, not advice" in adv
    assert "Client A" in adv and "Advisor B" in adv


def test_advisor_report_matches_mockup():
    """The Bern example shows the same content as the advisor-report mockup."""
    _, adv = _bern(property_value=1_250_000, mortgage=800_000)
    adv = html.unescape(adv)
    assert "5-flat residential building · built 1946–1960 · EGID 1230068" in adv
    assert "Main driver: river flood" in adv and "Main driver: gas heating" in adv
    assert "64% → 65.3–67.4%" in adv and "CHF 800'000 on CHF 1'250'000" in adv
    assert "Inside flood area (indicative federal map)" in adv
    assert "59'300 kWh/yr" in adv and "CHF 60'000 to 90'000" in adv
    assert "Flood protection (door barriers, basement)" in adv
    for step in ("Order a GEAK Plus energy report", "Get a heat pump and solar quote",
                 "Review flood protection with the building insurer",
                 "Discuss a renovation tranche in the mortgage offer"):
        assert step in adv
    assert "Check the binding cantonal hazard map" in adv
    assert "Fossil heating" in adv


def test_advisor_report_names_data_gaps():
    """Missing data is listed for the advisor, never hidden behind 'no risk'."""
    r = engine.score(ZURICH, 900_000, 600_000, mode="example")
    adv = report.advisor_report(r)
    assert "Please check before the talk" in adv
    assert "Hail, 50-year: no data" in adv and "Building not found" in adv
    assert "– · No data" in adv
    assert "Fill the data gaps" in adv
    assert "Heat pump replacement" not in adv and "Flood protection" not in adv
    assert "Get a heat pump" not in adv


def test_advisor_report_escapes_user_input():
    _, adv = _bern(client="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in adv
    assert "&lt;script&gt;" in adv


def test_talking_points_and_steps_follow_the_data():
    r, _ = _bern()
    r["hazards"]["river_flood_100"]["level"] = "low"
    r["hazards"]["extreme_flood_300plus"]["level"] = "low"
    r["building"]["energy_source"] = "heat pump"
    r["chf"]["heat_pump_cost"] = None
    pts, steps = report._talking_points(r), report._next_steps(r)
    assert not any("flood" in p for p in pts)
    assert not any("heat pump quote" in s or "renovation tranche" in s for s in steps)
    assert "Get a solar quote" in steps


def test_building_insurer_by_canton():
    assert report.building_insurer("BE") == "GVB (cantonal, BE)"
    assert report.building_insurer("VS").startswith("Private insurer")
    assert report.building_insurer(None) is None
    _, adv = _bern()
    assert "cantonal building insurance (GVB)" in adv


def test_missing_register_fields_are_flagged():
    r, _ = _bern()
    for k in ("period_label", "floors", "energy_source"):
        r["building"][k] = None
    r["energy"]["roof_area_m2"] = 58.0776
    adv = html.unescape(report.advisor_report(r))
    assert "no entry for year built, floors, heating" in adv
    assert "(58 m²)" in adv
