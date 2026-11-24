import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import engine  # noqa: E402
from backend import geoadmin  # noqa: E402

BERN = "Gerberngasse 20, 3011 Bern"


def test_bern_matches_group_mockup():
    r = engine.score(BERN, 1_250_000, 800_000, mode="example")
    s, c = r["scores"], r["chf"]
    assert s["physical"] == 4 and s["transition"] == 3
    assert r["hazards"]["river_flood_100"]["level"] == "high"
    assert r["hazards"]["hail_50y"]["level"] == "medium"
    assert r["hazards"]["storm_50y"]["level"] == "medium"
    assert c["value_discount"] == [-25000, -62500]
    assert c["ltv_today_pct"] == 64.0
    assert c["ltv_after_pct"] == [65.3, 67.4]
    assert c["co2_t_per_year"] == 11.7 and c["co2_levy_per_year"] == 1409
    assert c["heat_pump_cost"] == [60000, 90000]
    assert c["solar_income_per_year"] == 1510
    assert s["main_drivers"] == ["river flood", "gas heating"]


def test_clean_address_and_missing_data():
    r = engine.score("Zürichbergstrasse 221", mode="example")
    assert r["scores"]["physical"] == 1
    assert r["scores"]["transition"] is None
    assert r["hazards"]["hail_50y"]["level"] == "unknown"
    assert r["chf"]["value_discount"] is None


def test_live_parsing_with_mocked_api(monkeypatch):
    monkeypatch.setattr(geoadmin, "geocode", lambda a: {
        "label": "Teststrasse 1, 3000 Bern", "e": 2600000.0, "n": 1200000.0,
        "egid": 111, "feature_id": "111_0"})
    hits = [
        {"layerBodId": "ch.bafu.aquaprotect_100", "attributes": {}},
        {"layerBodId": "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre",
         "attributes": {"label": "5.5 cm"}},
        {"layerBodId": "ch.bafu.sturm-boeenspitzen_50", "attributes": {"wert": 150}},
    ]
    monkeypatch.setattr(geoadmin, "identify", lambda e, n, layers, tolerance_px=0: [
        h for h in hits if h["layerBodId"] in layers])
    monkeypatch.setattr(geoadmin, "building", lambda fid: {
        "gbaup": 8012, "gastw": 3, "ganzwhg": 2, "garea": 120, "genh1": 7530})
    monkeypatch.setattr(geoadmin, "solar", lambda e, n: [
        {"attributes": {"gwr_egid": 111, "klasse": 3, "flaeche": 40, "stromertrag": 6000,
                        "bedarf_heizung": 30000, "bedarf_warmwasser": 4000}},
        {"attributes": {"gwr_egid": 111, "klasse": 5, "flaeche": 50, "stromertrag": 9000}}])
    r = engine.score("Teststrasse 1", 1_000_000, 700_000, mode="live")
    assert r["hazards"]["hail_50y"]["level"] == "high"
    assert r["hazards"]["storm_50y"]["level"] == "high"
    assert r["scores"]["physical"] == 5          # flood + hail + storm high
    assert r["building"]["energy_source"] == "oil"
    assert r["scores"]["transition"] == 5        # oil 4 + built before 1946
    assert r["energy"]["roof_class"] == "excellent" and r["energy"]["solar_kwh"] == 9000
    assert r["chf"]["co2_levy_per_year"] == round(30000 * 0.265 / 1000 * 120)


def test_one_bad_layer_does_not_break_the_rest(monkeypatch):
    import requests
    monkeypatch.setattr(geoadmin, "geocode", lambda a: {
        "label": "Sihlmatten 7, 8134 Adliswil", "e": 2682407.25, "n": 1239689.125,
        "egid": 222, "feature_id": "222_0"})

    def fake_identify(e, n, layers, tolerance_px=0):
        if layers == ["ch.bafu.aquaprotect_500"]:
            raise requests.HTTPError("400 Client Error: Bad Request")
        if layers == ["ch.bafu.aquaprotect_100"]:
            return [{"layerBodId": layers[0], "attributes": {}}]
        return []
    monkeypatch.setattr(geoadmin, "identify", fake_identify)
    monkeypatch.setattr(geoadmin, "building", lambda fid: {"gbaup": 8019, "genh1": 7520, "ganzwhg": 6})
    monkeypatch.setattr(geoadmin, "solar", lambda e, n: (_ for _ in ()).throw(requests.HTTPError("500")))
    r = engine.score("Sihlmatten 7, 8134 Adliswil", 2_000_000, 800_000, mode="live")
    assert r["hazards"]["extreme_flood_300plus"]["level"] == "unknown"
    assert r["hazards"]["river_flood_100"]["level"] == "high"
    assert set(r["meta"]["errors"]) == {"ch.bafu.aquaprotect_500", "solar roofs"}
    assert r["building"]["energy_source"] == "gas"


def test_coordinates_bern():
    from backend import geoadmin as g
    lat, lon = g.lv95_to_wgs84(2601406, 1199640)
    assert 46.94 < lat < 46.96 and 7.44 < lon < 7.47
