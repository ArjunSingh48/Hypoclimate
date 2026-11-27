"""HypoClimate scoring engine.

Two steps, kept separate on purpose:
  1. collect(address)  -> raw facts (from the federal API, or example data)
  2. evaluate(facts)   -> scores, CHF figures and the JSON every screen uses

Everything a screen needs comes from evaluate(); no screen calculates anything.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import config
from . import example_data
from . import geoadmin

HAIL_KEYS = ["value_0.name"]          # WMS answer, e.g. value_0.name = '4' (cm)
STORM_KEYS = ["boenspitzen_kmh_50"]   # e.g. "130 ± 21 km/h"
ZONE_HAZARDS = list(config.ZONE_LEVEL_IF_INSIDE)


# ---------------------------------------------------------------------------
# Step 1: collect facts
# ---------------------------------------------------------------------------
def collect(address: str, mode: str = "live") -> dict:
    if mode == "example":
        facts = example_data.lookup(address)
        if facts is None:
            raise LookupError(
                "Example mode only knows: Gerberngasse 20, 3011 Bern and "
                "Zürichbergstrasse 221, Zürich. Use live mode for other addresses.")
        return {**facts, "mode": "example"}
    return _collect_live(address)


def _collect_live(address: str) -> dict:
    errors: dict[str, str] = {}
    try:
        loc = geoadmin.geocode(address)
    except Exception as exc:
        raise LookupError(f"Address search failed for '{address}': {str(exc)[:150]}") from exc
    if loc is None:
        raise LookupError(f"Address not found in Switzerland: {address}")
    e, n = loc["e"], loc["n"]
    raw: dict = {"location": loc}

    # Ask for each layer separately: one bad layer must not break the others.
    by_layer: dict[str, list] = {}

    def ask(layer):
        try:
            if layer in config.WMS_ONLY_LAYERS:
                hits = [{"attributes": a} for a in geoadmin.wms_feature_info(e, n, layer)]
            else:
                hits = geoadmin.identify(e, n, [layer])
            return layer, hits, None
        except Exception as exc:
            return layer, [], str(exc)[:150]

    with ThreadPoolExecutor(max_workers=7) as pool:
        for layer, hits, err in pool.map(ask, config.HAZARD_LAYERS.values()):
            by_layer[layer] = [h.get("attributes") or {} for h in hits]
            if err:
                errors[layer] = err
    raw["hazards"] = by_layer

    hazards = {}
    for key, layer in config.HAZARD_LAYERS.items():
        hits = by_layer.get(layer, [])
        if key in ZONE_HAZARDS:
            hazards[key] = {"inside": None if layer in errors else bool(hits)}
        else:
            keys = HAIL_KEYS if key == "hail_50y" else STORM_KEYS
            value = None
            for attrs in hits:
                value = geoadmin.first_number(attrs, keys)
                if value is not None:
                    break
            hazards[key] = {"value": value}

    building, egid = {}, loc["egid"]
    attrs = {}
    try:
        if loc["feature_id"]:
            attrs = geoadmin.building(loc["feature_id"]) or {}
        if not attrs:  # no building id from the address search: find the building at the point
            number = geoadmin.parse_address(address)["number"]
            attrs = geoadmin.building_near(e, n, number) or {}
            egid = egid or _int(attrs.get("egid"))
    except Exception as exc:
        errors["building register"] = str(exc)[:150]
    raw["building"] = attrs
    building = _read_building(attrs) if attrs else {}

    # Solar roofs: first every roof linked to this building's EGID; only if there is none,
    # the roof at the address point (and then say whose roof that is).
    roofs, roof_owner = [], None
    try:
        if egid:
            roofs = geoadmin.solar_by_egid(egid)
        if not roofs:
            roofs = geoadmin.solar(e, n) or geoadmin.solar(e, n, tolerance_px=10)
            other = {_int((r.get("attributes") or {}).get("gwr_egid")) for r in roofs} - {None, egid}
            if other:
                oid = sorted(other)[0]
                try:
                    o = geoadmin.building_by_egid(oid)
                except Exception:
                    o = None
                roof_owner = {"egid": oid, "label": (o or {}).get("strname_deinr"),
                              "in_register": o is not None}
    except Exception as exc:
        roofs, errors["solar roofs"] = [], str(exc)[:150]
    raw["solar"] = [r.get("attributes") or {} for r in roofs]
    energy = _read_solar(raw["solar"], egid, roof_owner)

    return {
        "address": loc["label"], "egid": egid, "lv95": {"e": e, "n": n},
        "hazards": hazards, "building": building, "energy": energy,
        "queried_at": date.today().isoformat(), "mode": "live", "raw": raw,
        "errors": errors, "warnings": _plausibility(hazards, building, energy, loc),
        "address_source": loc.get("source"), "match_note": loc.get("match_note"),
    }


def _plausibility(hazards: dict, b: dict, en: dict, loc: dict) -> list[str]:
    """Flag values that cannot be right or that come from somewhere else, so nothing passes silently."""
    w = []
    if loc.get("match_note") and loc["match_note"] != "exact house number":
        w.append(loc["match_note"])
    hail = hazards.get("hail_50y", {}).get("value")
    if hail is not None and not 0 < hail <= 15:
        w.append(f"hail value {hail} cm is outside 0-15 cm")
    storm = hazards.get("storm_50y", {}).get("value")
    if storm is not None and not 40 <= storm <= 300:
        w.append(f"storm value {storm} km/h is outside 40-300 km/h")
    year = b.get("period_end_year")
    if year is not None and not 1000 <= year <= date.today().year + 1:
        w.append(f"construction year {year} is not plausible")
    if b and b.get("energy_source") is None:
        w.append(f"the building register has no heating entry for this building "
                 f"({b.get('category') or 'category unknown'}); transition score not calculated")
    heat, area, flats = en.get("heat_demand_kwh"), b.get("energy_area_m2"), b.get("flats")
    if heat and area and heat / area > 400:
        w.append(f"heat demand {heat:,.0f} kWh/yr on {area} m² heated area looks too high")
    elif heat and not area and flats and b.get("category") == "residential only" \
            and heat / flats > 40_000:
        w.append(f"heat demand {heat:,.0f} kWh/yr for {flats} flat(s) looks too high")
    owner = en.get("roof_owner")
    if owner:
        who = f"{owner['label']} (EGID {owner['egid']})" if owner.get("label") else \
            f"EGID {owner['egid']}, which is no longer in the building register"
        used = "its solar potential is shown, its heat demand is not used" if owner.get("in_register") \
            else "no solar or heat figures are shown"
        w.append(f"the solar register has no roof for this building; the roof at this address "
                 f"belongs to {who}; {used}")
    if b.get("energy_source") in ("oil", "gas") and b.get("category") \
            and b["category"] not in config.HEAT_PUMP_COST_CATEGORIES:
        w.append(f"heat pump cost is estimated per flat, which does not fit a "
                 f"{b['category']} building; not calculated")
    return w


def _read_building(a: dict) -> dict:
    period = config.GWR_PERIOD.get(_int(a.get("gbaup")))
    year = _int(a.get("gbauj"))
    code = _int(a.get("genh1"))
    return {
        "period_label": str(year) if year else (period[0] if period else None),
        "period_end_year": year or (period[1] if period else None),
        "floors": _int(a.get("gastw")),
        "flats": _int(a.get("ganzwhg")),
        "footprint_m2": _int(a.get("garea")),
        "energy_area_m2": _int(a.get("gebf")),
        "category": config.GWR_CATEGORY.get(_int(a.get("gkat"))),
        "name": a.get("gbez") or None,
        # no heating entry in the register -> None (no score), never a guessed value
        "energy_source": config.GWR_ENERGY_SOURCE.get(code, "unknown") if code else None,
    }


def _read_solar(roofs: list[dict], egid: int | None, roof_owner: dict | None = None) -> dict:
    if not roofs:
        return {}
    num = geoadmin.first_number
    if roof_owner and not roof_owner.get("in_register"):
        # the roof at the point belongs to a building that no longer exists (replaced):
        # its old roof data says nothing about the building standing there now
        return {"roofs": 0, "matched_building": False, "roof_owner": roof_owner}
    mine = [r for r in roofs if egid is not None and _int(r.get("gwr_egid") or r.get("egid")) == egid]
    matched = bool(mine)
    roofs = mine or roofs
    best = max(roofs, key=lambda r: (_int(r.get("klasse")) or 0, num(r, ["stromertrag"]) or 0))
    # Heat demand is given per building part (building_id), repeated on each of its roofs.
    parts: dict = {}
    for r in roofs:
        p = parts.setdefault(r.get("building_id", "one part"), {"area": 0.0, "heat": None, "water": None})
        p["area"] += num(r, ["flaeche"]) or 0
        p["heat"] = p["heat"] if p["heat"] is not None else num(r, ["bedarf_heizung", "heizwaermebedarf"])
        p["water"] = p["water"] if p["water"] is not None else num(r, ["bedarf_warmwasser"])
    main = max(parts.values(), key=lambda p: p["area"])
    return {
        # the heat demand of another building is never used for this one
        "heat_demand_kwh": main["heat"] if matched else None,
        "hot_water_kwh": main["water"] if matched else None,
        "building_parts": len(parts) if matched else 0,
        "roof_area_m2": num(best, ["flaeche"]),
        "roof_class": config.SOLAR_CLASS.get(_int(best.get("klasse"))),
        "solar_kwh": num(best, ["stromertrag"]),
        "solar_kwh_all_roofs": sum(num(r, ["stromertrag"]) or 0 for r in roofs),
        "roofs": len(roofs), "matched_building": matched, "roof_owner": roof_owner,
    }


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Step 2: evaluate
# ---------------------------------------------------------------------------
def _level(key: str, h: dict) -> tuple[str, str]:
    """Return (level, finding text) for one hazard."""
    if key in ZONE_HAZARDS:
        if h.get("inside") is None:
            return "unknown", "no data"
        if h["inside"]:
            return config.ZONE_LEVEL_IF_INSIDE[key], "inside zone"
        return "low", "outside zone"
    v = h.get("value")
    if v is None:
        return "unknown", "no data"
    t, unit = (config.HAIL_CM, "cm") if key == "hail_50y" else (config.STORM_KMH, "km/h")
    lvl = "low" if v < t["low_max"] else "medium" if v < t["medium_max"] else "high"
    return lvl, f"{v:g} {unit}"


def evaluate(facts: dict, property_value: float | None = None,
             mortgage: float | None = None) -> dict:
    hazards = {}
    for key, layer in config.HAZARD_LAYERS.items():
        lvl, finding = _level(key, facts["hazards"].get(key, {}))
        hazards[key] = {"label": config.HAZARD_LABELS[key], "level": lvl,
                        "finding": finding, "source": layer}

    # physical score: worst peril, +1 if two or more perils are high
    peril_level = {}
    for peril, keys in config.PERILS.items():
        lv = [hazards[k]["level"] for k in keys if hazards[k]["level"] != "unknown"]
        if lv:
            peril_level[peril] = max(lv, key=lambda x: config.LEVEL_POINTS[x])
    physical = None
    if peril_level:
        physical = max(config.LEVEL_POINTS[l] for l in peril_level.values())
        if sum(l == "high" for l in peril_level.values()) >= 2:
            physical += config.EXTRA_POINT_IF_TWO_HIGH_PERILS
        physical = min(physical, 5)
    high = [p for p, l in peril_level.items() if l == "high"]
    medium = [p for p, l in peril_level.items() if l == "medium"]
    physical_drivers = high or medium

    b = facts.get("building") or {}
    en = facts.get("energy") or {}
    source = b.get("energy_source")
    transition = None
    if source:
        transition = config.TRANSITION_BASE.get(source, 3)
        if (b.get("period_end_year") or 9999) < config.TRANSITION_EXTRA_IF_BUILT_BEFORE:
            transition += 1
        transition = min(transition, 5)

    chf = _chf(hazards, b, en, property_value, mortgage)
    drivers = physical_drivers + ([f"{source} heating"] if source in ("oil", "gas") else [])

    lv = facts.get("lv95")
    wgs = geoadmin.lv95_to_wgs84(lv["e"], lv["n"]) if lv else facts.get("wgs84")
    return {
        "address": facts["address"],
        "egid": facts.get("egid"),
        "lv95": lv,
        "wgs84": {"lat": round(wgs[0], 6), "lon": round(wgs[1], 6)} if wgs else None,
        "hazards": hazards,
        "building": b,
        "energy": en,
        "scores": {
            "physical": physical, "physical_label": _score_label(physical),
            "transition": transition, "transition_label": _score_label(transition),
            "main_drivers": drivers,
        },
        "chf": chf,
        "trend_50y": [
            {"extra_warming_c": d,
             "heavy_rain_intensity_change_pct": round(d * config.HEAVY_RAIN_PCT_PER_DEG, 1)}
            for d in config.EXTRA_WARMING_STEPS
        ],
        "summary": _summary(physical_drivers, source, hazards),
        "meta": {"queried_at": facts.get("queried_at"), "mode": facts.get("mode"),
                 "assumptions_version": config.ASSUMPTIONS_VERSION,
                 "note": "Information, not advice. Federal flood maps are indicative.",
                 "errors": facts.get("errors", {}), "warnings": facts.get("warnings", []),
                 "address_source": facts.get("address_source"),
                 "match_note": facts.get("match_note")},
    }


def _chf(hazards, b, en, value, mortgage) -> dict:
    out = {"value_discount": None, "ltv_today_pct": None, "ltv_after_pct": None,
           "co2_t_per_year": None, "co2_levy_per_year": None,
           "heat_pump_cost": None, "solar_income_per_year": None}
    if value:
        lo, hi = config.FLOOD_VALUE_DISCOUNT
        inside = hazards["river_flood_100"]["level"] == "high"
        disc = (round(value * lo), round(value * hi)) if inside else (0, 0)
        out["value_discount"] = [-disc[0], -disc[1]]
        if mortgage:
            out["ltv_today_pct"] = round(100 * mortgage / value, 1)
            out["ltv_after_pct"] = [round(100 * mortgage / (value - d), 1) for d in disc]
    src = b.get("energy_source")
    heat = en.get("heat_demand_kwh")
    if src in config.CO2_KG_PER_KWH and heat:
        t = heat * config.CO2_KG_PER_KWH[src] / 1000
        out["co2_t_per_year"] = round(t, 1)
        out["co2_levy_per_year"] = round(t * config.CO2_LEVY_CHF_PER_T)
    if src in ("oil", "gas") and b.get("flats") and b.get("category") in config.HEAT_PUMP_COST_CATEGORIES:
        lo, hi = config.HEAT_PUMP_CHF_PER_FLAT
        out["heat_pump_cost"] = [b["flats"] * lo, b["flats"] * hi]
    if en.get("solar_kwh"):
        out["solar_income_per_year"] = round(en["solar_kwh"] * config.SOLAR_CHF_PER_KWH)
    return out


def _score_label(s):
    if s is None:
        return "no data"
    return {1: "Low", 2: "Low", 3: "Medium", 4: "High", 5: "High"}[s]


def _summary(drivers, source, hazards) -> str:
    parts = []
    if drivers:
        parts.append(f"Main physical risk: {', '.join(drivers)}.")
    else:
        parts.append("No high or medium natural hazard found at this address.")
    if source in ("oil", "gas"):
        parts.append(f"The {source} heating is a transition risk: plan for a replacement.")
    if hazards["river_flood_100"]["level"] == "high":
        parts.append("Flood damage to the building is covered by the cantonal building "
                     "insurance; value loss, contents and deductibles are not.")
    return " ".join(parts)


def score(address: str, property_value=None, mortgage=None, mode="live") -> dict:
    return evaluate(collect(address, mode), property_value, mortgage)
