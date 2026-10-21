"""Generate cardinality-boundary test cases for the order-matching solver.

Writes one sub-case directory per scenario, each with:
  order_headers.csv  (id,total_price,total_lines)
  order_lines.csv    (description,price)
  expected.json      {"expect_solvable": bool, "ground_truth": {...}|null}

Cases (total_lines is always within the README range 1..10):
  k1-singletons    : all headers k=1, duplicate-price lines force a distinct
                     assignment of identically priced lines to headers
  k10-max          : every header k=10 (the allowed maximum), solvable
  k-mix            : one shared line pool with k=1,2,9,10 headers
  many-k1-few-pool : 8 headers k=1 against exactly 8 uniquely priced lines
                     (the forced perfect assignment)

All prices are positive with exactly 2 decimals; header totals are exact
integer-cent sums of the ground-truth lines.  Descriptions are unique even
when prices collide, so ground-truth lines stay unambiguous.

Run from the project root:  python3 -I tests/boundary-cardinality/generate.py
"""

import csv
import json
import os
import random

SEED = 20251021
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


def fresh_desc(rng, used):
    """A not-yet-used line description."""
    while True:
        d = f"{rng.choice(ADJ)} {rng.choice(MID)} {rng.choice(NOUN)}"
        if d not in used:
            used.add(d)
            return d


def add_lines(rng, prices_cents, used, lines):
    """Append one line per cent value; return (description, cents) pairs."""
    pairs = []
    for c in prices_cents:
        d = fresh_desc(rng, used)
        lines.append((d, c))
        pairs.append((d, c))
    return pairs


def write_case(name, headers, lines, gt):
    d = os.path.join(BASE, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, total_cents, k in headers:
            w.writerow([hid, f"{total_cents / 100:.2f}", k])
    with open(os.path.join(d, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for desc, cents in lines:
            w.writerow([desc, f"{cents / 100:.2f}"])
    with open(os.path.join(d, "expected.json"), "w") as f:
        json.dump({"expect_solvable": True, "ground_truth": gt}, f, indent=2)
        f.write("\n")


def gen_k1_singletons():
    """All k=1: several price values, each shared by more lines than headers,
    so identically priced lines must still go to distinct headers."""
    rng = random.Random(SEED + 1)
    used, lines, gt, headers = set(), [], {}, []
    # (headers, lines) per distinct price value; headers < lines per value.
    groups = [(4, 6), (3, 4), (2, 3), (1, 2)]
    values = rng.sample(range(150, 90000), len(groups))
    hid = 1
    for (nh, nl), price in zip(groups, values):
        pairs = add_lines(rng, [price] * nl, used, lines)
        for idx in range(nh):
            headers.append((hid, price, 1))
            gt[str(hid)] = [pairs[idx][0]]
            hid += 1
    # Decoy lines at unrelated prices (colliding among themselves).
    decoys = rng.sample(range(150, 90000), 3)
    add_lines(rng, decoys + decoys[:2], used, lines)
    write_case("k1-singletons", headers, lines, gt)


def gen_k10_max():
    """Both headers take exactly 10 lines (the maximum allowed k)."""
    rng = random.Random(SEED + 2)
    used, lines, gt, headers = set(), [], {}, []
    prices = rng.sample(range(200, 60000), 22)
    first = add_lines(rng, prices[:10], used, lines)
    second = add_lines(rng, prices[10:20], used, lines)
    add_lines(rng, prices[20:], used, lines)  # 2 decoy lines
    headers = [(1, sum(c for _, c in first), 10),
               (2, sum(c for _, c in second), 10)]
    gt = {"1": [d for d, _ in first], "2": [d for d, _ in second]}
    write_case("k10-max", headers, lines, gt)


def gen_k_mix():
    """One shared pool; headers span the k extremes: 1, 2, 9 and 10."""
    rng = random.Random(SEED + 3)
    used, lines, gt, headers = set(), [], {}, []
    ks = [1, 2, 9, 10]
    prices = rng.sample(range(200, 60000), sum(ks) + 2)  # 22 + 2 decoys
    pos = 0
    for hid, k in enumerate(ks, start=1):
        chunk = prices[pos:pos + k]
        pos += k
        pairs = add_lines(rng, chunk, used, lines)
        headers.append((hid, sum(c for _, c in pairs), k))
        gt[str(hid)] = [d for d, _ in pairs]
    add_lines(rng, prices[pos:], used, lines)  # 2 decoy lines
    write_case("k-mix", headers, lines, gt)


def gen_many_k1_few_pool():
    """8 headers with k=1 against exactly 8 lines, each priced uniquely, so
    every header's target matches exactly one line: a forced 1-1 mapping."""
    rng = random.Random(SEED + 4)
    used, lines = set(), []
    prices = rng.sample(range(150, 90000), 8)
    pairs = add_lines(rng, prices, used, lines)
    headers = [(hid, c, 1) for hid, (_, c) in enumerate(pairs, start=1)]
    gt = {str(hid): [d]
          for hid, (d, _) in enumerate(pairs, start=1)}
    write_case("many-k1-few-pool", headers, lines, gt)


def main():
    gen_k1_singletons()
    gen_k10_max()
    gen_k_mix()
    gen_many_k1_few_pool()


if __name__ == "__main__":
    main()