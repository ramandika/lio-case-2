"""Generate performance / stress cases for the order-matching solver.

Every sub-case is a solvable instance built the same way: sample one
ground-truth bundle of lines per header (k in 1..10), set the header's
total_price to the exact cent sum of its bundle, then add decoy lines
that no header needs.  All prices are positive integer cents rendered
with exactly two decimals, so every total is exact in cents.

Cases (one directory each):

  big-100     10 headers / 100 lines; bundles k in 1..4, ~73 decoys.
              Stress: line volume with a wide, distinct price spread.
  big-300     25 headers / 300 lines; bundles k in 1..3, ~254 decoys.
              Stress: big candidate pool per header (C(300,3) already
              ~4.5M combinations for every k=3 header).
  wide-k10    3 headers at k=10 (the worst enumeration case,
              C(n,10)); ~30 ground lines + tiny decoys.  Decoy prices
              are 2-3 orders of magnitude below any ground-truth
              price, so a sum-aware solver can prune; the shipped
              naive solver must enumerate, which caps feasible n.
  many-dupes  15 headers / 150 lines drawn from only 5 distinct
              prices -> tens of thousands of alternative k-subsets per
              header (massive candidate repetition).

Run from the project root:  python3 -I tests/perf-stress/generate.py
"""

import csv
import json
import os
import random
from itertools import combinations

SEED = 20241022
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


def make_descriptions(rng, n):
    """n unique order-line descriptions."""
    seen, out = set(), []
    while len(out) < n:
        d = "%s %s %s" % (rng.choice(ADJ), rng.choice(MID), rng.choice(NOUN))
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def distinct_prices(rng, n, lo=100, hi=60000):
    """n distinct positive cent prices (wide spread -> few accidental sums)."""
    return rng.sample(range(lo, hi + 1), n)


def assemble(rng, ks, prices, descs):
    """Build headers + lines from one flat pool.

    ks: k (bundle size) per header.  prices/descs: full line pool, where the
    first sum(ks) entries are the ground-truth bundles (assigned round-robin)
    and the rest are decoys.  Returns (headers, lines, truth).
    """
    idx = list(range(len(prices)))
    rng.shuffle(idx)
    truth, headers, pos = {}, [], 0
    for hid, k in enumerate(ks, 1):
        take = idx[pos:pos + k]
        pos += k
        truth[str(hid)] = [descs[i] for i in take]
        headers.append((hid, sum(prices[i] for i in take), k))
    order = idx[:pos] + idx[pos:]          # bundles first, then decoys
    rng.shuffle(order)                     # scatter decoys among bundles
    lines = [(descs[i], prices[i]) for i in order]
    return headers, lines, truth


def case_big100(rng):
    n, ks = 100, [3, 4, 1, 2, 3, 4, 2, 3, 2, 3]   # 10 headers, 27 ground lines
    descs = make_descriptions(rng, n)
    prices = distinct_prices(rng, n)               # all distinct, 1.00-600.00
    return assemble(rng, ks, prices, descs)


def case_big300(rng):
    n = 300
    ks = [3] * 6 + [2] * 9 + [1] * 10              # 25 headers, 46 ground lines
    descs = make_descriptions(rng, n)
    prices = distinct_prices(rng, n)
    return assemble(rng, ks, prices, descs)


def case_widek10(rng):
    """3 headers at k=10 -- the worst enumeration case (C(n,10) per header).

    Ground-truth prices are large (50.00-900.00) and the decoys are tiny
    (< 1.00), so each target sits far above any subset of decoys: a
    sum-aware solver can discard most of the space by feasibility.  The
    shipped naive solver has no such pruning, so n is capped at 32.
    """
    ks = [10, 10, 10]                              # 30 ground lines, 2 decoys
    ground = distinct_prices(rng, 30, lo=5000, hi=90000)
    decoys = distinct_prices(rng, 2, lo=5, hi=100) # 0.05-1.00: sum << targets
    n = len(ks) * 10 + len(decoys)
    descs = make_descriptions(rng, n)
    return assemble(rng, ks, ground + decoys, descs)


