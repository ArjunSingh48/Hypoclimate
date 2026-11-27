"""The 8 test addresses, replayed with the real answers the federal services gave on 26.11.2026.

tests/fixtures/geoadmin_2026-11-26.json holds what geo.admin.ch actually returned
(address search, building register, solar register, storm layer, WMS hazard layers).
The fakes below only hand those answers back; all matching, reading and scoring is the
real code. If a service changes its answers, run `python3 -m backend.live_check` again.
"""
import json
import os

import pytest

from backend import engine, geoadmin

FIX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "geoadmin_2026-11-26.json"),
                     encoding="utf-8"))

# address point (rounded LV95) -> EGID, taken from the recorded search results
POINT = {}
for cands in FIX["search"].values():
    for c in cands:
        POINT[(round(c["y"]), round(c["x"]))] = c["featureId"].split("_")[0]

WMS_LAYERS = {"ch.bafu.aquaprotect_100", "ch.bafu.aquaprotect_500",
              "ch.bafu.gefaehrdungskarte-oberflaechenabfluss", "ch.bafu.silvaprotect-sturz",
              "ch.bafu.silvaprotect-lawinen"}
HAIL = "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre"


def _wms_text(egid, layer):
    rec = FIX["wms"][egid]
    if layer == HAIL:
        return (f"GetFeatureInfo results:\n\nLayer '{HAIL}'\n  Feature 0: \n"
                f"    {HAIL}.value_0.name = '{rec['hail']}'\n")
    if layer in rec:
        return f"GetFeatureInfo results:\n\nLayer '{layer}'\n  {rec[layer]}: \n"
    return "GetFeatureInfo results:\n\n  Search returned no results.\n"


@pytest.fixture
def recorded(monkeypatch):
    asked = []

    def search(address, limit=8):
        asked.append(address)
        return FIX["search"].get(address, [])

    def egid_at(e, n):
        return POINT[(round(e), round(n))]

    def identify(e, n, layers, tolerance_px=0):
        assert layers == ["ch.bafu.sturm-boeenspitzen_50"], layers
        return [{"attributes": {"boenspitzen_kmh_50": FIX["storm_kmh_50"][egid_at(e, n)]}}]

    monkeypatch.setattr(geoadmin, "search_candidates", search)
    monkeypatch.setattr(geoadmin, "identify", identify)
    monkeypatch.setattr(geoadmin, "wms_feature_info", lambda e, n, layer: geoadmin.parse_feature_info(
        _wms_text(egid_at(e, n), layer), layer))
    monkeypatch.setattr(geoadmin, "building", lambda fid: FIX["buildings"].get(fid))
    monkeypatch.setattr(geoadmin, "building_by_egid", lambda egid: FIX["other_buildings"].get(str(egid)))
    monkeypatch.setattr(geoadmin, "solar_by_egid", lambda egid: [
        {"attributes": a} for a in FIX["solar_by_egid"].get(str(egid), [])])
    monkeypatch.setattr(geoadmin, "solar", lambda e, n, tolerance_px=0: [
        {"attributes": a} for a in FIX["solar_at_point"].get(egid_at(e, n), [])])
    return asked


def run(address):
    return engine.score(address, 1_000_000, 650_000, mode="live")


# address typed by the user -> (EGID, physical, transition, heating)
EXPECTED = {
    "Sihlmatten 7, 8134 adliswil": (52947, 4, 4, "oil"),
    "Uetlibergstrasse 111b": (302063214, 3, 1, "heat pump"),
    "St. Leodegarstrasse 6": (211552, 4, 4, "gas"),
    "Bielstrasse 3, 4500 Solothurn": (1764933, 3, 3, "gas"),
    "Untertor 3, 4915 St. Urban": (184379, 3, 3, "district heating"),
    "Rohrerstrasse 7": (522994, 3, None, None),
    "Buschberghof 261, 5064 Wittnau": (190194511, 3, 3, "wood"),
    "Gloriastrasse 32": (302066155, 3, 2, "district heating"),
}


