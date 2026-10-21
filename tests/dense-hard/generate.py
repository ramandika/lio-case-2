"""Generate dense hard test cases for the order-matching solver.

Category: instances NEAR THE PHASE TRANSITION of subset-sum.  Line prices
live in a NARROW integer-cents band (e.g. 1000-1100 cents == 10.00-11.00)
and header targets are sized so valid k-subsets are barely abundant.
Ground truth is constructed first; a brute-force pass then counts every
distinct valid global matching so we know exactly how ambiguous each
instance is.  Instances stay small (<= 16 lines) so the brute force is
cheap.

Cases (one sub-directory each):
  narrow-range     : 3 headers, every price in a 100-cent band, 12 lines.
  near-crossover   : density tuned until the instance sits right at the
                     crossover - solvable but with only 1-2 global matchings.
  many-alternatives: dense band where the ground-truth partition is very
                     far from unique (count reported).
  collision-prone  : header targets deliberately equal sums of OTHER
                     headers' lines plus decoy lines, so cross-assignment
                     decoys abound.

All prices are positive with exactly 2 decimals; 1-10 lines per header.

Run from the project root:  python3 -I tests/dense-hard/generate.py
"""

import csv
import json
import os
import random
from itertools import combinations

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


def uniq_descs(rng, n):
    """n distinct order-line descriptions (lines are keyed by description)."""
    descs, out = set(), []
    while len(out) < n:
        d = f"{rng.choice(ADJ)} {rng.choice(MID)} {rng.choice(NOUN)}"
        if d not in descs:
            descs.add(d)
            out.append(d)
    return out


def count_global_matchings(prices, specs):
    """Count distinct valid global matchings by brute force.

    prices: list of integer-cent prices for every line in the pool
            (decoys included, unused lines allowed).
    specs:  [(target_cents, k), ...] one entry per header.
    A global matching is a tuple of pairwise-disjoint index subsets, one
    per header, each of size k and summing to its target.  Headers are
    distinguishable, so swaps between equal-target headers count twice.
    """
    opts = []
    for target, k in specs:
        opts.append([frozenset(c)
                     for c in combinations(range(len(prices)), k)
                     if sum(prices[i] for i in c) == target])
    def rec(i, used):
        if i == len(opts):
            return 1
        total = 0
        for opt in opts[i]:
            if opt.isdisjoint(used):
                total += rec(i + 1, used | opt)
        return total
    return rec(0, frozenset())


def write_case(name, headers, lines, ground_truth):
    """headers: [(id, total_cents, k)], lines: [(desc, cents)],
    ground_truth: {id: [desc, ...]}."""
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
                   "ground_truth": {str(h): sorted(v)
                                    for h, v in ground_truth.items()}},
                  f, indent=2)
        f.write("\n")


def lines_from(prices, descs):
    return list(zip(descs, prices))


def by_desc(lines):
    return {d: c for d, c in lines}


def gt_from(groups, descs):
    """groups: [index lists per header] over descs -> {hid: [desc, ...]}."""
    return {hid + 1: [descs[i] for i in g] for hid, g in enumerate(groups)}


def check_case(name, lines, ground_truth, specs):
    """Sanity: ground truth valid inside the pool, plus count report."""
    pd = by_desc(lines)
    assert len(pd) == len(lines), f"{name}: duplicate descriptions"
    for d, c in lines:
        assert c > 0, f"{name}: non-positive price"
    used = [d for v in ground_truth.values() for d in v]
    assert len(used) == len(set(used)), f"{name}: ground truth reuses a line"
    for hid, descs_gt in ground_truth.items():
        assert sum(pd[d] for d in descs_gt) == specs[hid - 1][0]
        assert len(descs_gt) == specs[hid - 1][1]
        assert 1 <= len(descs_gt) <= 10
    return count_global_matchings([c for _, c in lines], specs)


def random_dense(rng, n_lines, ks, band, n_extra_decoys=0):
    """Random dense instance: prices from a narrow band, random truth
    partition of the first sum(ks) lines, targets = truth sums."""
    prices = [rng.randint(*band) for _ in range(n_lines)]
    descs = uniq_descs(rng, n_lines)
    m = sum(ks)
    chosen = rng.sample(range(n_lines), m)
    groups, idx = [], 0
    for k in ks:
        groups.append(sorted(chosen[idx:idx + k]))
        idx += k
    specs = [(sum(prices[i] for i in g), len(g)) for g in groups]
    gt = gt_from(groups, descs)
    headers = [(hid + 1, t, k) for hid, (t, k) in enumerate(specs)]
    return headers, lines_from(prices, descs), gt, specs


