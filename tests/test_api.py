import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from backend import api  # noqa: E402

BERN = "Gerberngasse 20, 3011 Bern"


def test_api():
    client = TestClient(api.app)
    ok = client.get("/score", params={"address": BERN, "value": 1250000,
                                      "mortgage": 800000, "mode": "example"})
    assert ok.status_code == 200 and ok.json()["scores"]["physical"] == 4
    assert client.get("/score", params={"address": "x", "mode": "example"}).status_code == 404
