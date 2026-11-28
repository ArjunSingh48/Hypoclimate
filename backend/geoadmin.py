"""Client for the free federal geodata services (geo.admin.ch) plus one fallback.

Calls used:
  geocode(address)              -> best matching address: coordinates (LV95) + building id (EGID)
  identify(e, n, layers)        -> vector layers at a point (storm, building register, solar roofs)
  wms_feature_info(e, n, layer) -> map-picture layers at a point (flood, runoff, hail, rockfall, avalanche)
  building(feature_id)          -> federal building register record
  building_near(e, n)           -> building register record of the building at a point (fallback)
  solar_by_egid(egid)           -> all roof surfaces of one building (solar register)
  solar(e, n)                   -> roof surfaces at a point (fallback)

Fallback: if the federal address search finds nothing, OpenStreetMap (Nominatim) is asked for the
coordinates, and the building is then found in the federal building register at that point.
Every answer is kept raw, so any mismatch is easy to spot.
"""
from __future__ import annotations

import re
import unicodedata

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

_session = requests.Session()
_session.headers["User-Agent"] = "HypoClimate student prototype (UZH FinTech seminar)"
_retry = Retry(total=3, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504),
               allowed_methods=("GET",))
_session.mount("https://", HTTPAdapter(max_retries=_retry))


def _get(path: str, params: dict | None = None) -> dict:
    r = _session.get(f"{config.API_BASE}/{path}", params=params, timeout=config.TIMEOUT_S)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Address search
# ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    """Lower case, umlauts as 'ue', no accents, single spaces: for comparing addresses."""
    t = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


_HOUSE_NO = re.compile(r"\b(\d+\s?[a-z]?)\b(?!\d)")
_POSTCODE = re.compile(r"\b(\d{4})\b")


def parse_address(address: str) -> dict:
    """Split a typed address into street words, house number and postcode (if present)."""
    head, _, tail = address.partition(",")
    if not tail:  # no comma: "Street 16 8006 Zürich" -> the 4-digit number after the house number is the postcode
        m = re.match(r"^(.*\b\d+\s?[a-z]?)\s+(\d{4}\b.*)$", _norm(head))
        if m:
            head, tail = m.group(1), m.group(2)
    no = _HOUSE_NO.findall(_norm(head))
    pc = _POSTCODE.findall(_norm(tail)) if tail else []
    street = re.sub(r"\d+\s?[a-z]?\b", " ", _norm(head))
    return {"street": " ".join(street.split()), "number": no[-1].replace(" ", "") if no else None,
            "postcode": pc[0] if pc else None}


def _variants(address: str) -> list[str]:
    """Spellings to try, in order: as typed, without commas, St./Sankt swapped."""
    out = [address, address.replace(",", " ")]
    if re.search(r"\bSt\.\s?", address):
        out.append(re.sub(r"\bSt\.\s?-?", "Sankt-", address))
        out.append(re.sub(r"\bSt\.\s?", "St.", address).replace("St.", "St. "))
    if re.search(r"str\.(?=\s|,|$)", address, re.I):
        out.append(re.sub(r"str\.(?=\s|,|$)", "strasse", address, flags=re.I))
    if re.search(r"\bSankt[- ]", address, re.I):
        out.append(re.sub(r"\bSankt[- ]", "St. ", address, flags=re.I))
    # "Xstrasse" may be stored as "X-Strasse" in the index (and the other way round)
    for v in list(out):
        if re.search(r"[a-zäöü]strasse\b", v, re.I):
            out.append(re.sub(r"([a-zäöü])strasse\b", r"\1-Strasse", v, flags=re.I))
        if re.search(r"-Strasse\b", v):
            out.append(v.replace("-Strasse", "strasse"))
    seen, uniq = set(), []
    for v in out:
        v = " ".join(v.split())
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


_SAINT = re.compile(r"\b(sankt|saint|san)\b")


def _compact_street(street: str) -> str:
    """Street name without spaces, dots or hyphens, 'Sankt' as 'st', 'str' as 'strasse'.

    'St. Gallerstrasse', 'St.-Galler-Strasse' and 'Sankt Galler Str' all give
    'stgallerstrasse', so spelling differences do not decide the match.
    """
    t = _SAINT.sub("st", _norm(street))
    t = re.sub(r"\bstr\b", "strasse", t)
    return t.replace(" ", "")


def split_label(label: str) -> dict:
    """'Bahnhofstrasse 7.1 <b>8001 Zürich</b>' -> street, house number '7.1', postcode, town."""
    head, _, tail = label.partition("<b>")
    head = " ".join(re.sub(r"<[^>]+>", " ", head).split())
    tail = " ".join(re.sub(r"<[^>]+>", " ", tail).split())
    m = re.match(r"^(.*?)\s+(\d+(?:\.\d+)?\s?[a-zA-Z]?)$", head)
    street, no = (m.group(1), m.group(2).replace(" ", "").lower()) if m else (head, None)
    pc = re.match(r"(\d{4})\s*(.*)", tail)
    return {"street": street, "number": no, "postcode": pc.group(1) if pc else None,
            "town": pc.group(2) if pc else tail}