def main():
    rng = random.Random(SEED)
    report = []

    # ------------------------------------------------------------------
    # 1. narrow-range: 3 headers (k=3,2,2), 12 lines all in 1000-1099c.
    # ------------------------------------------------------------------
    best, best_count = None, 0
    for trial in range(60):
        headers, lines, gt, specs = random_dense(rng, 12, [3, 2, 2], (1000, 1049))
        count = count_global_matchings([c for _, c in lines], specs)
        if count > best_count:
            best, best_count = (headers, lines, gt, specs), count
        if best_count >= 20:
            break
    assert best_count > 1, "narrow-range: ground truth should not be unique"
    headers, lines, gt, specs = best
    check_case("narrow-range", lines, gt, specs)
    write_case("narrow-range", headers, lines, gt)
    report.append(("narrow-range", len(lines), best_count))

    # ------------------------------------------------------------------
    # 2. near-crossover: search until the instance is exactly at the
    #    crossover - solvable, with only 1 or 2 global matchings.
    #    Density tuned via band width and decoy count.
    # ------------------------------------------------------------------
    found = None
    for band in [(1000, 1029), (1000, 1039), (1000, 1049), (1000, 1059),
                 (1000, 1069), (1000, 1079)]:
        if found:
            break
        for trial in range(40):
            ks = [4, 3, 2]
            headers, lines, gt, specs = random_dense(
                rng, 9 + 0, ks, band)
            count = count_global_matchings([c for _, c in lines], specs)
            # ground truth must be one of them; count >= 1 iff solvable
            if 1 <= count <= 2:
                found = (headers, lines, gt, specs, count)
                break
    assert found, "near-crossover: no instance with count in {1,2} found"
    headers, lines, gt, specs, count = found
    check_case("near-crossover", lines, gt, specs)
    write_case("near-crossover", headers, lines, gt)
    report.append(("near-crossover", len(lines), count))

    # ------------------------------------------------------------------
    # 3. many-alternatives: keep the densest instance found where the
    #    ground-truth global matching is far from unique.
    # ------------------------------------------------------------------
    best, best_count = None, 0
    for trial in range(60):
        headers, lines, gt, specs = random_dense(rng, 12, [3, 3, 3], (1000, 1069))
        count = count_global_matchings([c for _, c in lines], specs)
        if count > best_count:
            best, best_count = (headers, lines, gt, specs), count
        if best_count >= 100:
            break
    assert best_count > 1, "many-alternatives: ground truth should not be unique"
    headers, lines, gt, specs = best
    check_case("many-alternatives", lines, gt, specs)
    write_case("many-alternatives", headers, lines, gt)
    report.append(("many-alternatives", len(lines), best_count))

    # ------------------------------------------------------------------
    # 4. collision-prone: build decoys on purpose.
    #    Truth: A(k=2){a1,a2}, B(k=2){b1,b2}, C(k=1){c1}.
    #    Decoy lines planted so that:
    #      - a decoy PAIR  (x1,x2) sums to A's target;
    #      - decoy z = T_A - b1  -> B's line b1 + z hits A's target;
    #      - decoy y = T_B - a1  -> A's line a1 + y hits B's target;
    #      - a decoy priced exactly like c1 -> C's line is a twin decoy.
    # ------------------------------------------------------------------
    band = (1000, 1099)
    while True:
        a1, a2, b1, b2 = rng.randint(*band), rng.randint(*band), \
            rng.randint(*band), rng.randint(*band)
        c1 = rng.randint(*band)
        prices = [a1, a2, b1, b2, c1]
        T_A, T_B, T_C = a1 + a2, b1 + b2, c1
        # decoy pair hitting T_A
        x1 = rng.randint(max(band[0], T_A - band[1]), min(band[1], T_A - band[0]))
        x2 = T_A - x1
        if not (band[0] <= x2 <= band[1]):
            continue
        z = T_A - b1          # b1 + z == T_A (cross decoy for A)
        y = T_B - a1          # a1 + y == T_B (cross decoy for B)
        twin = c1             # twin decoy for C (duplicate price OK)
        if not all(band[0] <= v <= band[1] for v in (x1, x2, z, y, twin)):
            continue
        break
    prices += [x1, x2, z, y, twin]
    descs = uniq_descs(rng, len(prices))
    lines = lines_from(prices, descs)
    gt = {1: [descs[0], descs[1]], 2: [descs[2], descs[3]], 3: [descs[4]]}
    specs = [(T_A, 2), (T_B, 2), (T_C, 1)]
    headers = [(1, T_A, 2), (2, T_B, 2), (3, T_C, 1)]
    count = check_case("collision-prone", lines, gt, specs)
    assert count > 1, "collision-prone: decoys did not create alternatives"
    write_case("collision-prone", headers, lines, gt)
    report.append(("collision-prone", len(lines), count))

    for name, n, cnt in report:
        print(f"{name}: {n} lines, {cnt} distinct valid global matchings")
    print("wrote 4 dense-hard cases under", BASE)


if __name__ == "__main__":
    main()