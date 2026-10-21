"""Generate deliberately unsolvable order-matching test cases.

Each sub-directory isolates exactly ONE reason why no valid matching exists.
Before anything is written, every case is PROVED infeasible by brute force:
per-header k-subset enumeration plus an exhaustive disjoint-assignment search
across all headers. Files are written only if every proof succeeds.

Usage: python3 -I tests/infeasible-varieties/generate.py
"""

import csv
import json
import os
import random
import sys
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261021


# ---------------------------------------------------------------- exact cents

def cents(s):
    """Exact integer cents from a 2-decimal string (no float involved)."""
    if "." not in s or len(s.rsplit(".", 1)[1]) != 2:
        raise ValueError(f"price must have exactly 2 decimals: {s!r}")
    whole, frac = s.split(".")
    whole = int(whole) if whole else 0
    return whole * 100 + int(frac)


def fmt(c):
    return f"{c // 100}.{c % 100:02d}"


# ----------------------------------------------------------------- brute force

def candidate_combos(line_prices, target, k):
    """All k-line subsets whose exact cent sum equals target."""
    return [c for c in combinations(range(len(line_prices)), k)
            if sum(line_prices[i] for i in c) == target]


def global_matching_exists(headers, line_prices):
    """Exhaustive search for an assignment of disjoint combos to all headers."""
    combos = []
    for hid, target, k in headers:
        opts = candidate_combos(line_prices, cents(target), k)
        if not opts:
            return False, "header %s has no k-subset with the exact sum" % hid
        combos.append(opts)

    def dfs(i, used):
        if i == len(combos):
            return True
        for opt in combos[i]:
            if not (used & set(opt)):
                if dfs(i + 1, used | set(opt)):
                    return True
        return False

    return dfs(0, frozenset()), "exhaustive assignment search"


def any_subset_size(line_prices, target):
    """Smallest subset size (any size) achieving exactly target, else None."""
    n = len(line_prices)
    for size in range(1, n + 1):
        for c in combinations(range(n), size):
            if sum(line_prices[i] for i in c) == target:
                return size
    return None


def prove_infeasible(name, headers, lines, extra_check):
    line_prices = [cents(p) for _, p in lines]
    ok, why = global_matching_exists(headers, line_prices)
    assert not ok, f"{name}: brute force FOUND a matching ({why})"
    extra_check(name, headers, lines, line_prices)
    print(f"  PROVED infeasible: {name}")


# ------------------------------------------------------------------- cases

ADJ = ["streamlined", "persistent", "cross-platform", "grass-roots",
       "open-source", "value-added", "enterprise", "next-generation"]
NOUN = ["matrix", "pricing", "task-force", "groupware", "policy", "portal",
        "framework", "database"]


def make_descriptions(n):
    rng = random.Random(SEED)
    out, seen = [], set()
    while len(out) < n:
        d = "%s %s %d" % (rng.choice(ADJ), rng.choice(NOUN), rng.randrange(1000, 9999))
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def attach_lines(raw_prices):
    descs = make_descriptions(len(raw_prices))
    return list(zip(descs, raw_prices))


def case_sum_impossible():
    """All line prices carry an EVEN number of cents, so every subset sum is
    even in cents; both headers target an ODD number of cents."""
    lines = attach_lines(["2.00", "3.00", "4.00", "5.50", "6.00", "7.50"])
    headers = [(1, "10.01", 2), (2, "12.03", 3)]

    def check(name, headers, lines, lp):
        assert all(c % 2 == 0 for c in lp), "not all lines have even cents"
        for hid, target, k in headers:
            assert cents(target) % 2 == 1, f"header {hid} target not odd-cents"
            assert not candidate_combos(lp, cents(target), k)

    return "sum-impossible", headers, lines, check


def case_count_impossible():
    """3.00 IS reachable (1.00+1.00+1.00) but only with 3 lines; the header
    demands exactly 4 lines and the cheapest 4-line bundle costs 5.50."""
    lines = attach_lines(["1.00", "1.00", "1.00", "2.50", "4.75"])
    headers = [(1, "3.00", 4)]

    def check(name, headers, lines, lp):
        target, k = cents(headers[0][1]), headers[0][2]
        assert not candidate_combos(lp, target, k), "a 4-subset matches"
        small = any_subset_size(lp, target)
        assert small is not None and small < k, \
            "sum not achievable with fewer lines"

    return "count-impossible", headers, lines, check


