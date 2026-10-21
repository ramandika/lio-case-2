#!/usr/bin/env python3
"""Generate the forced-unique test cases.

Every instance produced here has EXACTLY ONE valid global matching: a single
choice of line-set per header satisfies all of (total_lines, total_price)
with no line reused.

Uniqueness is verified inside this generator by enumerating every candidate
k-subset per header and then every tuple of mutually disjoint feasible
subsets across headers (the product of the per-header feasible sets).  All
instances stay small (<= 10 lines total, <= 4 headers), so the enumeration
is exhaustive and exact.  Two of the four sub-cases additionally get a
structural proof:

  superincreasing            line prices are strictly super-increasing
                             (a_j > sum of all smaller prices), so by the
                             standard greedy-induction argument any
                             reachable target has at most one subset
                             representation; the targets are set to sums of
                             disjoint lines, hence the matching is unique.
                             Brute force confirms it.

  two-headers-exchange-proof exactly one global matching is confirmed by
                             enumeration, and additionally every single-line
                             swap between the two headers is enumerated to
                             show no swap preserves both sums.

  single-header-unique-k     all C(n, k) k-subsets are enumerated; exactly
                             one sums to the target.

  pinning-chain              headers small->big, each in turn admits exactly
                             one feasible line-set among the lines not yet
                             taken by earlier headers (verified per step),
                             so the small headers pin the big header's only
                             remaining lines.  Full enumeration confirms
                             global uniqueness as well.

Runs fully deterministically from a fixed seed.
"""

import csv
import json
import os
import random
from itertools import combinations

BASE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261021
MAX_RETRIES = 20000
NODE_BUDGET = 300000

ADJ = ["Adaptive", "Balanced", "Centralized", "Digital", "Enterprise",
       "Fluctuating", "Grass-roots", "Horizontal", "Integrated", "Key",
       "Lagged", "Modular", "Networked", "Open-architected", "Profound",
       "Quality-focused", "Re-engineered", "Streamlined", "Total",
       "User-friendly"]
NOUN = ["capability", "contingency", "data-warehouse", "database",
        "emulation", "framework", "function", "groupware", "hardware",
        "hub", "infrastructure", "instruction-set", "interface", "matrix",
        "migration", "monitoring", "neural-net", "open-system", "policy",
        "portal", "protocol", "software", "standardization", "structure",
        "success", "support", "time-frame", "toolset", "utility"]


rng = random.Random(SEED)


def cents_str(c):
    return f"{c // 100}.{c % 100:02d}"


def fresh_descriptions(n):
    """n unique, deterministic description strings."""
    seen = set()
    while len(seen) < n:
        d = f"{rng.choice(ADJ)} {rng.choice(NOUN)} #{rng.randrange(1000, 10000)}"
        seen.add(d)
    return sorted(seen)


def random_prices(n, lo=150, hi=90000):
    """n distinct positive cent amounts (all lines get distinct prices)."""
    return rng.sample(range(lo, hi + 1), n)


def feasible_subsets(lines, k, target):
    """Every k-line subset of `lines` ((desc, cents) tuples) summing to target."""
    out = []
    for combo in combinations(lines, k):
        if sum(c for _, c in combo) == target:
            out.append(combo)
    return out


def count_global_matchings(headers, lines, limit=2):
    """Number of tuples of mutually disjoint feasible subsets (one per header).

    headers: ordered (k, target) list, lines: [(desc, cents), ...].
    Each header is forced to exactly total_lines lines, so the set of global
    matchings is exactly the set of such tuples.  Stops counting at `limit`.
    Returns (count, nodes_used)."""
    feas = []
    for k, target in headers:
        fs = feasible_subsets(lines, k, target)
        if not fs:
            return 0, 0
        feas.append(fs)

    nodes = [0]

    def rec(i, used):
        nodes[0] += 1
        if nodes[0] > NODE_BUDGET:
            raise RuntimeError("node budget exceeded")
        if i == len(feas):
            return 1
        total = 0
        for combo in feas[i]:
            ds = frozenset(d for d, _ in combo)
            if used.isdisjoint(ds):
                total += rec(i + 1, used | ds)
                if total >= limit:
                    return total
        return total

    return rec(0, frozenset()), nodes[0]


def chain_forced(headers, lines):
    """pinning-chain structural check: each header in order admits exactly one
    feasible subset among the lines not consumed by earlier headers."""
    remaining = list(lines)
    for k, target in headers:
        fs = feasible_subsets(remaining, k, target)
        if len(fs) != 1:
            return False
        taken = fs[0]
        remaining = [l for l in remaining if l not in taken]
    return True