def _base_no(no: str | None) -> str | None:
    """House number without letter or entrance suffix: '111b' -> '111', '7.1' -> '7'."""
    return re.match(r"\d+", no).group() if no and re.match(r"\d+", no) else None


def _score_candidate(want: dict, attrs: dict) -> tuple[int, dict]:
    """How well one search result matches the typed address (higher is better).

    House number: exact +10, same number with another letter/entrance (111 vs 111b, 7.1 vs 7) +3.
    Postcode: same +5, different -5. Street: same (spelling-independent) +6,
    one contained in the other (Gallerstrasse vs St. Gallerstrasse) +2.
    """
    c = split_label(attrs.get("label", ""))
    score, why = 0, {"number": False, "street": False, "postcode": None}
    if want["number"]:
        if c["number"] == want["number"]:
            score += 10
            why["number"] = True
        elif _base_no(c["number"]) == _base_no(want["number"]):
            score += 3
    if want["postcode"] and c["postcode"]:
        same = c["postcode"] == want["postcode"]
        score += 5 if same else -5
        why["postcode"] = same
    ws, cs = _compact_street(want["street"]), _compact_street(c["street"])
    if ws and cs:
        if ws == cs:
            score += 6
            why["street"] = True
        elif ws in cs or cs in ws:
            score += 2
    return score, why


def search_candidates(address: str, limit: int = 8) -> list[dict]:
    """All address results of the federal search for one spelling."""
    data = _get("api/SearchServer", {
        "searchText": address, "type": "locations", "origins": "address",
        "limit": limit, "sr": 2056,
    })
    return [r["attrs"] for r in data.get("results") or [] if "attrs" in r]


def _location_from_attrs(a: dict, note: str) -> dict:
    # In this API, attrs["y"] is the easting and attrs["x"] the northing.
    feature_id = str(a.get("featureId") or "")
    egid = feature_id.split("_")[0] if feature_id else None
    return {
        "label": " ".join(re.sub(r"<[^>]+>", " ", a.get("label", "")).split()),
        "e": float(a["y"]), "n": float(a["x"]),
        "egid": int(egid) if egid and egid.isdigit() else None,
        "feature_id": feature_id or None,
        "source": "geo.admin.ch address search", "match_note": note,
        "canton": canton_from_detail(a.get("detail", "")),
    }


def canton_from_detail(detail: str) -> str | None:
    """The address search ends its 'detail' text with the canton, e.g. '... ch be' -> 'BE'."""
    m = re.search(r"\bch ([a-z]{2})\s*$", detail or "")
    return m.group(1).upper() if m else None


def geocode(address: str) -> dict | None:
    """Best matching Swiss address. Tries several spellings, then OpenStreetMap as fallback."""
    want = parse_address(address)
    best, best_score, best_why, tried, exact = None, -99, None, [], {}
    for variant in _variants(address):
        tried.append(variant)
        for attrs in search_candidates(variant):
            s, why = _score_candidate(want, attrs)
            if why["number"] and why["street"] and why["postcode"] is not False:
                c = split_label(attrs.get("label", ""))
                exact.setdefault(c["postcode"], attrs)
            if s > best_score:
                best, best_score, best_why = attrs, s, why
        # stop only when number AND street are exactly right (a near miss in another
        # town must not end the search before the other spellings are tried)
        if best_why and best_why["street"] and (best_why["number"] or not want["number"]):
            break
    if best is not None:
        notes = []
        if want["number"] and not best_why["number"]:
            notes.append(f"house number {want['number']} not found exactly; closest address used")
        if not best_why["street"]:
            notes.append(f"street spelled differently in the register: "
                         f"{split_label(best.get('label', ''))['street']}")
        if not want["postcode"] and len(exact) > 1:
            towns = ", ".join(sorted(" ".join(split_label(a["label"])[k] for k in ("postcode", "town"))
                                     for a in exact.values()))
            notes.append(f"this address exists in several places ({towns}); add the postcode")
        return _location_from_attrs(best, "; ".join(notes) or "exact house number")
    osm = geocode_osm(address)
    if osm:
        osm["match_note"] = f"not in federal address search (tried: {'; '.join(tried)}); " \
                            "location from OpenStreetMap"
    return osm


def geocode_osm(address: str) -> dict | None:
    """Fallback: OpenStreetMap Nominatim (max. 1 request per second, attribution required)."""
    r = _session.get(config.NOMINATIM_URL, params={
        "q": address, "countrycodes": "ch", "format": "jsonv2", "limit": 1}, timeout=config.TIMEOUT_S)
    r.raise_for_status()
    res = r.json()
    if not res:
        return None
    lat, lon = float(res[0]["lat"]), float(res[0]["lon"])
    e, n = wgs84_to_lv95(lat, lon)
    return {"label": res[0].get("display_name", address), "e": e, "n": n, "egid": None,
            "feature_id": None, "source": "OpenStreetMap Nominatim", "match_note": ""}


