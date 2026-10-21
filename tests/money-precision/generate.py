"""Generate monetary-precision edge cases for the order-matching solver.

One sub-case directory per scenario, each with:
  order_headers.csv  (id,total_price,total_lines)
  order_lines.csv    (description,price)
  expected.json      {"expect_solvable": bool, "ground_truth": {...} or null}

Cases (prices positive, exactly 2 decimals; 1-10 lines per header):
  x99-chains          .99-ending prices whose bundle sums force cent carry
                      chains (e.g. 5 x 9.99 = 49.95)
  large-totals        line prices 500.00-9999.99, k=10 headers totaling
                      ~50,000.00 each
  one-cent-difference two bundles whose sums differ by exactly 0.01; each
                      header's target matches only its own bundle (decoy
                      near-misses at -0.01 and +0.01)
  float-hostile-sums  huge prices whose naive IEEE-754 float sum drifts by
                      >= 0.01 from the exact decimal sum, while the exact
                      cent bookkeeping stays perfect
  one-cent-gap        INFEASIBLE: every k-line bundle misses the target by
                      at least 0.01, the closest by exactly 0.01

All targets are computed with exact integer cents.  Every emitted price
string is verified to round-trip through the harness's own conversion
(cents = round(float(value) * 100)) so that generator, solver and validator
agree on every cent.  Float drift >= 0.01 is only reachable at ~10^13-dollar
magnitudes (drift bound ~ N * ulp(total) / 2), which is why the
float-hostile case uses astronomically large but still exactly
round-trip-safe prices; at ordinary magnitudes the drift is nonzero but far
below 0.01 (measured and reported for every bundle below).

Run: python3 -I tests/money-precision/generate.py
"""

import csv
import json
import os
import random
from fractions import Fraction
from itertools import combinations

SEED = 20251021
BASE = os.path.dirname(os.path.abspath(__file__))

# float-hostile line-price band, in cents (5e12 to 1.5e13 dollars per line)
FLOAT_HOSTILE_LO = 5 * 10 ** 14
FLOAT_HOSTILE_HI = 15 * 10 ** 14

ADJ = ["Aggregate", "Balanced", "Configurable", "Cross-platform", "Customizable",
       "Distributed", "Enhanced", "Future-proofed", "Grass-roots", "Horizontal",
       "Inverse", "Managed", "Multi-tiered", "Open-architected", "Persistent",
       "Reduced", "Secured", "Stand-alone", "Synchronized", "Up-sized"]
NOUN = ["account", "advance", "balance", "budget", "clearance", "commission",
        "debit", "deposit", "disbursement", "escrow", "fee", "invoice",
        "ledger", "payroll", "premium", "rebate", "receipt", "refund",
        "settlement", "tariff"]


def make_descs(rng, n):
    seen, out = set(), []
    while len(out) < n:
        d = f"{rng.choice(ADJ)} {rng.choice(NOUN)}"
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def price_str(cents):
    s = f"{cents / 100:.2f}"
    # The harness parses every price with round(float(value) * 100); each
    # emitted value must survive that round trip bit-exactly.
    assert cents > 0 and round(float(s) * 100) == cents, (cents, s)
    return s


def float_sum_drift(cents_list):
    """Naive left-to-right IEEE-754 float sum of the emitted price strings
    versus the exact decimal sum.

    Returns (float_sum_dollars, drift_cents); the drift is computed with
    exact rational arithmetic so the measurement itself never loses cents.
    """
    fs = 0.0
    for c in cents_list:
        fs += float(price_str(c))
    drift = float((Fraction(fs) - Fraction(sum(cents_list), 100)) * 100)
    return fs, drift


