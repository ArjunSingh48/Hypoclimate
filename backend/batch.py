"""Score a whole mortgage book from a CSV file.

Input CSV columns: address, property_value, mortgage (values may be empty)
Usage:
    python -m backend.batch data/sample_portfolio.csv results.csv --mode example
    python -m backend.batch my_book.csv results.csv     (live mode, needs internet)
Prints coverage and speed at the end: this is the technical test.
"""
from __future__ import annotations

import argparse
import csv
import json
import time

from . import engine


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def run(rows: list[dict], mode: str = "live") -> tuple[list[dict], dict]:
    out, times = [], []
    for row in rows:
        t0 = time.perf_counter()
        rec = {"address": row.get("address", "")}
        try:
            r = engine.score(rec["address"], _num(row.get("property_value")),
                             _num(row.get("mortgage")), mode=mode)
            known = sum(h["level"] != "unknown" for h in r["hazards"].values())
            rec.update({
                "status": "ok",
                "physical": r["scores"]["physical"],
                "transition": r["scores"]["transition"],
                "main_drivers": "; ".join(r["scores"]["main_drivers"]),
                "flood_100": r["hazards"]["river_flood_100"]["level"],
                "runoff": r["hazards"]["surface_runoff"]["level"],
                "hail": r["hazards"]["hail_50y"]["level"],
                "storm": r["hazards"]["storm_50y"]["level"],
                "heating": r["building"].get("energy_source"),
                "hazards_known": f"{known}/{len(r['hazards'])}",
                "complete": known == len(r["hazards"]) and bool(r["building"]),
                "co2_levy_per_year": r["chf"]["co2_levy_per_year"],
                "ltv_today_pct": r["chf"]["ltv_today_pct"],
            })
        except Exception as exc:  # one bad address must not stop the whole book
            rec.update({"status": "error", "error": str(exc)[:200], "complete": False})
        rec["seconds"] = round(time.perf_counter() - t0, 3)
        times.append(rec["seconds"])
        out.append(rec)

    n = len(out)
    summary = {
        "addresses": n,
        "scored": sum(r["status"] == "ok" for r in out),
        "complete": sum(bool(r.get("complete")) for r in out),
        "coverage_pct": round(100 * sum(r["status"] == "ok" for r in out) / n, 1) if n else 0,
        "complete_pct": round(100 * sum(bool(r.get("complete")) for r in out) / n, 1) if n else 0,
        "avg_seconds": round(sum(times) / n, 3) if n else 0,
        "max_seconds": max(times) if times else 0,
        "mode": mode,
    }
    return out, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--mode", choices=["live", "example"], default="live")
    a = p.parse_args()
    with open(a.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    results, summary = run(rows, a.mode)
    fields = sorted({k for r in results for k in r}, key=lambda k: (k != "address", k))
    with open(a.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