def build_superincreasing():
    """Case 1: super-increasing prices; targets are sums of disjoint lines.

    Construction argument: a_j > sum of all smaller prices implies every
    target has at most one subset representation (greedy-induction), so each
    header's feasible set is a singleton and the tuple is unique."""
    for _ in range(MAX_RETRIES):
        values = []
        total = 0
        first = rng.randrange(101, 500)
        values.append(first)
        total += first
        for _ in range(9):
            nxt = total + rng.randrange(1, 400)  # strictly > sum of all smaller
            values.append(nxt)
            total += nxt
        descs = fresh_descriptions(len(values))
        lines = list(zip(descs, values))

        order = list(range(10))
        rng.shuffle(order)
        sizes = [2, 3, 2]
        headers, truth = [], {}
        pos = 0
        for hid, size in enumerate(sizes, 1):
            group = order[pos:pos + size]
            pos += size
            target = sum(values[j] for j in group)
            headers.append((len(group), target))
            truth[str(hid)] = [descs[j] for j in group]

        count, _ = count_global_matchings(headers, lines)
        if count == 1:
            return headers, lines, truth, "super-increasing construction + brute force"
    raise RuntimeError("superincreasing: no instance found")


def exchange_swaps(headers, lines, truth_pairs):
    """Case 2 extra check: enumerate every single-line exchange between the
    two headers; none may preserve both sums."""
    (k1, t1), (k2, t2) = headers
    h1 = [l for l in lines if l in truth_pairs[0]]
    h2 = [l for l in lines if l in truth_pairs[1]]
    for a in h1:
        for b in h2:
            if t1 - a[1] + b[1] == t1 and t2 - b[1] + a[1] == t2:
                return False
    return True


def build_two_headers():
    """Case 2: 2 headers, unique global matching; no preserving single swap."""
    for _ in range(MAX_RETRIES):
        prices = random_prices(8)
        descs = fresh_descriptions(8)
        lines = list(zip(descs, prices))
        k1 = rng.randrange(1, 4)
        k2 = rng.randrange(1, 4)
        idx = rng.sample(range(8), k1 + k2)
        g1, g2 = idx[:k1], idx[k1:]
        headers = [(k1, sum(prices[j] for j in g1)),
                   (k2, sum(prices[j] for j in g2))]
        truth = {"1": [descs[j] for j in g1], "2": [descs[j] for j in g2]}
        count, _ = count_global_matchings(headers, lines)
        if count != 1:
            continue
        sol1 = tuple((descs[j], prices[j]) for j in g1)
        sol2 = tuple((descs[j], prices[j]) for j in g2)
        if exchange_swaps(headers, lines, (sol1, sol2)):
            return headers, lines, truth, "brute-force enumeration + swap enumeration"
    raise RuntimeError("two-headers: no instance found")


def build_single_header():
    """Case 3: one header; exactly one k-subset among all C(n, k) hits target."""
    for _ in range(MAX_RETRIES):
        prices = random_prices(10)
        descs = fresh_descriptions(10)
        lines = list(zip(descs, prices))
        k = rng.randrange(3, 8)
        subset = rng.sample(range(10), k)
        target = sum(prices[j] for j in subset)
        if len(feasible_subsets(lines, k, target)) != 1:
            continue
        count, _ = count_global_matchings([(k, target)], lines)
        if count == 1:
            truth = {"1": sorted(descs[j] for j in subset)}
            return [(k, target)], lines, truth, "enumeration of all k-subsets"
    raise RuntimeError("single-header: no instance found")


def build_pinning_chain():
    """Case 4: headers small->big; each is forced among not-yet-taken lines,
    so earlier headers pin the big header's only remaining lines."""
    sizes = [1, 2, 1, 4]  # 8 of 10 lines used, 2 decoys left over
    for _ in range(MAX_RETRIES):
        prices = random_prices(10)
        descs = fresh_descriptions(10)
        lines = list(zip(descs, prices))
        idx = rng.sample(range(10), sum(sizes))
        headers, truth = [], {}
        pos = 0
        for hid, size in enumerate(sizes, 1):
            group = idx[pos:pos + size]
            pos += size
            headers.append((len(group), sum(prices[j] for j in group)))
            truth[str(hid)] = [descs[j] for j in group]
        count, _ = count_global_matchings(headers, lines)
        if count != 1:
            continue
        if chain_forced(headers, lines):
            return headers, lines, truth, "sequential pinning + brute force"
    raise RuntimeError("pinning-chain: no instance found")


def write_case(name, headers, lines, truth, _proof):
    case_dir = os.path.join(BASE, name)
    os.makedirs(case_dir, exist_ok=True)

    with open(os.path.join(case_dir, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, (k, target) in enumerate(headers, 1):
            w.writerow([hid, cents_str(target), k])

    with open(os.path.join(case_dir, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for desc, c in lines:
            w.writerow([desc, cents_str(c)])

    with open(os.path.join(case_dir, "expected.json"), "w") as f:
        json.dump({"expect_solvable": True, "ground_truth": truth}, f, indent=2)
        f.write("\n")

    size = f"{len(headers)} headers, {len(lines)} lines"
    truth_desc = sum(len(v) for v in truth.values())
    print(f"wrote tests/forced-unique/{name}: {size}, "
          f"assigned lines = {truth_desc}, unique matchings verified = 1")


def main():
    builds = [
        ("superincreasing", build_superincreasing),
        ("two-headers-exchange-proof", build_two_headers),
        ("single-header-unique-k", build_single_header),
        ("pinning-chain", build_pinning_chain),
    ]
    for name, fn in builds:
        headers, lines, truth, proof = fn()
        write_case(name, headers, lines, truth, proof)
    print(f"done (seed={SEED})")


if __name__ == "__main__":
    main()