# --- many-dupes: 150 lines from 5 distinct prices ------------------------

DUP_PRICES = (200, 350, 500, 750, 1000)
# k=3 patterns chosen so each header's target has several alternative
# price-decompositions (e.g. 1050 = 200+350+500 = 350*3) over ~30 copies
# of each price -> tens of thousands of valid k-subsets per header.
DUP_K3 = [(200, 200, 350),   # 750
          (200, 350, 500),   # 1050 (alt: 350,350,350)
          (200, 500, 500),   # 1200 (alt: 350,350,500)
          (350, 350, 500),   # 1200
          (200, 750, 750),   # 1700 (alt: 200,500,1000 / 350,350,1000)
          (350, 350, 1000),  # 1700
          (500, 500, 1000),  # 2000 (alt: 500,750,750)
          (750, 750, 500)]   # 2000
DUP_K2 = [(200, 350),        # 550
          (350, 500),        # 850
          (500, 1000)]       # 1500 (alt: 750,750)
DUP_K1 = [(500,), (1000,)]


def case_manydupes(rng):
    per_price = 30
    ks = [1] * 2 + [2] * 3 + [3] * 10             # 15 headers, 38 ground lines
    pool = [p for p in DUP_PRICES for _ in range(per_price)]  # 150 lines
    descs = make_descriptions(rng, len(pool))

    idx_by_price = {p: [] for p in DUP_PRICES}
    for i, p in enumerate(pool):
        idx_by_price[p].append(i)

    truth, headers = {}, []
    used = set()

    def take(price, count):
        """Distinct line indices for `count` lines at `price`."""
        avail = [i for i in idx_by_price[price] if i not in used]
        assert len(avail) >= count, "price pool exhausted"
        picked = rng.sample(avail, count)
        used.update(picked)
        return picked

    hid = 0
    for k, patterns in ((1, DUP_K1), (2, DUP_K2), (3, DUP_K3)):
        want = ks.count(k)
        for j in range(want):
            hid += 1
            pattern = patterns[j % len(patterns)]
            picks = []
            for price in sorted(set(pattern)):
                picks += take(price, pattern.count(price))
            truth[str(hid)] = [descs[i] for i in picks]
            headers.append((hid, sum(pool[i] for i in picks), k))

    lines = [(descs[i], pool[i]) for i in range(len(pool))]
    rng.shuffle(lines)
    return headers, lines, truth


def enumerate_load(headers, n_lines):
    """Total combinations the naive solver must scan: sum(C(n, k))."""
    return sum(len(list(combinations(range(n_lines), k))) for _, _, k in headers)


def write_case(name, headers, lines, truth):
    out = os.path.join(BASE, name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, total, k in headers:
            w.writerow([hid, "%.2f" % (total / 100), k])
    with open(os.path.join(out, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for d, c in lines:
            w.writerow([d, "%.2f" % (c / 100)])
    with open(os.path.join(out, "expected.json"), "w") as f:
        json.dump({"expect_solvable": True, "ground_truth": truth}, f, indent=2)
    decoys = len(lines) - sum(len(v) for v in truth.values())
    print("%-10s %2d headers %4d lines (%3d ground, %3d decoys) "
          "naive-scan ~%s combinations"
          % (name, len(headers), len(lines), len(lines) - decoys, decoys,
             f"{enumerate_load(headers, len(lines)):,}"))


def main():
    rng = random.Random(SEED)
    for name, builder in (("big-100", case_big100),
                          ("big-300", case_big300),
                          ("wide-k10", case_widek10),
                          ("many-dupes", case_manydupes)):
        headers, lines, truth = builder(rng)
        write_case(name, headers, lines, truth)


if __name__ == "__main__":
    main()