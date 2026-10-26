"""Evaluate a running SlothBotanist server on sample pantries and write real numbers.

Usage:
  uvicorn main:app &            # with SERPAPI_KEY set and a model loaded
  python eval_brews.py [http://localhost:8000]

Reports, per case and overall: engines succeeded, pantry violations, allergen blocks,
withheld rate and latency. Allergy cases also assert the safety rule: a blocked item must
never appear in the finished recipe.
"""
import json
import sys
import time

import requests

from apothecary_core import allergen_hits, resolve_allergies

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

CASES = [
    {"name": "cold-basic", "pantry_items": ["fresh ginger", "lemon peel", "cinnamon stick", "dried mint", "honey"],
     "wellness_goal": "soothing drink for a cold evening"},
    {"name": "digestion", "pantry_items": ["fennel seeds", "dried mint", "orange peel", "black tea bag"],
     "wellness_goal": "gentle after-dinner digestion drink"},
    {"name": "energy-morning", "pantry_items": ["green tea bag", "lemon", "ginger", "frozen berries", "oats"],
     "wellness_goal": "clean morning energy"},
    {"name": "sleep", "pantry_items": ["chamomile tea", "dried lavender", "honey", "cinnamon stick"],
     "wellness_goal": "calming bedtime drink"},
    {"name": "hydration", "pantry_items": ["cucumber", "mint leaves", "lime", "frozen strawberries"],
     "wellness_goal": "refreshing hydration for a hot day"},
    {"name": "leftovers", "pantry_items": ["half a cinnamon stick", "two clove", "apple peel", "tea bags"],
     "wellness_goal": "use up leftovers in a warming drink"},
    # Allergy cases: expect_blocked items must be removed and must never show up in the output.
    {"name": "tree-nut", "pantry_items": ["fresh ginger", "almond milk", "walnuts", "cinnamon stick", "oat milk"],
     "wellness_goal": "creamy warming drink", "allergies": ["tree nuts"], "expect_blocked": ["almond milk", "walnuts"]},
    {"name": "dairy", "pantry_items": ["butter", "whole milk", "turmeric", "black pepper", "coconut cream"],
     "wellness_goal": "golden latte", "allergies": ["dairy"], "expect_blocked": ["butter", "whole milk"]},
    {"name": "ragweed", "pantry_items": ["chamomile tea", "dried mint", "lemon", "honey"],
     "wellness_goal": "relaxing evening tea", "allergies": ["ragweed"], "expect_caution": ["chamomile tea"]},
    {"name": "custom-kiwi", "pantry_items": ["kiwi slices", "mint leaves", "lime", "cucumber"],
     "wellness_goal": "green refresher", "allergies": ["kiwi"], "expect_blocked": ["kiwi slices"]},
]


def run_case(case):
    body = {k: v for k, v in case.items() if k in ("pantry_items", "wellness_goal", "allergies")}
    t0 = time.time()
    r = requests.post(f"{BASE}/api/brew", json=body, timeout=300)
    ms = int((time.time() - t0) * 1000)
    row = {"name": case["name"], "http": r.status_code, "ms": ms, "problems": []}
    try:
        data = r.json()
    except ValueError:
        row["problems"].append("non-JSON response")
        return row
    if r.status_code != 200:
        row["problems"].append(f"HTTP {r.status_code}: {str(data)[:120]}")
        return row

    report = data.get("engine_report", [])
    row["status"] = data.get("status")
    row["engines_ok"] = sum(1 for e in report if e["status"] in ("success", "cache_hit", "fallback_cache"))
    row["engines_total"] = len(report)
    row["sources"] = len(data.get("all_sources", []))
    row["pantry_violations"] = len(data.get("pantry_violations", []))
    row["seasonality"] = bool(data.get("seasonality"))
    al = data.get("allergies", {})
    row["blocked"] = [b["item"] for b in al.get("blocked_items", [])]
    row["cautions"] = [c["item"] for c in al.get("cross_reactivity_cautions", [])]
    row["regenerated"] = al.get("regenerated", False)

    text = data.get("elixirs") or ""
    for item in case.get("expect_blocked", []):
        if item not in row["blocked"]:
            row["problems"].append(f"expected '{item}' to be blocked")
    # Independent re-check of the finished recipe with the same detector (plant milks and
    # nutmeg are handled by it), so a leak would fail the run even if the server missed it.
    if text and case.get("allergies"):
        leaks = allergen_hits(text, resolve_allergies(case["allergies"]))
        if leaks:
            row["problems"].append(f"allergen terms in the recipe: {leaks}")
    for item in case.get("expect_caution", []):
        if item not in row["cautions"]:
            row["problems"].append(f"expected a cross-reactivity caution for '{item}'")
    return row


def main():
    rows = []
    for case in CASES:
        try:
            row = run_case(case)
        except requests.RequestException as e:
            row = {"name": case["name"], "problems": [f"request failed: {e}"]}
        rows.append(row)
        flag = "OK " if not row["problems"] else "BAD"
        print(f"[{flag}] {row['name']:<16} {row.get('status', '-'):<9} "
              f"engines {row.get('engines_ok', '-')}/{row.get('engines_total', '-')}  "
              f"sources {row.get('sources', '-')}  {row.get('ms', '-')} ms  {'; '.join(row['problems'])}")

    done = [r for r in rows if "status" in r]
    allergy_rows = [r for r, c in zip(rows, CASES) if c.get("allergies") and "status" in r]
    summary = {
        "cases": len(rows),
        "completed": len(done),
        "withheld": sum(1 for r in done if r["status"] == "withheld"),
        "avg_engines_ok": round(sum(r["engines_ok"] for r in done) / len(done), 2) if done else None,
        "avg_sources": round(sum(r["sources"] for r in done) / len(done), 1) if done else None,
        "total_pantry_violations": sum(r["pantry_violations"] for r in done),
        "allergy_cases": len(allergy_rows),
        "allergy_cases_clean": sum(1 for r in allergy_rows if not r["problems"]),
        "items_blocked": sum(len(r["blocked"]) for r in done),
        "avg_latency_ms": round(sum(r["ms"] for r in done) / len(done)) if done else None,
    }
    print("\n" + json.dumps(summary, indent=2))
    with open("eval_report.json", "w") as f:
        json.dump({"summary": summary, "cases": rows}, f, indent=2)
    print("Saved eval_report.json")
    sys.exit(1 if any(r["problems"] for r in rows) else 0)


if __name__ == "__main__":
    main()
