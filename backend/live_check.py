"""Live check: query real federal data for a list of addresses and report what came back.

Usage (on a laptop with internet, in the Hypoclimate folder):
    python3 -m backend.live_check data/test_addresses.csv

For every address it prints which address was matched, every hazard, the building,
the solar roof, the scores, and any error or warning. Everything, including the raw
API answers, is also saved to data/live_runs/run_<date_time>.json for checking.
Nothing here is stored or invented: every value comes from the live services.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime

from . import engine, geoadmin

SHORT = {"river_flood_100": "flood100", "extreme_flood_300plus": "flood300",
         "surface_runoff": "runoff", "hail_50y": "hail", "storm_50y": "storm",
         "rockfall": "rockfall", "avalanche": "avalanche"}


def check(address: str) -> dict:
    t0 = time.perf_counter()
    out = {"input": address}
    try:
        out["candidates"] = [" ".join(c.get("label", "").replace("<b>", "").replace("</b>", "").split())
                             for c in geoadmin.search_candidates(address, limit=3)]
    except Exception as exc:
        out["candidates"] = [f"search error: {str(exc)[:80]}"]
    try:
        facts = engine.collect(address, mode="live")
        out["facts"] = facts
        out["result"] = engine.evaluate(facts, 1_000_000, 650_000)
        out["status"] = "ok"
    except Exception as exc:
        out.update({"status": "error", "error": str(exc)[:300]})
    out["seconds"] = round(time.perf_counter() - t0, 2)
    return out


def show(o: dict) -> None:
    print("=" * 100)
    print(f"INPUT     {o['input']}   ({o['seconds']} s)")
    print(f"SEARCH    top results: {' | '.join(o['candidates']) or 'none'}")
    if o["status"] != "ok":
        print(f"ERROR     {o['error']}")
        return
    r, f = o["result"], o["facts"]
    print(f"MATCHED   {r['address']}  · EGID {r['egid']} · via {f.get('address_source')}"
          f" · {f.get('match_note')}")
    print("HAZARDS   " + "  ".join(f"{SHORT[k]}={h['level']}({h['finding']})"
                                   for k, h in r["hazards"].items()))
    b, en = r["building"], r["energy"]
    print(f"BUILDING  built {b.get('period_label')} · floors {b.get('floors')} · flats {b.get('flats')}"
          f" · heating {b.get('energy_source')}")
    print(f"ENERGY    heat demand {en.get('heat_demand_kwh')} kWh/yr · best roof {en.get('roof_area_m2')} m²"
          f" {en.get('roof_class')} {en.get('solar_kwh')} kWh/yr · roofs {en.get('roofs')}"
          f" · matched to building: {en.get('matched_building')}")
    s = r["scores"]
    print(f"SCORES    physical {s['physical']} · transition {s['transition']} · drivers {s['main_drivers']}")
    for k, v in (f.get("errors") or {}).items():
        print(f"ERROR     {k}: {v}")
    for w in f.get("warnings") or []:
        print(f"WARNING   {w}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="CSV with a column 'address'")
    a = p.parse_args()
    with open(a.input, newline="", encoding="utf-8") as fh:
        addresses = [row["address"] for row in csv.DictReader(fh) if row.get("address")]
    runs = []
    for addr in addresses:
        o = check(addr)
        show(o)
        runs.append(o)
    ok = [o for o in runs if o["status"] == "ok"]
    full = [o for o in ok if not o["facts"].get("errors")
            and all(h["level"] != "unknown" for h in o["result"]["hazards"].values())
            and o["result"]["building"]]
    print("=" * 100)
    print(f"SUMMARY   {len(ok)}/{len(runs)} addresses found · {len(full)}/{len(runs)} complete "
          f"(all 7 hazards + building, no errors) · "
          f"{sum(len(o['facts'].get('warnings') or []) for o in ok)} warnings · "
          f"avg {sum(o['seconds'] for o in runs) / max(len(runs), 1):.1f} s per address")
    os.makedirs("data/live_runs", exist_ok=True)
    path = f"data/live_runs/run_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(runs, fh, indent=2, ensure_ascii=False, default=str)
    print(f"SAVED     {path}  (send this file for checking)")


if __name__ == "__main__":
    main()
