#!/usr/bin/env python3
"""Scoring test for the v2 flat-share spec (deterministic, offline — no Google calls)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pragueflats import config, scoring  # noqa: E402


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def approx(a, b, tol=1e-3):
    return abs(a - b) <= tol


def main():
    print("Scoring test (spec v2 — flat-share)")

    # all-in estimate
    allin, est = scoring.all_in_cost(28000, 65)
    check("all-in: 28000 + est(5850) = 33850, flagged estimated", allin == 33850 and est)
    check("all-in: None base -> (None, False)", scoring.all_in_cost(None, None) == (None, False))
    check("all-in: real charges 30000+4500, not estimated",
          scoring.all_in_cost(30000, 70, 4500) == (34500, False))

    # layout allow-list: flatmate-viable only
    check("layout: 2+1 allowed", scoring.disposition_ok("2+1"))
    check("layout: 3+1 allowed", scoring.disposition_ok("3+1"))
    check("layout: 3+kk allowed (case-insensitive)", scoring.disposition_ok("3+KK"))
    check("layout: 2+kk rejected (one of us would sleep in the kitchen)",
          not scoring.disposition_ok("2+kk"))
    check("layout: 1+kk rejected", not scoring.disposition_ok("1+kk"))
    check("layout: 'Pokoj' (single room) rejected", not scoring.disposition_ok("Pokoj"))
    check("layout: None rejected", not scoring.disposition_ok(None))

    # hard filters — never reject on a guessed all-in (judge on base when estimated)
    check("filter: 30000 base, est all-in 35850, ceiling 32000 -> PASS (not rejected on guess)",
          scoring.passes_hard_filters("2+1", 30000, 35850, True, ceiling=32000))
    check("filter: 33000 base over ceiling -> reject",
          not scoring.passes_hard_filters("2+1", 33000, 38850, True, ceiling=32000))
    check("filter: real all-in 31500 under ceiling -> pass",
          scoring.passes_hard_filters("3+kk", 27000, 31500, False, ceiling=32000))
    check("filter: real all-in 32500 over ceiling -> reject",
          not scoring.passes_hard_filters("3+kk", 27000, 32500, False, ceiling=32000))
    check("filter: right price but 2+kk -> reject",
          not scoring.passes_hard_filters("2+kk", 25000, 29000, True, ceiling=32000))
    check("filter: default ceiling comes from config",
          scoring.passes_hard_filters("2+1", config.MAX_PRICE_ALLIN_CZK - 1, None, True))

    # term normalizations
    check("commute: 0 min -> 1.0", approx(scoring.commute_score(0), 1.0))
    check("commute: 30 min -> 0.5", approx(scoring.commute_score(30), 0.5))
    check("commute: 90 min -> 0.0 (clamped)", approx(scoring.commute_score(90), 0.0))
    check("commute: None -> 0.0", approx(scoring.commute_score(None), 0.0))
    check("ppm: 320 -> 1.0", approx(scoring.price_per_m2_score(320), 1.0))
    check("ppm: 510 -> 0.5", approx(scoring.price_per_m2_score(510), 0.5))
    check("ppm: 700 -> 0.0", approx(scoring.price_per_m2_score(700), 0.0))

    # preferred areas: Vinohrady by NEIGHBOURHOOD (spans Praha 2 + 3), P6/P7 by district
    check("area: Vinohrady in Praha 2 -> 1.0", approx(scoring.area_score("Praha 2", "Vinohrady"), 1.0))
    check("area: Vinohrady in Praha 3 -> 1.0", approx(scoring.area_score("Praha 3", "Vinohrady"), 1.0))
    check("area: Praha 6 -> 1.0", approx(scoring.area_score("Praha 6", "Dejvice"), 1.0))
    check("area: Praha 7 -> 1.0", approx(scoring.area_score("Praha 7", "Holešovice"), 1.0))
    check("area: Žižkov (Praha 3, not Vinohrady) -> 0.0",
          approx(scoring.area_score("Praha 3", "Žižkov"), 0.0))
    check("area: Praha 5 -> 0.0", approx(scoring.area_score("Praha 5", "Smíchov"), 0.0))
    check("area: unknown -> 0.0", approx(scoring.area_score(None, None), 0.0))

    # composite: 12-min commute (0.8), 510 CZK/m² (0.5), Vinohrady (1.0)
    total, bd = scoring.score(12, 510.0, "Praha 2", "Vinohrady")
    check("score: weighted sum = 0.77", approx(total, 0.77, 1e-3))
    check("score: breakdown carries minutes+ppm", bd["minutes"] == 12 and bd["ppm"] == 510.0)

    # a weak flat lands well below the notify threshold
    weak, _ = scoring.score(50, 680.0, "Praha 9", "Prosek")
    check("score: weak flat below notify threshold", weak < config.NOTIFY_THRESHOLD)

    # the same flat ranks higher inside a preferred area than outside it
    p7_total, _ = scoring.score(35, 480.0, "Praha 7", "Holešovice")
    p5_total, _ = scoring.score(35, 480.0, "Praha 5", "Smíchov")
    check("same flat ranks higher in P7 than P5", p7_total > p5_total)
    check("preferred-area margin equals the area weight",
          approx(p7_total - p5_total, scoring.WEIGHTS["area"]))

    # sanity: a realistic strong match clears the notify threshold
    strong, _ = scoring.score(25, 430.0, "Praha 2", "Vinohrady")
    check("realistic Vinohrady match clears notify threshold", strong >= config.NOTIFY_THRESHOLD)

    print("\nALL SCORING CHECKS PASSED")


if __name__ == "__main__":
    main()
