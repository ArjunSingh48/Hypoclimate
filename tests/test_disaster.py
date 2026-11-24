import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



BERN = "Gerberngasse 20, 3011 Bern"


def test_disaster_test_example():
    from backend import disaster_test
    rows = [{"address": BERN, "event": "Aare 2005", "hazard": "river_flood_100", "expected": "flagged"},
            {"address": "Zürichbergstrasse 221", "event": "control", "hazard": "river_flood_100",
             "expected": "clean"},
            {"address": "Zürichbergstrasse 221", "event": "control", "hazard": "hail_50y",
             "expected": "clean"}]
    res = disaster_test.run(rows, "example")
    assert [x["result"] for x in res] == ["PASS", "PASS", "NO DATA"]
