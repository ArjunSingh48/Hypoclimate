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


def test_coordinates_bern():
    from backend import geoadmin as g
    lat, lon = g.lv95_to_wgs84(2601406, 1199640)
    assert 46.94 < lat < 46.96 and 7.44 < lon < 7.47


# Real answers recorded from geo.admin.ch on 24.11.2026 (Gerberngasse 20, Bern / Sihlmatten 7, Adliswil)
WMS_FLOOD_INSIDE = "GetFeatureInfo results:\n\nLayer 'ch.bafu.aquaprotect_100'\n  Feature 1603: \n"
WMS_NO_RESULT = "GetFeatureInfo results:\n\n  Search returned no results.\n"
WMS_HAIL_4CM = ("GetFeatureInfo results:\n\nLayer 'ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre'\n"
                "  Feature 0: \n    ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre.value_0.name = '4'\n")
STORM_130 = {"layerBodId": "ch.bafu.sturm-boeenspitzen_50", "featureId": 10779, "id": 10779,
             "attributes": {"boenspitzen_kmh_30": "121 ± 20 km/h", "boenspitzen_ms_30": "34 ± 6 m/s",
                            "boenspitzen_kmh_50": "130 ± 21 km/h", "boenspitzen_ms_50": "36 ± 6 m/s",
                            "label": 10779}}


def test_parse_real_wms_answers():
    assert geoadmin.parse_feature_info(WMS_FLOOD_INSIDE, "ch.bafu.aquaprotect_100") == [{}]
    assert geoadmin.parse_feature_info(WMS_NO_RESULT, "ch.bafu.silvaprotect-sturz") == []
    hail = geoadmin.parse_feature_info(WMS_HAIL_4CM, "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre")
    assert hail == [{"value_0.name": "4"}]


def _fake_live(monkeypatch, wms_answers, fail=()):
    import requests
    monkeypatch.setattr(geoadmin, "geocode", lambda a: {
        "label": "Gerberngasse 20 3011 Bern", "e": 2601406.0, "n": 1199640.0,
        "egid": 1230068, "feature_id": "1230068_0"})

    def fake_wms(e, n, layer):
        if layer in fail:
            raise requests.HTTPError("502 Server Error")
        return geoadmin.parse_feature_info(wms_answers.get(layer, WMS_NO_RESULT), layer)
    monkeypatch.setattr(geoadmin, "wms_feature_info", fake_wms)
    monkeypatch.setattr(geoadmin, "identify", lambda e, n, layers, tolerance_px=0:
                        [STORM_130] if layers == ["ch.bafu.sturm-boeenspitzen_50"] else [])
    monkeypatch.setattr(geoadmin, "building", lambda fid: {
        "gbaup": 8013, "gastw": 4, "ganzwhg": 5, "garea": 173, "genh1": 7520})
    monkeypatch.setattr(geoadmin, "solar_by_egid", lambda egid: [
        {"attributes": {"gwr_egid": 1230068, "klasse": 4, "flaeche": 75, "stromertrag": 15100,
                        "bedarf_heizung": 59300, "bedarf_warmwasser": 9500}}])


def test_live_bern_with_real_answers(monkeypatch):
    _fake_live(monkeypatch, {"ch.bafu.aquaprotect_100": WMS_FLOOD_INSIDE,
                             "ch.bafu.aquaprotect_500": WMS_FLOOD_INSIDE.replace("_100", "_500"),
                             "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre": WMS_HAIL_4CM})
    r = engine.score("Gerberngasse 20, 3011 Bern", 1_250_000, 800_000, mode="live")
    h = r["hazards"]
    assert h["river_flood_100"]["level"] == "high"
    assert h["extreme_flood_300plus"]["level"] == "high"
    assert h["surface_runoff"]["level"] == "low"
    assert h["hail_50y"]["level"] == "medium" and h["hail_50y"]["finding"] == "4 cm"
    assert h["storm_50y"]["level"] == "medium" and h["storm_50y"]["finding"] == "130 km/h"
    assert h["rockfall"]["level"] == "low" and h["avalanche"]["level"] == "low"
    assert r["scores"]["physical"] == 4 and r["scores"]["transition"] == 3
    assert r["meta"]["errors"] == {}


def test_one_failing_layer_does_not_break_the_rest(monkeypatch):
    _fake_live(monkeypatch, {"ch.bafu.aquaprotect_100": WMS_FLOOD_INSIDE},
               fail=("ch.bafu.silvaprotect-sturz",))
    r = engine.score("Gerberngasse 20, 3011 Bern", 1_250_000, 800_000, mode="live")
    assert r["hazards"]["rockfall"]["level"] == "unknown"
    assert r["hazards"]["river_flood_100"]["level"] == "high"
    assert set(r["meta"]["errors"]) == {"ch.bafu.silvaprotect-sturz"}
