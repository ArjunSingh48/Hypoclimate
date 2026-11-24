"""Mortgage-book view: score many loans and sum them up for the bank dashboard."""
from __future__ import annotations

import time
from collections import Counter

from . import engine
from . import example_portfolio

HIGH_OVERALL = {"physical_min": 4, "transition_min": 3}  # both conditions must hold


def score_example_book(n_loans: int = 240) -> list[dict]:
    rows = []
    for loan in example_portfolio.build(n_loans):
        r = engine.evaluate(loan["facts"], loan["property_value"], loan["mortgage"])
        rows.append({"loan_id": loan["loan_id"], "town": loan["town"],
                     "exposure": loan["mortgage"], "result": r, "status": "ok"})
    return rows


def score_csv_rows(rows: list[dict], mode: str) -> list[dict]:
    out = []
    for i, row in enumerate(rows):
        t0 = time.perf_counter()
        rec = {"loan_id": row.get("loan_id") or f"L-{i + 1}",
               "town": "", "exposure": _num(row.get("mortgage")) or 0}
        try:
            rec["result"] = engine.score(row["address"], _num(row.get("property_value")),
                                         _num(row.get("mortgage")), mode=mode)
            rec["status"] = "ok"
        except Exception as exc:
            rec.update({"result": None, "status": "error", "error": str(exc)[:200],
                        "address": row.get("address", "")})
        rec["seconds"] = round(time.perf_counter() - t0, 3)
        out.append(rec)
    return out


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def summarize(book: list[dict]) -> dict:
    ok = [b for b in book if b["status"] == "ok"]
    total_n = len(ok) or 1
    total_chf = sum(b["exposure"] for b in ok) or 1

    def share(pred):
        sel = [b for b in ok if pred(b["result"])]
        return {"loans": len(sel), "pct": round(100 * len(sel) / total_n, 1),
                "chf": sum(b["exposure"] for b in sel),
                "chf_pct": round(100 * sum(b["exposure"] for b in sel) / total_chf, 1)}

    def high_overall(r):
        s = r["scores"]
        return (s["physical"] or 0) >= HIGH_OVERALL["physical_min"] and \
               (s["transition"] or 0) >= HIGH_OVERALL["transition_min"]

    kpis = {
        "flood_100": share(lambda r: r["hazards"]["river_flood_100"]["level"] == "high"),
        "runoff": share(lambda r: r["hazards"]["surface_runoff"]["level"] != "low"
                        and r["hazards"]["surface_runoff"]["level"] != "unknown"),
        "fossil": share(lambda r: r["building"].get("energy_source") in ("oil", "gas")),
        "high_overall": share(high_overall),
    }
    levels = {}
    for key, label in [("river_flood_100", "River flood"), ("surface_runoff", "Surface runoff"),
                       ("hail_50y", "Hail"), ("storm_50y", "Storm"), ("rockfall", "Rockfall")]:
        c = Counter(b["result"]["hazards"][key]["level"] for b in ok)
        levels[label] = {lvl: round(100 * c.get(lvl, 0) / total_n, 1)
                         for lvl in ("low", "medium", "high", "unknown")}
    heating = Counter(b["result"]["building"].get("energy_source") or "unknown" for b in ok)
    top = sorted(ok, key=lambda b: ((b["result"]["scores"]["physical"] or 0)
                                    + (b["result"]["scores"]["transition"] or 0),
                                    b["exposure"]), reverse=True)[:10]
    secs = [b["seconds"] for b in book if "seconds" in b]
    return {
        "loans": len(book), "scored": len(ok),
        "coverage_pct": round(100 * len(ok) / (len(book) or 1), 1),
        "exposure_chf": sum(b["exposure"] for b in ok),
        "kpis": kpis, "hazard_levels": levels,
        "heating_mix": {k: round(100 * v / total_n, 1) for k, v in heating.most_common()},
        "top_risk": [{"loan": b["loan_id"], "where": b["town"] or b["result"]["address"],
                      "exposure_chf": b["exposure"],
                      "ltv_pct": b["result"]["chf"]["ltv_today_pct"],
                      "physical": b["result"]["scores"]["physical"],
                      "transition": b["result"]["scores"]["transition"],
                      "main_driver": ", ".join(b["result"]["scores"]["main_drivers"]) or "–"}
                     for b in top],
        "avg_seconds": round(sum(secs) / len(secs), 3) if secs else None,
    }
