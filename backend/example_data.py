"""Example mode: facts for addresses the group already queried by hand.

Gerberngasse 20, Bern: values from the group's query of 17.11.2026
(see the HypoClimate prototype PDF and group summary).
Zuerichbergstrasse 221, Zuerich: the group reported "comes back clean" for
hazards; building and roof data were not reported, so they are left empty.
This lets the demo run without internet and shows how missing data is handled.
"""

EXAMPLES = {
    "gerberngasse 20, 3011 bern": {
        "address": "Gerberngasse 20, 3011 Bern",
        "egid": 1230068,
        "canton": "BE",
        "lv95": {"e": 2601406, "n": 1199640},
        "hazards": {
            "river_flood_100": {"inside": True},
            "extreme_flood_300plus": {"inside": True},
            "surface_runoff": {"inside": False},
            "hail_50y": {"value": 4.0},
            "storm_50y": {"value": 116.0},
            "rockfall": {"inside": False},
            "avalanche": {"inside": False},
        },
        "building": {
            "period_label": "1946-1960", "period_end_year": 1960,
            "floors": 4, "flats": 5, "footprint_m2": 173, "energy_source": "gas",
            "category": "residential only",  # as described in the group mockup (5 flats)
        },
        "energy": {
            "heat_demand_kwh": 59300, "hot_water_kwh": 9500,
            "roof_area_m2": 75, "roof_class": "very good", "solar_kwh": 15100,
        },
        "queried_at": "2026-11-17",
    },
    "zürichbergstrasse 221, zürich": {
        "address": "Zürichbergstrasse 221, Zürich",
        "egid": None,
        "canton": "ZH",
        "lv95": None,
        "hazards": {
            "river_flood_100": {"inside": False},
            "extreme_flood_300plus": {"inside": False},
            "surface_runoff": {"inside": False},
            "hail_50y": {"value": None},
            "storm_50y": {"value": None},
            "rockfall": {"inside": False},
            "avalanche": {"inside": False},
        },
        "building": {},
        "energy": {},
        "queried_at": "2026-11-17",
    },
}

ALIASES = {
    "gerberngasse 20": "gerberngasse 20, 3011 bern",
    "gerberngasse 20 bern": "gerberngasse 20, 3011 bern",
    "zürichbergstrasse 221": "zürichbergstrasse 221, zürich",
    "zuerichbergstrasse 221": "zürichbergstrasse 221, zürich",
    "zürichbergstrasse 221 zürich": "zürichbergstrasse 221, zürich",
}


def lookup(address: str) -> dict | None:
    key = " ".join(address.lower().replace("  ", " ").split())
    key = ALIASES.get(key, key)
    return EXAMPLES.get(key)
