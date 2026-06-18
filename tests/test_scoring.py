#!/usr/bin/env python3
"""Step-3 scoring test (deterministic, offline — no Google calls)."""
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
    print("Step-3 scoring test")

    # all-in estimate
    allin, est = scoring.all_in_cost(17000, 30)
    check("all-in: 17000 + est(2700) = 19700, flagged estimated", allin == 19700 and est)
    check("all-in: None base -> (None, False)", scoring.all_in_cost(None, None) == (None, False))

    # hard filters — never reject on a guessed all-in (judge on base when estimated)
    check("filter: 17000 base, est all-in 19700, ceiling 18000 -> PASS (not rejected on guess)",
          scoring.passes_hard_filters("1+kk", 17000, 19700, True, ceiling=18000))
    check("filter: 19000 base over ceiling -> reject",
          not scoring.passes_hard_filters("1+kk", 19000, 21700, True, ceiling=18000))
    check("filter: no disposition -> reject",
          not scoring.passes_hard_filters(None, 15000, 17500, True, ceiling=18000))
    check("filter: real all-in 17500 under ceiling -> pass",
          scoring.passes_hard_filters("2+kk", 15000, 17500, False, ceiling=18000))

    # term normalizations
    check("commute: 0 min -> 1.0", approx(scoring.commute_score(0), 1.0))
    check("commute: 30 min -> 0.5", approx(scoring.commute_score(30), 0.5))
    check("commute: 90 min -> 0.0 (clamped)", approx(scoring.commute_score(90), 0.0))
    check("commute: None -> 0.0", approx(scoring.commute_score(None), 0.0))
    check("ppm: 300 -> 1.0", approx(scoring.price_per_m2_score(300), 1.0))
    check("ppm: 600 -> 0.5", approx(scoring.price_per_m2_score(600), 0.5))
    check("ppm: 900 -> 0.0", approx(scoring.price_per_m2_score(900), 0.0))
    check("district: Praha 7 -> 1.0", approx(scoring.district_score("Praha 7"), 1.0))
    check("district: Praha 5 -> 0.7", approx(scoring.district_score("Praha 5"), 0.7))
    check("district: Praha 9 (unlisted) -> 0.0", approx(scoring.district_score("Praha 9"), 0.0))

    # composite: 12-min commute, 16500/30 = 550 CZK/m², Praha 7
    total, bd = scoring.score(12, 550.0, "Praha 7")
    check("score: weighted sum = 0.775", approx(total, 0.775, 1e-3))
    check("score: breakdown carries minutes+ppm", bd["minutes"] == 12 and bd["ppm"] == 550.0)

    # a weak flat lands well below the 0.75 notify threshold
    weak, _ = scoring.score(50, 850.0, "Praha 9")
    check("score: weak flat < 0.75", weak < 0.75)

    # Prague 7 is commute-relaxed: a far P7 flat keeps a floored commute score, while the
    # same trip in another district is not floored.
    _, bd_p7 = scoring.score(55, 550.0, "Praha 7")
    _, bd_p5 = scoring.score(55, 550.0, "Praha 5")
    check("far P7 commute floored to RELAXED_COMMUTE_FLOOR",
          approx(bd_p7["commute"], config.RELAXED_COMMUTE_FLOOR))
    check("far P5 commute NOT floored", approx(bd_p5["commute"], scoring.commute_score(55)))
    p7_total, _ = scoring.score(55, 550.0, "Praha 7")
    p5_total, _ = scoring.score(55, 550.0, "Praha 5")
    check("same far flat ranks higher in P7 than P5", p7_total > p5_total)

    print("\nALL SCORING CHECKS PASSED")


if __name__ == "__main__":
    main()
