import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import engine  # noqa: E402

BERN = "Gerberngasse 20, 3011 Bern"


def test_advisor_report():
    from backend import report
    r = engine.score(BERN, 1_250_000, 800_000, mode="example")
    adv = report.advisor_report(r, "Client A", "Advisor B")
    assert "Gerberngasse 20" in adv and "100-year river flood area" in adv
    assert "Information, not advice" in adv
