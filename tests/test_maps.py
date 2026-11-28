import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



BERN = "Gerberngasse 20, 3011 Bern"


def test_maps_build():
    from frontend import maps
    assert maps.address_map(46.9478, 7.4571, "x")._name == "Map"
    assert maps.portfolio_map([{"lat": 46.9, "lon": 7.4, "label": "a", "physical": 4}])._name == "Map"


def test_legend_for_every_map_layer():
    from frontend import maps
    html = maps.legend_html()
    for layer in maps.OVERLAYS.values():
        assert f"legends/{layer}_en.png" in html