# ---------------------------------------------------------------------------
# Layers at a point
# ---------------------------------------------------------------------------
def identify(e: float, n: float, layers: list[str], tolerance_px: int = 0) -> list[dict]:
    half = 50  # 100 m x 100 m window at 100 px: 1 px = 1 m
    data = _get("ech/MapServer/identify", {
        "geometry": f"{e},{n}", "geometryType": "esriGeometryPoint", "sr": 2056,
        "layers": "all:" + ",".join(layers), "tolerance": tolerance_px,
        "mapExtent": f"{e-half},{n-half},{e+half},{n+half}",
        "imageDisplay": "100,100,96", "returnGeometry": "false", "lang": "en",
    })
    return data.get("results") or []


def wms_feature_info(e: float, n: float, layer: str) -> list[dict]:
    """Which features of one map-picture layer cover this point (WMS GetFeatureInfo)."""
    half = 50  # 100 m x 100 m window, 101 x 101 pixels: the address is the centre pixel
    r = _session.get(config.WMS_URL, params={
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo",
        "LAYERS": layer, "QUERY_LAYERS": layer, "CRS": "EPSG:2056",
        "BBOX": f"{e-half},{n-half},{e+half},{n+half}", "WIDTH": 101, "HEIGHT": 101,
        "I": 50, "J": 50, "INFO_FORMAT": "text/plain", "FORMAT": "image/png",
    }, timeout=config.TIMEOUT_S)
    r.raise_for_status()
    return parse_feature_info(r.text, layer)


_FEATURE = re.compile(r"^\s*Feature\s+\S+:", re.M)
_ATTR = re.compile(r"^\s*(\S+)\s*=\s*'(.*)'\s*$", re.M)


def parse_feature_info(text: str, layer: str) -> list[dict]:
    """Turn the plain-text WMS answer into one dict of attributes per feature."""
    if "Search returned no results" in text or "Feature" not in text:
        return []
    features = []
    for block in _FEATURE.split(text)[1:]:
        features.append({k.replace(layer + ".", "", 1): v for k, v in _ATTR.findall(block)})
    return features


# ---------------------------------------------------------------------------
# Building register and solar roofs
# ---------------------------------------------------------------------------
def building(feature_id: str) -> dict | None:
    data = _get(f"ech/MapServer/{config.BUILDING_LAYER}/{feature_id}",
                {"returnGeometry": "false", "lang": "en"})
    feat = data.get("feature") or (data.get("features") or [None])[0]
    if not feat:
        return None
    return feat.get("attributes") or feat.get("properties")


def building_near(e: float, n: float, number: str | None = None) -> dict | None:
    """Building register entry at a point (used when the address search gave no EGID)."""
    hits = identify(e, n, [config.BUILDING_LAYER], tolerance_px=15)
    if not hits:
        return None
    attrs = [h.get("attributes") or {} for h in hits]
    if number:
        same_no = [a for a in attrs if _norm(str(a.get("deinr", ""))) == number]
        if same_no:
            return same_no[0]
    return attrs[0]


def find(layer: str, field: str, value) -> list[dict]:
    """All features of a layer whose field equals value (exact match)."""
    data = _get("ech/MapServer/find", {"layer": layer, "searchField": field,
                                         "searchText": value, "contains": "false",
                                         "returnGeometry": "false", "lang": "en"})
    return data.get("results") or []


def solar_by_egid(egid: int) -> list[dict]:
    """Every roof surface the federal solar register links to this building (EGID)."""
    return find(config.SOLAR_LAYER, "gwr_egid", egid)


def solar(e: float, n: float, tolerance_px: int = 0) -> list[dict]:
    """Roof surfaces at a point (used only if no roof is linked to the building's EGID)."""
    return identify(e, n, [config.SOLAR_LAYER], tolerance_px=tolerance_px)


def building_by_egid(egid: int) -> dict | None:
    hits = find(config.BUILDING_LAYER, "egid", egid)
    return (hits[0].get("attributes") or {}) if hits else None


# ---------------------------------------------------------------------------
# Helpers
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


def wgs84_to_lv95(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 -> Swiss LV95 (E, N), swisstopo approximate formulas (~1 m)."""
    phi = (lat * 3600 - 169028.66) / 10000
    lam = (lon * 3600 - 26782.5) / 10000
    e = (2600072.37 + 211455.93 * lam - 10938.51 * lam * phi - 0.36 * lam * phi * phi
         - 44.54 * lam ** 3)
    n = (1200147.07 + 308807.95 * phi + 3745.25 * lam * lam + 76.63 * phi * phi
         - 194.56 * lam * lam * phi + 119.79 * phi ** 3)
    return e, n


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