@pytest.mark.parametrize("address", list(EXPECTED))
def test_all_eight_addresses(recorded, address):
    egid, physical, transition, heating = EXPECTED[address]
    r = run(address)
    assert r["egid"] == egid
    assert r["scores"]["physical"] == physical
    assert r["scores"]["transition"] == transition
    assert r["building"]["energy_source"] == heating
    assert r["meta"]["errors"] == {}
    assert all(h["level"] != "unknown" for h in r["hazards"].values())


def test_st_leodegar_without_postcode_is_luzern_not_niederwil(recorded):
    r = run("St. Leodegarstrasse 6")
    assert r["address"] == "St.-Leodegar-Strasse 6 6006 Luzern"
    assert r["meta"]["match_note"] == "exact house number"
    assert "St. Leodegar-Strasse 6" in recorded  # the hyphen spelling had to be tried


def test_entrance_number_7_1_does_not_count_as_7(recorded):
    assert geoadmin.geocode("Rohrerstrasse 7")["egid"] == 522994
    s7, _ = geoadmin._score_candidate(geoadmin.parse_address("Rohrerstrasse 7"),
                                      FIX["search"]["Rohrerstrasse 7"][0])
    s71, _ = geoadmin._score_candidate(geoadmin.parse_address("Rohrerstrasse 7"),
                                       FIX["search"]["Rohrerstrasse 7"][1])
    assert s7 > s71


def test_flood_zones_read_from_real_wms_answers(recorded):
    h = run("Sihlmatten 7, 8134 adliswil")["hazards"]
    assert h["river_flood_100"]["level"] == "high" and h["extreme_flood_300plus"]["level"] == "high"
    assert h["hail_50y"]["finding"] == "4 cm" and h["storm_50y"]["finding"] == "130 km/h"
    h = run("St. Leodegarstrasse 6")["hazards"]
    assert h["river_flood_100"]["level"] == "low" and h["extreme_flood_300plus"]["level"] == "high"


def test_neighbours_heat_demand_is_never_used(recorded):
    r = run("Sihlmatten 7, 8134 adliswil")
    en = r["energy"]
    assert en["matched_building"] is False and en["heat_demand_kwh"] is None
    assert en["roof_owner"]["label"] == "Sihlmatten 3"
    assert r["chf"]["co2_t_per_year"] is None  # no CO2 figure from another building's demand
    assert any("Sihlmatten 3" in w for w in r["meta"]["warnings"])
    r = run("Gloriastrasse 32")
    assert r["energy"]["roofs"] == 0 and r["chf"]["solar_income_per_year"] is None
    assert any("no longer in the building register" in x for x in r["meta"]["warnings"])


def test_heat_pump_cost_only_for_buildings_of_flats(recorded):
    assert run("Sihlmatten 7, 8134 adliswil")["chf"]["heat_pump_cost"] == [96000, 144000]  # 8 flats
    r = run("Bielstrasse 3, 4500 Solothurn")  # 6 floors, 1 flat, partly residential
    assert r["chf"]["heat_pump_cost"] is None
    assert any("heat pump cost" in w for w in r["meta"]["warnings"])


def test_all_roofs_of_a_big_building_are_counted(recorded):
    en = run("Bielstrasse 3, 4500 Solothurn")["energy"]
    assert en["roofs"] == 16 and en["matched_building"]
    assert en["heat_demand_kwh"] == 517339
    assert en["solar_kwh"] == 41034  # best roof: class 4, highest yield


def test_heat_demand_of_main_building_part(recorded):
    r = run("St. Leodegarstrasse 6")
    assert r["energy"]["heat_demand_kwh"] == 117135
    assert "heat_demand_all_parts_kwh" not in r["energy"]
    assert not any("parts" in w for w in r["meta"]["warnings"])


def test_missing_heating_entry_gives_no_score(recorded):
    r = run("Rohrerstrasse 7")
    assert r["scores"]["transition"] is None
    assert any("no heating entry" in w for w in r["meta"]["warnings"])
