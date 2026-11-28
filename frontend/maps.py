"""Maps with official swisstopo base maps and federal hazard layers (WMS).

The map tiles load in the user's browser directly from geo.admin.ch.
"""
import folium

BASE_TILES = ("https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-grau/default/"
              "current/3857/{z}/{x}/{y}.jpeg")
ATTRIBUTION = "© swisstopo, FOEN, MeteoSwiss (geo.admin.ch)"
WMS_URL = "https://wms.geo.admin.ch/"

OVERLAYS = {
    "River flood 100-yr": "ch.bafu.aquaprotect_100",
    "Extreme flood 300-yr+": "ch.bafu.aquaprotect_500",
    "Surface runoff": "ch.bafu.gefaehrdungskarte-oberflaechenabfluss",
    "Hail 50-yr": "ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre",
    "Storm 50-yr": "ch.bafu.sturm-boeenspitzen_50",
    "Rockfall": "ch.bafu.silvaprotect-sturz",
    "Avalanche": "ch.bafu.silvaprotect-lawinen",
    "Solar roofs": "ch.bfe.solarenergie-eignung-daecher",
}
LEGEND_URL = "https://api3.geo.admin.ch/static/images/legends/{layer}_en.png"
SCORE_COLOUR = {1: "#2e7d32", 2: "#2e7d32", 3: "#ef6c00", 4: "#c62828", 5: "#7f0000"}


def _base(lat, lon, zoom):
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None, control_scale=True)
    folium.TileLayer(BASE_TILES, attr=ATTRIBUTION, name="swisstopo map").add_to(m)
    return m


def address_map(lat: float, lon: float, label: str, shown=("River flood 100-yr",)):
    m = _base(lat, lon, 16)
    for name, layer in OVERLAYS.items():
        folium.WmsTileLayer(WMS_URL, layers=layer, fmt="image/png", transparent=True,
                            name=name, attr=ATTRIBUTION, opacity=0.6,
                            show=name in shown).add_to(m)
    folium.Marker([lat, lon], tooltip=label).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def portfolio_map(points: list[dict]):
    """points: dicts with lat, lon, label, physical (1-5 or None)."""
    lat = sum(p["lat"] for p in points) / len(points)
    lon = sum(p["lon"] for p in points) / len(points)
    m = _base(lat, lon, 9)
    for p in points:
        folium.CircleMarker([p["lat"], p["lon"]], radius=5, weight=0, fill=True,
                            fill_opacity=0.8, fill_color=SCORE_COLOUR.get(p["physical"], "#9e9e9e"),
                            tooltip=p["label"]).add_to(m)
    return m


def legend_html(names=None) -> str:
    """Official geo.admin.ch legend images for the map layers, on white so they read in dark mode.

    Like the map tiles, the images load in the user's browser directly from geo.admin.ch.
    """
    items = "".join(
        f"<div style='break-inside:avoid;margin:0 0 10px'>"
        f"<div style='font-size:12px;font-weight:600;color:#1d1d1d;margin-bottom:3px'>{name}</div>"
        f"<img src='{LEGEND_URL.format(layer=layer)}' alt='Legend: {name}' "
        f"style='max-width:100%;height:auto'></div>"
        for name, layer in OVERLAYS.items() if names is None or name in names)
    return (f"<div style='background:#fff;border-radius:6px;padding:10px 12px;"
            f"column-count:2;column-gap:16px'>{items}</div>")