def write_case(name, headers, lines, gt, expect_solvable):
    out = os.path.join(BASE, name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, total, k in headers:
            w.writerow([hid, price_str(total), k])
    with open(os.path.join(out, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for d, c in lines:
            w.writerow([d, price_str(c)])
    with open(os.path.join(out, "expected.json"), "w") as f:
        json.dump({"expect_solvable": expect_solvable,
                   "ground_truth": (None if gt is None
                                    else {str(h): sorted(v)
                                          for h, v in gt.items()})},
                  f, indent=2)
        f.write("\n")


def final_check(name, headers, lines, gt, expect_solvable):
    by_desc = dict(lines)
    assert len(by_desc) == len(lines), f"{name}: duplicate descriptions"
    assert all(c > 0 for c in by_desc.values()), f"{name}: non-positive price"
    assert all(1 <= k <= 10 for _, _, k in headers), f"{name}: bad total_lines"
    if gt is not None:
        used = set()
        for hid, total, k in headers:
            ds = gt[hid]
            assert len(ds) == k and len(set(ds)) == k, f"{name}: header {hid}"
            assert not (set(ds) & used), f"{name}: line reused by header {hid}"
            assert sum(by_desc[d] for d in ds) == total, \
                f"{name}: header {hid} truth sum != total"
            used |= set(ds)


def build_x99(rng):
    """Prices all ending in .99; k-line sums end in .(100-k) via carry."""
    ks = [5, 4, 3]
    prices = rng.sample([c for c in range(199, 50000) if c % 100 == 99], 16)
    bundles, i = [], 0
    for k in ks:
        bundles.append(prices[i:i + k])
        i += k
    decoys = prices[i:]                       # .99 prices in no truth bundle
    descs = make_descs(rng, len(prices))
    headers, gt, lines, notes = [], {}, [], []
    idx = 0
    for hid, (k, bundle) in enumerate(zip(ks, bundles), start=1):
        assert all(c % 100 == 99 for c in bundle)
        total = sum(bundle)                   # exact carry chain in cents
        ds, idx = descs[idx:idx + k], idx + k
        headers.append((hid, total, k))
        gt[hid] = ds
        lines += list(zip(ds, bundle))
        fs, drift = float_sum_drift(bundle)
        notes.append(f"header {hid}: {k} x .99 lines -> exact total "
                     f"{total / 100:.2f}; naive float sum {fs!r} "
                     f"(drift {drift:+.6g} cents vs exact)")
    lines += list(zip(descs[idx:], decoys))
    return ("x99-chains", headers, lines, gt, True, notes)


def build_large(rng):
    """k=10 headers, line prices 500.00-9999.99, totals ~50,000.00."""
    headers, gt, lines, notes = [], {}, [], []
    for hid in (1, 2):
        while True:
            bundle = rng.sample(range(50000, 1000000), 10)  # 500.00-9999.99
            total = sum(bundle)
            if 4500000 <= total <= 6000000:                 # ~ 50,000.00
                break
        ds = make_descs(rng, 10)
        headers.append((hid, total, 10))
        gt[hid] = ds
        lines += list(zip(ds, bundle))
        notes.append(f"header {hid}: 10 lines of 500.00-9999.99, "
                     f"exact total {total / 100:.2f}")
    decoys = rng.sample(range(50000, 1000000), 2)
    lines += list(zip(make_descs(rng, 2), decoys))
    return ("large-totals", headers, lines, gt, True, notes)


def build_one_cent(rng):
    """Bundle P sums to T, decoy Q to T-0.01, decoy R to T+0.01; header 1
    (total T) is matched only by P, header 2 (total T-0.01) only by Q."""
    for _ in range(5000):
        pool = rng.sample(range(1000, 90000), 15)          # 10.00-900.00
        p1, p2, p3, q1, q2, r1, r2 = pool[:7]
        decoy = pool[7:10]
        T = p1 + p2 + p3
        q3, r3 = T - 1 - q1 - q2, T + 1 - r1 - r2
        if not (0 < q3 < 5 * 10 ** 5 and 0 < r3 < 5 * 10 ** 5):
            continue
        prices = [p1, p2, p3, q1, q2, q3, r1, r2, r3] + decoy
        if len(set(prices)) != len(prices):
            continue
        hit_T, hit_Tm1 = [], []
        for combo in combinations(range(len(prices)), 3):
            s = sum(prices[i] for i in combo)
            if s == T:
                hit_T.append(combo)
            elif s == T - 1:
                hit_Tm1.append(combo)
        # P (lines 0,1,2) and Q (lines 3,4,5) must be the unique candidates.
        if len(hit_T) == 1 and len(hit_Tm1) == 1:
            descs = make_descs(rng, 12)
            headers = [(1, T, 3), (2, T - 1, 3)]
            gt = {1: descs[0:3], 2: descs[3:6]}
            lines = list(zip(descs, prices))
            notes = [f"header 1 target {T / 100:.2f}: only bundle P matches; "
                     f"decoys Q ({(T - 1) / 100:.2f}) and R "
                     f"({(T + 1) / 100:.2f}) are 0.01 away",
                     f"header 2 target {(T - 1) / 100:.2f}: only bundle Q "
                     f"matches (exactly 0.01 below header 1's target)"]
            return ("one-cent-difference", headers, lines, gt, True, notes)
    raise AssertionError("could not build one-cent-difference case")


def build_float_hostile(rng):
    """A k=10 bundle whose naive IEEE-754 float sum drifts by >= 0.01 from
    the exact decimal sum, while the exact cent bookkeeping (and the
    harness's round(float(s) * 100) conversion for every emitted value,
    including the ~1e13-dollar header total) still round-trips exactly.

    The magnitude band is the largest at which every emitted 2-decimal
    value survives round(float(s) * 100) bit-exactly:
      ulp(dollars) / 2 * 100 < 0.5 cents  ->  dollars < ~7e13.
    A near-miss decoy bundle sums to exactly target - 0.01.
    """
    while True:
        bundle = sorted(rng.sample(range(FLOAT_HOSTILE_LO, FLOAT_HOSTILE_HI),
                                   10), reverse=True)
        target = sum(bundle)
        if target > 89 * 10 ** 14:          # keep float(target)/100 exact
            continue
        fs, drift = float_sum_drift(bundle)
        if abs(drift) >= 1.0:               # >= 0.01 dollars of float drift
            break
    assert round(target / 100 * 100) == target

    while True:                             # decoy bundle: exact sum = target - 1 cent
        d9 = rng.sample(range(FLOAT_HOSTILE_LO, FLOAT_HOSTILE_HI), 9)
        last = target - 1 - sum(d9)
        if FLOAT_HOSTILE_LO <= last <= FLOAT_HOSTILE_HI and last not in d9:
            break
    decoy = d9 + [last]
    assert sum(decoy) == target - 1

    headers = [(1, target, 10)]
    descs = make_descs(rng, 20)
    gt = {1: descs[:10]}
    lines = list(zip(descs[:10], bundle)) + list(zip(descs[10:], decoy))
    notes = [f"header 1: 10 lines of ${FLOAT_HOSTILE_LO / 100:.3g}-"
             f"${FLOAT_HOSTILE_HI / 100:.3g}; exact sum "
             f"{sum(bundle) / 100:.2f}; NAIVE FLOAT sum {fs!r} differs from "
             f"the exact decimal sum by {drift:+.4g} cents "
             f"(>= 0.01 dollars)",
             "decoy bundle of 10 lines sums to exactly target - 0.01: a "
             "solver that compares float sums with any 0.01 tolerance "
             "cannot separate truth from decoy"]
    return ("float-hostile-sums", headers, lines, gt, True, notes)


def build_gap(rng):
    """INFEASIBLE: single header whose target is missed by every 3-line
    bundle; the closest bundles sit exactly one cent (0.01) away."""
    while True:
        prices = rng.sample(range(2000, 200000), 12)
        sums = {}
        for combo in combinations(range(12), 3):
            sums.setdefault(sum(prices[i] for i in combo), []).append(combo)
        keys = sorted(sums)
        cands = [s for s in keys[1:-1] if s + 1 not in sums]
        if not cands:
            continue
        both = [s for s in cands if s + 2 in sums]   # one-cent miss on both sides
        chosen_pool = both or cands
        s = chosen_pool[len(chosen_pool) // 2]
        target = s + 1
        break
    assert target not in sums and min(abs(x - target) for x in keys) == 1
    descs = make_descs(rng, 12)
    lines = list(zip(descs, prices))
    notes = [f"INFEASIBLE: no 3-line bundle sums to {target / 100:.2f}; the "
             f"closest bundle(s) miss by exactly 0.01 "
             f"({s / 100:.2f} attained"
             + (f", {target / 100 + 0.01:.2f} also attained" if s + 2 in sums
                else "") + ")",
             "a solver that verifies bundle sums with a 0.01 tolerance would "
             "wrongly claim a matching here"]
    return ("one-cent-gap", [(1, target, 3)], lines, None, False, notes)


def main():
    rng = random.Random(SEED)
    cases = [build_x99(rng), build_large(rng), build_one_cent(rng),
             build_float_hostile(rng), build_gap(rng)]
    for name, headers, lines, gt, expect, notes in cases:
        final_check(name, headers, lines, gt, expect)
        write_case(name, headers, lines, gt, expect)
        print(f"wrote {name}: {len(headers)} header(s), {len(lines)} "
              f"line(s), expect_solvable={expect}")
        for note in notes:
            print(f"  - {note}")


if __name__ == "__main__":
    main()