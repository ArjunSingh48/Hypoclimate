"""Disaster test: does HypoClimate flag places where real disasters happened?

Input: data/disaster_tests.csv with columns
  address, event, hazard, expected
  hazard   = a hazard key (e.g. river_flood_100, surface_runoff, rockfall) or "physical"
  expected = "flagged" (level medium or high / score >= 3) or "clean" (level low / score <= 2)
Usage (on your laptop, live data):
  python -m backend.disaster_test data/disaster_tests.csv
"""
from __future__ import annotations

import argparse
import csv

from . import engine


def check(row: dict, mode: str) -> dict:
    out = {"address": row["address"], "event": row.get("event", ""),
           "hazard": row["hazard"], "expected": row["expected"]}
    try:
        r = engine.score(row["address"], mode=mode)
        if row["hazard"] == "physical":
            got = r["scores"]["physical"]
            flagged = got is not None and got >= 3
        else:
            got = r["hazards"][row["hazard"]]["level"]
            flagged = got in ("medium", "high")
        out["got"] = got
        if got in (None, "unknown"):
            out["result"] = "NO DATA"
        else:
            out["result"] = "PASS" if flagged == (row["expected"] == "flagged") else "FAIL"
    except Exception as exc:
        out.update({"got": str(exc)[:120], "result": "ERROR"})
    return out


def run(rows: list[dict], mode: str = "live") -> list[dict]:
    return [check(r, mode) for r in rows]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input")
    p.add_argument("--mode", choices=["live", "example"], default="live")
    a = p.parse_args()
    with open(a.input, newline="", encoding="utf-8") as f:
        results = run(list(csv.DictReader(f)), a.mode)
    for r in results:
        print(f"{r['result']:8} {r['address']} | {r['event']} | {r['hazard']} "
              f"expected {r['expected']}, got {r['got']}")
    passed = sum(r["result"] == "PASS" for r in results)
    print(f"\n{passed} of {len(results)} passed")


if __name__ == "__main__":
    main()
