"""Address matching: the right result must win even when it is not the first one.

The search service is replaced by a fake that returns several candidates in a bad
order, so these tests prove the matching logic, not any stored answer.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import engine, geoadmin  # noqa: E402


def cand(label, detail, egid, e=2600000.0, n=1200000.0):
    return {"label": label, "detail": detail, "featureId": f"{egid}_0", "y": e, "x": n}


def test_parse_address():
    assert geoadmin.parse_address("Uetlibergstrasse 111b") == {"street": "uetlibergstrasse", "number": "111b", "postcode": None}
    assert geoadmin.parse_address("Bielstrasse 3, 4500 Solothurn")["postcode"] == "4500"
    assert geoadmin.parse_address("Buschberghof 261, 5064 Wittnau")["number"] == "261"
    assert geoadmin.parse_address("Clausiusstrasse 16 8006 Zürich") == {"street": "clausiusstrasse", "number": "16", "postcode": "8006"}
    assert geoadmin.parse_address("Uetlibergstrasse 111b 8045 Zürich")["number"] == "111b"
    assert geoadmin.parse_address("Sihlmatten 7 8134 adliswil")["postcode"] == "8134"


def test_best_candidate_wins_not_first(monkeypatch):
    results = [
        cand("Uetlibergstrasse 111 <b>8045 Zürich</b>", "uetlibergstrasse 111 8045 zuerich", 1),
        cand("Uetlibergstrasse 111a <b>8045 Zürich</b>", "uetlibergstrasse 111a 8045 zuerich", 2),
        cand("Uetlibergstrasse 111b <b>8045 Zürich</b>", "uetlibergstrasse 111b 8045 zuerich", 3),
    ]
    monkeypatch.setattr(geoadmin, "search_candidates", lambda a, limit=8: results)
    loc = geoadmin.geocode("Uetlibergstrasse 111b")
    assert loc["egid"] == 3 and loc["match_note"] == "exact house number"


def test_postcode_decides_between_towns(monkeypatch):
    results = [
        cand("Rohrerstrasse 7 <b>5033 Buchs AG</b>", "rohrerstrasse 7 5033 buchs ag", 10),
        cand("Rohrerstrasse 7 <b>5000 Aarau</b>", "rohrerstrasse 7 5000 aarau", 11),
    ]
    monkeypatch.setattr(geoadmin, "search_candidates", lambda a, limit=8: results)
    assert geoadmin.geocode("Rohrerstrasse 7, 5000 Aarau")["egid"] == 11


def test_spelling_variant_is_tried(monkeypatch):
    calls = []

    def fake(a, limit=8):
        calls.append(a)
        if "Sankt-Leodegar" in a or "Leodegar-Strasse" in a:
            return [cand("St. Leodegar-Strasse 6 <b>6006 Luzern</b>",
                         "st leodegar strasse 6 6006 luzern", 20)]
        return []
    monkeypatch.setattr(geoadmin, "search_candidates", fake)
    loc = geoadmin.geocode("St. Leodegarstrasse 6, 6006 Luzern")
    assert loc["egid"] == 20 and len(calls) > 1


def test_missing_house_number_is_reported(monkeypatch):
    monkeypatch.setattr(geoadmin, "search_candidates", lambda a, limit=8: [
        cand("Gloriastrasse 30 <b>8006 Zürich</b>", "gloriastrasse 30 8006 zuerich", 30)])
    loc = geoadmin.geocode("Gloriastrasse 32, 8006 Zürich")
    assert "not found exactly" in loc["match_note"]


def test_openstreetmap_fallback(monkeypatch):
    monkeypatch.setattr(geoadmin, "search_candidates", lambda a, limit=8: [])

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"lat": "46.9478", "lon": "7.4571", "display_name": "Somewhere, Bern"}]
    monkeypatch.setattr(geoadmin._session, "get", lambda *a, **k: R())
    loc = geoadmin.geocode("Nowhere-in-index 1, 3000 Bern")
    assert loc["source"] == "OpenStreetMap Nominatim" and loc["egid"] is None
    assert 2600000 < loc["e"] < 2602000 and 1198000 < loc["n"] < 1201000


def test_coordinate_round_trip():
    lat, lon = geoadmin.lv95_to_wgs84(2682407, 1239689)
    e, n = geoadmin.wgs84_to_lv95(lat, lon)
    assert abs(e - 2682407) < 2 and abs(n - 1239689) < 2


def test_building_found_at_point_when_search_gives_no_id(monkeypatch):
    monkeypatch.setattr(geoadmin, "geocode", lambda a: {
        "label": "X 5", "e": 2600000.0, "n": 1200000.0, "egid": None, "feature_id": None,
        "source": "OpenStreetMap Nominatim", "match_note": "location from OpenStreetMap"})
    monkeypatch.setattr(geoadmin, "wms_feature_info", lambda e, n, layer: [])
    monkeypatch.setattr(geoadmin, "identify", lambda e, n, layers, tolerance_px=0: [
        {"attributes": {"egid": 555, "deinr": "5", "gbauj": 1985, "genh1": 7501, "ganzwhg": 3}}]
        if layers == ["ch.bfs.gebaeude_wohnungs_register"] else [])
    monkeypatch.setattr(geoadmin, "solar_by_egid", lambda egid: [])
    monkeypatch.setattr(geoadmin, "solar", lambda e, n, tolerance_px=0: [])
    r = engine.score("X 5, 3000 Bern", mode="live")
    assert r["egid"] == 555 and r["building"]["energy_source"] == "heat pump"
    assert r["scores"]["transition"] == 1
    assert any("OpenStreetMap" in w for w in r["meta"]["warnings"])


def test_plausibility_catches_wrong_numbers(monkeypatch):
    monkeypatch.setattr(geoadmin, "geocode", lambda a: {
        "label": "Y 1", "e": 2600000.0, "n": 1200000.0, "egid": 9, "feature_id": "9_0",
        "source": "geo.admin.ch address search", "match_note": "exact house number"})
    monkeypatch.setattr(geoadmin, "wms_feature_info", lambda e, n, layer: [])
    monkeypatch.setattr(geoadmin, "identify", lambda e, n, layers, tolerance_px=0: [
        {"attributes": {"boenspitzen_kmh_50": "10779"}}]
        if layers == ["ch.bafu.sturm-boeenspitzen_50"] else [])
    monkeypatch.setattr(geoadmin, "building", lambda fid: {"gbauj": 1970, "ganzwhg": 2, "genh1": 7530,
                                                            "gkat": 1020})
    monkeypatch.setattr(geoadmin, "solar_by_egid", lambda egid: [
        {"attributes": {"gwr_egid": 9, "klasse": 3, "flaeche": 50, "stromertrag": 8000,
                        "bedarf_heizung": 200000}}])
    w = engine.score("Y 1", mode="live")["meta"]["warnings"]
    assert any("storm value" in x for x in w)
    assert any("heat demand" in x for x in w)


def test_live_check_tool_runs(monkeypatch, tmp_path):
    """The live-check tool must run end to end and save its report (network faked)."""
    from backend import live_check
    monkeypatch.setattr(geoadmin, "search_candidates", lambda a, limit=8: [
        cand("Bielstrasse 3 <b>4500 Solothurn</b>", "bielstrasse 3 4500 solothurn", 77)])
    monkeypatch.setattr(geoadmin, "wms_feature_info", lambda e, n, layer: [])
    monkeypatch.setattr(geoadmin, "identify", lambda e, n, layers, tolerance_px=0: [
        {"attributes": {"boenspitzen_kmh_50": "125 ± 20 km/h"}}]
        if layers == ["ch.bafu.sturm-boeenspitzen_50"] else [])
    monkeypatch.setattr(geoadmin, "building", lambda fid: {"gbauj": 1912, "ganzwhg": 4, "genh1": 7520})
    monkeypatch.setattr(geoadmin, "solar_by_egid", lambda egid: [])
    monkeypatch.setattr(geoadmin, "solar", lambda e, n, tolerance_px=0: [])
    csv_file = tmp_path / "a.csv"
    csv_file.write_text("address\n\"Bielstrasse 3, 4500 Solothurn\"\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["live_check", str(csv_file)])
    live_check.main()
    saved = list((tmp_path / "data" / "live_runs").glob("run_*.json"))
    assert len(saved) == 1
    import json
    run = json.loads(saved[0].read_text(encoding="utf-8"))[0]
    assert run["status"] == "ok" and run["result"]["egid"] == 77
    assert run["result"]["hazards"]["storm_50y"]["finding"] == "125 km/h"
