"""All rules and assumptions in one place.

The business team (scoring owner) can change any value here without
touching the rest of the code. Every assumption says where it comes from.
"""

API_BASE = "https://api3.geo.admin.ch/rest/services"
TIMEOUT_S = 15

# ---------------------------------------------------------------------------
# Federal map layers we query (open government data, geo.admin.ch)
# ---------------------------------------------------------------------------
HAZARD_LAYERS = {
    "river_flood_100": "ch.bafu.aquaprotect_100",
    "extreme_flood_300plus": "ch.bafu.aquaprotect_500",
    "surface_runoff": "ch.bafu.gefaehrdungskarte-oberflaechenabfluss",
    "hail_50y": "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre",
    "storm_50y": "ch.bafu.sturm-boeenspitzen_50",
    "rockfall": "ch.bafu.silvaprotect-sturz",
    "avalanche": "ch.bafu.silvaprotect-lawinen",
}
# Layers that exist only as map pictures (no data table for "identify"):
# they are asked through the WMS map service ("GetFeatureInfo") instead.
WMS_ONLY_LAYERS = {
    "ch.bafu.aquaprotect_100", "ch.bafu.aquaprotect_500",
    "ch.bafu.gefaehrdungskarte-oberflaechenabfluss",
    "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre",
    "ch.bafu.silvaprotect-sturz", "ch.bafu.silvaprotect-lawinen",
}
WMS_URL = "https://wms.geo.admin.ch/"
# Fallback address search if geo.admin.ch finds nothing (OpenStreetMap, max. 1 request/second)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

BUILDING_LAYER = "ch.bfs.gebaeude_wohnungs_register"
SOLAR_LAYER = "ch.bfe.solarenergie-eignung-daecher"

HAZARD_LABELS = {
    "river_flood_100": "River flood, 100-year",
    "extreme_flood_300plus": "Extreme flood, 300-year+",
    "surface_runoff": "Surface runoff (heavy rain)",
    "hail_50y": "Hail, 50-year",
    "storm_50y": "Storm gusts, 50-year",
    "rockfall": "Rockfall",
    "avalanche": "Avalanche",
}

# Hazards that are "in zone or not": inside the zone -> this level
ZONE_LEVEL_IF_INSIDE = {
    "river_flood_100": "high",
    "extreme_flood_300plus": "high",
    "surface_runoff": "medium",  # layer gives no flow depth, so never "high"
    "rockfall": "high",
    "avalanche": "high",
}

# Hazards with a number: thresholds (value < low_max -> low, < medium_max -> medium, else high)
HAIL_CM = {"low_max": 3.0, "medium_max": 5.0}       # 4.0 cm -> medium (as in the mockup)
STORM_KMH = {"low_max": 100.0, "medium_max": 140.0}  # 116 km/h -> medium (as in the mockup)

# Several zone layers describe the same peril; count each peril once
PERILS = {
    "river flood": ["river_flood_100", "extreme_flood_300plus"],
    "surface runoff": ["surface_runoff"],
    "hail": ["hail_50y"],
    "storm": ["storm_50y"],
    "rockfall & avalanche": ["rockfall", "avalanche"],
}

LEVEL_POINTS = {"low": 1, "medium": 3, "high": 4}  # physical score 1-5
EXTRA_POINT_IF_TWO_HIGH_PERILS = 1

# ---------------------------------------------------------------------------
# Transition score (heating) 1-5
# ---------------------------------------------------------------------------
TRANSITION_BASE = {
    "oil": 4, "gas": 3, "electric": 3, "unknown": 3,
    "wood": 2, "district heating": 2, "waste heat": 2, "heat pump": 1, "solar thermal": 1, "none": 1,
}
TRANSITION_EXTRA_IF_BUILT_BEFORE = 1946  # very old buildings: +1 (capped at 5)

# ---------------------------------------------------------------------------
# CHF assumptions (from the group's "Method & data" page)
# ---------------------------------------------------------------------------
FLOOD_VALUE_DISCOUNT = (0.02, 0.05)       # 2-5% if inside the 100-year flood area
CO2_KG_PER_KWH = {"gas": 0.198, "oil": 0.265}  # gas from the Method page; oil = group to confirm
CO2_LEVY_CHF_PER_T = 120.0
HEAT_PUMP_CHF_PER_FLAT = (12_000, 18_000)
# the per-flat cost only makes sense where the building is mainly flats (GWR category)
HEAT_PUMP_COST_CATEGORIES = ("residential only", "residential with other use")
SOLAR_CHF_PER_KWH = 0.10                  # gives CHF 1,510 for 15,100 kWh, as in the mockup
HEAVY_RAIN_PCT_PER_DEG = 7.0              # heavy-rain intensity per extra degree of warming
EXTRA_WARMING_STEPS = (1.0, 2.0)          # shown as "if warming rises by 1 / 2 degrees"

ASSUMPTIONS_VERSION = "v1"

# ---------------------------------------------------------------------------
# Federal building register (GWR) codes
# ---------------------------------------------------------------------------
GWR_ENERGY_SOURCE = {
    7500: "none", 7501: "heat pump", 7510: "heat pump", 7511: "heat pump", 7512: "heat pump",
    7513: "heat pump", 7520: "gas", 7530: "oil", 7540: "wood", 7541: "wood", 7542: "wood",
    7543: "wood", 7550: "waste heat", 7560: "electric", 7570: "solar thermal",
    7580: "district heating", 7581: "district heating", 7582: "district heating",
    7598: "unknown", 7599: "unknown",
}
GWR_PERIOD = {
    8011: ("before 1919", 1918), 8012: ("1919-1945", 1945), 8013: ("1946-1960", 1960),
    8014: ("1961-1970", 1970), 8015: ("1971-1980", 1980), 8016: ("1981-1985", 1985),
    8017: ("1986-1990", 1990), 8018: ("1991-1995", 1995), 8019: ("1996-2000", 2000),
    8020: ("2001-2005", 2005), 8021: ("2006-2010", 2010), 8022: ("2011-2015", 2015),
    8023: ("2016 or later", 2016),
}
GWR_CATEGORY = {  # gkat
    1010: "provisional shelter", 1020: "residential only", 1030: "residential with other use",
    1040: "partly residential", 1060: "non-residential", 1080: "special building",
}
SOLAR_CLASS = {1: "low", 2: "medium", 3: "good", 4: "very good", 5: "excellent"}
