"""Generate minimal/baseline test cases for the order-matching solver.

Writes one sub-case directory per baseline scenario, each with:
  order_headers.csv  (id,total_price,total_lines)
  order_lines.csv    (description,price)
  expected.json      {"expect_solvable": bool, "ground_truth": {...}|null}

Cases:
  single-pair                 : 1 header k=1, exactly 1 line
  single-header-3-groups      : 1 header k=3, exactly 3 lines, no decoys
  extra-decoy-lines           : 2 headers + 3 unused decoy lines
  exact-partition             : every line consumed by exactly one header

All prices are positive with exactly 2 decimals; totals are computed from
the generated ground-truth lines as exact integer cents.

Run from the project root:  python3 -I tests/baseline-minimal/generate.py
"""

import csv
import json
import os
import random

SEED = 20241021
BASE = os.path.dirname(os.path.abspath(__file__))

ADJ = ["Adaptive", "Business-focused", "Centralized", "Customizable",
       "Decentralized", "Digitized", "Distributed", "Extended", "Integrated",
       "Innovative", "Networked", "Optimized", "Organic", "Organized",
       "Proactive", "Quality-focused", "Reactive", "Realigned",
       "Seamless", "Synergized"]
MID = ["24/7", "actuating", "asymmetric", "client-driven", "coherent",
       "composite", "dynamic", "even-keeled", "grid-enabled", "heuristic",
       "holistic", "interactive", "logistical", "mission-critical",
       "next-generation", "object-oriented", "optimal", "stable", "standalone"]
NOUN = ["array", "capacity", "circuit", "core", "database", "emulation",
        "firmware", "groupware", "hub", "instruction-set", "interface",
        "knowledge-base", "matrix", "monitoring", "neural-net", "portal",
        "pricing-structure", "product", "projection", "toolset"]


def unique_prices(rng, n, lo=100, hi=60000):
    """n distinct positive cent values (< 1s conflict with nothing here)."""
    return rng.sample(range(lo, hi + 1), n)


def unique_lines(rng, n):
    """n lines with distinct descriptions."""
    lines, seen = [], set()
    return_lines = []
    descs = set()
    while len(descs) < n:
        d = f"{rng.choice(ADJ)} {rng.choice(MID)} {rng.choice(NOUN)}"
        if d in descs:
            continue
        descs.add(d)
        return_lines.append(d)
    return return_lines


def write_case(name, headers, lines, ground_truth):
    """headers: [(id, total_cents, k)], lines: [(desc, cents)],
    ground_truth: {id: [desc, ...]} or None."""
    out = os.path.join(BASE, name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, total, k in headers:
            w.writerow([hid, f"{total / 100:.2f}", k])
    with open(os.path.join(out, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for d, c in lines:
            w.writerow([d, f"{c / 100:.2f}"])
    with open(os.path.join(out, "expected.json"), "w") as f:
        json.dump({"expect_solvable": True,
                   "ground_truth": (None if ground_truth is None
                                    else {str(k): v for k, v in
                                          ground_truth.items()})},
                  f, indent=2)
        f.write("\n")


def truth_sums(lines, gt):
    sums = {}
    for hid, descs in gt.items():
        desc_set = set(descs)
        sums[hid] = sum(c for d, c in lines if d in desc_set)
    return sums


def main():
    rng = random.Random(SEED)

    # 1. single-pair: 1 header, k=1, exactly 1 line.
    (d1,) = unique_lines(rng, 1)
    p = unique_prices(rng, 1)[0]
    lines1 = [(d1, p)]
    gt1 = {1: [d1]}
    write_case("single-pair", [(1, truth_sums(lines1, gt1)[1], 1)], lines1, gt1)

    # 2. single-header-3-groups: 1 header, k=3, exactly 3 lines.
    ds = unique_lines(rng, 3)
    ps = unique_prices(rng, 3)
    lines2 = list(zip(ds, ps))
    gt2 = {1: sorted(ds)}
    write_case("single-header-3-groups",
               [(1, truth_sums(lines2, gt2)[1], 3)], lines2, gt2)

    # 3. extra-decoy-lines: 2 headers (k=2, k=3) plus 3 decoy lines.
    ds = unique_lines(rng, 8)
    ps = unique_prices(rng, 8)
    truth3, decoy3 = ds[:5], ds[5:]
    lines3 = list(zip(ds, ps))
    by_name = dict(zip(ds, ps))
    gt3 = {1: sorted(truth3[:2]), 2: sorted(truth3[2:])}
    sums3 = truth_sums(lines3, gt3)
    headers3 = [(hid, sums3[hid], len(d)) for hid, d in gt3.items()]
    write_case("extra-decoy-lines", headers3, lines3, gt3)

    # 4. exact-partition: 3 headers consuming every line exactly once.
    ks = [1, 3, 4]
    assert sum(ks) == len(lines4 := list(zip(unique_lines(rng, 8),
                                             unique_prices(rng, 8))))
    gt4 = {}
    idx = 0
    for hid, k in enumerate(ks, start=1):
        gt4[hid] = sorted(d for d, _ in lines4[idx:idx + k])
        idx += k
    sums4 = truth_sums(lines4, gt4)
    headers4 = [(hid, sums4[hid], k) for hid, k in zip(gt4, ks)]
    write_case("exact-partition", headers4, lines4, gt4)

    print("wrote 4 baseline-minimal cases under", BASE)


if __name__ == "__main__":
    main()