def case_resource_exhaustion():
    """Each header is individually matchable, but the headers demand 2+2+4=8
    distinct lines while only 5 lines exist (pigeonhole)."""
    lines = attach_lines(["1.00", "2.00", "3.00", "4.00", "5.00"])
    headers = [(1, "6.00", 2), (2, "6.00", 2), (3, "12.00", 4)]

    def check(name, headers, lines, lp):
        assert sum(k for _, _, k in headers) > len(lp), "not exhausted"
        for hid, target, k in headers:
            assert candidate_combos(lp, cents(target), k), \
                f"header {hid} not individually matchable"

    return "resource-exhaustion", headers, lines, check


def case_one_header_blocks():
    """Header 1 fits {1.00,4.00} or {2.00,3.00}; header 2 fits only {2.00,4.00}.
    Every candidate pair collides, yet 4 lines are demanded from 5 (so this is
    pure contention, not resource exhaustion)."""
    lines = attach_lines(["1.00", "2.00", "3.00", "4.00", "9.00"])
    headers = [(1, "5.00", 2), (2, "6.00", 2)]

    def check(name, headers, lines, lp):
        assert sum(k for _, _, k in headers) <= len(lp), "would be exhaustion"
        h1 = candidate_combos(lp, cents(headers[0][1]), headers[0][2])
        h2 = candidate_combos(lp, cents(headers[1][1]), headers[1][2])
        assert h1 and h2, "not individually matchable"
        assert all(set(a) & set(b) for a in h1 for b in h2), \
            "contention not airtight"

    return "one-header-blocks", headers, lines, check


def case_floating_trap():
    """Two lines whose DOUBLE sum equals the header total's double exactly,
    while the exact cent sums differ by 1 (prices just above 2**53 cents,
    where the double grid is coarser than one cent). A float-based solver
    accepts; an integer-cents solver must reject. Config found by search."""
    c1 = None
    for cand in range(2 ** 53 + 2, 2 ** 53 + 200000):        # exact-cents scan
        p1 = fmt(cand)
        if round(float(p1) * 100) != cand:
            continue                                          # faithful parse
        for c2 in range(1, 100):
            p2, h = fmt(c2), cand + c2 + 1                    # 1 cent short
            if (round(float(p2) * 100) == c2
                    and round(float(fmt(h)) * 100) == h
                    and float(p1) + float(p2) == float(fmt(h))):
                c1, trap = cand, (p2, fmt(h))
                break
        if c1 is not None:
            break
    assert c1 is not None, "no float collision found"
    p2, hstr = trap
    lines = attach_lines([p1, p2])
    headers = [(1, hstr, 2)]

    def check(name, headers, lines, lp):
        target = cents(headers[0][1])
        assert sum(lp) == target - 1, "not off by exactly 1 cent"
        assert float(lines[0][1]) + float(lines[1][1]) == float(headers[0][1]), \
            "doubles must collide"
        assert not candidate_combos(lp, target, 2)

    return "floating-trap", headers, lines, check


# ------------------------------------------------------------------- writing

def write_case(dirname, headers, lines):
    os.makedirs(dirname, exist_ok=True)
    with open(os.path.join(dirname, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, target, k in headers:
            w.writerow([hid, target, k])
    with open(os.path.join(dirname, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for d, p in lines:
            w.writerow([d, p])
    with open(os.path.join(dirname, "expected.json"), "w") as f:
        json.dump({"expect_solvable": False, "ground_truth": None}, f)
        f.write("\n")


def main():
    builders = [case_sum_impossible, case_count_impossible,
                case_resource_exhaustion, case_one_header_blocks,
                case_floating_trap]
    for build in builders:
        name, headers, lines, check = build()
        assert all(1 <= k <= 10 for _, _, k in headers)
        assert all(cents(p) > 0 for _, p in lines)
        assert len({d for d, _ in lines}) == len(lines), "duplicate descriptions"
        prove_infeasible(name, headers, lines, check)
        write_case(os.path.join(HERE, name), headers, lines)
        print(f"  wrote {name}/ ({len(headers)} headers, {len(lines)} lines)")
    print("all cases proved infeasible and written")


if __name__ == "__main__":
    sys.exit(main())