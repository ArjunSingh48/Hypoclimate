"""Thin client for the free federal geodata API (api3.geo.admin.ch).

Only four calls are needed:
  geocode(address)          -> coordinates (LV95) + building id (EGID)
  identify(e, n, layers)    -> which hazard layers exist at that point
  building(egid)            -> federal building register record
  solar(e, n)               -> roof solar potential near that point

Field names that differ between layers are read with fallbacks, and the raw
API answer is always kept, so any mismatch is easy to spot and fix.
"""
from __future__ import annotations

import re
import requests

from . import config

_session = requests.Session()
_session.headers["User-Agent"] = "HypoClimate student prototype (UZH FinTech seminar)"


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{config.API_BASE}/{path}"
    r = _session.get(url, params=params, timeout=config.TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def geocode(address: str) -> dict | None:
    data = _get("api/SearchServer", {
        "searchText": address, "type": "locations", "origins": "address",
        "limit": 1, "sr": 2056,
    })
    results = data.get("results") or []
    if not results:
        return None
    a = results[0]["attrs"]
    # Note: in this API, attrs["y"] is the easting and attrs["x"] the northing.
    feature_id = str(a.get("featureId") or "")
    egid = feature_id.split("_")[0] if feature_id else None
    label = re.sub(r"<[^>]+>", "", a.get("label", address))
    return {
        "label": label.strip(),
        "e": float(a["y"]), "n": float(a["x"]),
        "egid": int(egid) if egid and egid.isdigit() else None,
        "feature_id": feature_id or None,
    }


def identify(e: float, n: float, layers: list[str], tolerance_px: int = 0) -> list[dict]:
    half = 50
    data = _get("api/MapServer/identify", {
        "geometry": f"{e},{n}", "geometryType": "esriGeometryPoint", "sr": 2056,
        "layers": "all:" + ",".join(layers), "tolerance": tolerance_px,
        "mapExtent": f"{e-half},{n-half},{e+half},{n+half}",
        "imageDisplay": "100,100,96", "returnGeometry": "false", "lang": "en",
    })
    return data.get("results") or []


def building(feature_id: str) -> dict | None:
    data = _get(f"ech/MapServer/{config.BUILDING_LAYER}/{feature_id}",
                {"returnGeometry": "false", "lang": "en"})
    feat = data.get("feature") or (data.get("features") or [None])[0]
    if not feat:
        return None
    return feat.get("attributes") or feat.get("properties")


def solar(e: float, n: float) -> list[dict]:
    return identify(e, n, [config.SOLAR_LAYER], tolerance_px=10)


# ---------------------------------------------------------------------------
# Helpers to read numbers from attributes whose names vary between layers
# ---------------------------------------------------------------------------
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def lv95_to_wgs84(e: float, n: float) -> tuple[float, float]:
    """Swiss LV95 -> WGS84 (lat, lon), swisstopo approximate formulas (~1 m)."""
    y = (e - 2_600_000) / 1e6
    x = (n - 1_200_000) / 1e6
    lon = (2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x
           - 0.0436 * y ** 3)
    lat = (16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x
           - 0.0447 * y * y * x - 0.0140 * x ** 3)
    return lat * 100 / 36, lon * 100 / 36


def first_number(attrs: dict, keys: list[str]) -> float | None:
    for k in keys:
        if k in attrs and attrs[k] not in (None, ""):
            v = attrs[k]
            if isinstance(v, (int, float)):
                return float(v)
            m = _NUM.search(str(v))
            if m:
                return float(m.group().replace(",", "."))
    return None
