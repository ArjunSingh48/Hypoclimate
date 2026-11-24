import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



BERN = "Gerberngasse 20, 3011 Bern"


def test_example_portfolio_and_report():
    from backend import portfolio
    from backend import report
    book = portfolio.score_example_book(240)
    sm = portfolio.summarize(book)
    assert sm["scored"] == 240 and sm["coverage_pct"] == 100.0
    assert 0 < sm["kpis"]["flood_100"]["pct"] < 30
    assert abs(sum(sm["heating_mix"].values()) - 100) < 0.5
    assert len(sm["top_risk"]) == 10
    html = report.portfolio_report(sm, example=True)
    assert "EXAMPLE DATA" in html and "Highest-risk loans" in html
