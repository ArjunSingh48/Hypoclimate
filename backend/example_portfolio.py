"""EXAMPLE mortgage book for the bank dashboard demo.

All loans here are invented example data (as agreed in the group summary:
"bank portfolio = example data"). Town positions are approximate town centres.
The numbers must never be used as evidence in the thesis. The real evidence
comes from live runs on real addresses (batch.py, disaster_test.py).
"""
import random

TOWNS = [  # name, lat, lon, chance of 100-yr flood area, chance of runoff zone
    ("Bern", 46.948, 7.447, 0.10, 0.20), ("Thun", 46.758, 7.628, 0.18, 0.22),
    ("Interlaken", 46.686, 7.863, 0.20, 0.25), ("Brienz BE", 46.754, 8.039, 0.15, 0.30),
    ("Burgdorf", 47.059, 7.628, 0.12, 0.25), ("Münsingen", 46.873, 7.561, 0.08, 0.20),
    ("Spiez", 46.686, 7.680, 0.06, 0.18), ("Biel/Bienne", 47.137, 7.247, 0.10, 0.20),
    ("Langenthal", 47.215, 7.786, 0.05, 0.22), ("Konolfingen", 46.879, 7.621, 0.04, 0.20),
]
HEATING = [("oil", 31), ("gas", 27), ("heat pump", 26), ("district heating", 7),
           ("wood", 5), ("electric", 4)]
PERIODS = [("before 1919", 1918), ("1919-1945", 1945), ("1946-1960", 1960),
           ("1961-1970", 1970), ("1971-1980", 1980), ("1981-1990", 1990),
           ("1991-2000", 2000), ("2001-2010", 2010), ("2011 or later", 2015)]


def build(n_loans: int = 240, seed: int = 2026) -> list[dict]:
    rnd = random.Random(seed)
    loans = []
    for i in range(n_loans):
        town, lat, lon, p_flood, p_runoff = rnd.choice(TOWNS)
        flood = rnd.random() < p_flood
        mountain = town in ("Brienz BE", "Interlaken") and rnd.random() < 0.06
        heating = rnd.choices([h for h, _ in HEATING], [w for _, w in HEATING])[0]
        period, end_year = rnd.choice(PERIODS)
        flats = rnd.choice([1, 1, 1, 2, 3, 4, 5, 6, 8])
        value = rnd.randrange(600_000, 2_400_000, 10_000)
        loan = round(value * rnd.uniform(0.5, 0.8), -4)
        facts = {
            "address": f"Example loan H-{10000 + i}, {town}",
            "egid": None, "lv95": None,
            "wgs84": (lat + rnd.uniform(-0.012, 0.012), lon + rnd.uniform(-0.016, 0.016)),
            "hazards": {
                "river_flood_100": {"inside": flood},
                "extreme_flood_300plus": {"inside": flood or rnd.random() < 0.08},
                "surface_runoff": {"inside": rnd.random() < p_runoff},
                "hail_50y": {"value": round(rnd.uniform(2.0, 5.5), 1)},
                "storm_50y": {"value": round(rnd.uniform(90, 150))},
                "rockfall": {"inside": mountain},
                "avalanche": {"inside": False},
            },
            "building": {"period_label": period, "period_end_year": end_year,
                         "floors": max(1, flats // 2 + 1), "flats": flats,
                         "energy_source": heating},
            "energy": {"heat_demand_kwh": flats * rnd.randrange(8_000, 14_000, 100),
                       "solar_kwh": rnd.randrange(3_000, 16_000, 100)},
            "queried_at": "example", "mode": "example",
        }
        loans.append({"loan_id": f"H-{10000 + i}", "town": town, "property_value": value,
                      "mortgage": loan, "facts": facts})
    return loans
