import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import batch  # noqa: E402

BERN = "Gerberngasse 20, 3011 Bern"


def test_batch_example():
    rows = [{"address": BERN, "property_value": "1250000", "mortgage": "800000"},
            {"address": "Zürichbergstrasse 221", "property_value": "", "mortgage": ""},
            {"address": "Nowhere 1", "property_value": "", "mortgage": ""}]
    results, summary = batch.run(rows, mode="example")
    assert [r["status"] for r in results] == ["ok", "ok", "error"]
    assert summary["scored"] == 2 and summary["complete"] == 1
