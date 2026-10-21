"""Generate adversarial decoy cases for the order-matching solver.

Writes one sub-case directory per decoy scenario, each with:
  order_headers.csv  (id,total_price,total_lines)
  order_lines.csv    (description,price)
  expected.json      {"expect_solvable": bool, "ground_truth": {...}|null}

Cases (all engineered against greedy / local-search / myopic assignment):
  greedy-trap             : the easiest header's obvious candidate combo steals
                            a line required by every remaining header's combo,
                            while its second combo leaves the rest solvable.
  near-miss-decoys        : decoy lines that reach a target within 0.01, equal
                            a target as a single line, or sit +/-0.01 off a
                            k=1 target -- locally right, globally unusable.
  shared-line-contention  : two headers are each individually matchable with
                            the same popular line, but exactly one
                            cross-compatible (joint) assignment exists.
  poisoned-k              : a k=2 header whose target has MANY 2-subsets but
                            only one survives the other headers' needs.

Every claim (combo populations, decoy near-miss sums, which naive greedy
orderings fall for the trap, uniqueness of the joint solution) is verified
here by brute force before anything is written.

Run from the project root:  python3 -I tests/adversarial-decoys/generate.py
"""

import csv
import json
import os
from itertools import combinations
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


# --------------------------------------------------------------------------
# brute-force machinery
# --------------------------------------------------------------------------

def combos_for(lines, target, k):
    """All k-line index tuples (CSV order, lexicographic) summing to target."""
    return [c for c in combinations(range(len(lines)), k)
            if sum(lines[i][1] for i in c) == target]


def all_solutions(headers, lines):
    """Every disjoint full assignment (header id -> line-index tuple)."""
    combos = {hid: combos_for(lines, target, k)
              for hid, target, k in headers}
    sols = []

    def walk(i, used, acc):
        if i == len(headers):
            sols.append(dict(acc))
            return
        hid, target, k = headers[i]
        for c in combos[hid]:
            if any(idx in used for idx in c):
                continue
            acc[hid] = c
            walk(i + 1, used | set(c), acc)
            del acc[hid]

    walk(0, frozenset(), {})
    return sols, combos


def greedy_first_fit(headers, lines, order):
    """Myopic greedy: fixed `order` of header ids, first non-blocked combo,
    no backtracking, no re-sorting after each assignment."""
    combos = {hid: combos_for(lines, target, k)
              for hid, target, k in headers}
    used, assignment = set(), {}
    for hid in order:
        target, k = next((t, kk) for h, t, kk in headers if h == hid)
        pick = next((c for c in combos[hid] if not any(i in used for i in c)),
                    None)
        if pick is None:
            return False, assignment
        assignment[hid] = pick
        used |= set(pick)
    return True, assignment


def mcf_order(header_ids):
    """Most-constrained-first order: fewest candidate combos, ties by id
    (static / myopic -- never re-sorted after assignments)."""
    return lambda hdrs, combos: sorted(header_ids,
                                       key=lambda h: (len(combos[h]), h))


def gt_maps(gt, lines):
    """ground_truth {id: [descs]} -> {id: index tuple} under this line order."""
    index = {d: i for i, (d, _) in enumerate(lines)}
    return {hid: tuple(sorted(index[d] for d in descs))
            for hid, descs in gt.items()}


def check(condition, msg):
    if not condition:
        raise AssertionError("BRUTE-FORCE SANITY FAILED: " + msg)


# --------------------------------------------------------------------------
# case writing (with rng-sourced unique descriptions + verified-inert fillers)
# --------------------------------------------------------------------------

def unique_desc(rng, taken):
    while True:
        d = f"{rng.choice(ADJ)} {rng.choice(MID)} {rng.choice(NOUN)}"
        if d not in taken:
            taken.add(d)
            return d


def try_filler(rng, lines, headers, taken):
    """Draw a filler line; keep it only if it creates NO new candidate combo
    for any header (brute-forced), so it cannot change any claim."""
    desc = unique_desc(rng, taken)
    price = rng.randrange(5000, 90000)
    cand = lines + [(desc, price)]
    new_idx = len(lines)
    for hid, target, k in headers:
        if any(new_idx in c for c in combos_for(cand, target, k)):
            return None
    return (desc, price)


def add_fillers(rng, lines, headers, taken, n):
    base = len(lines)
    lines = list(lines)
    while len(lines) < base + n and len(lines) < 14:
        filler = try_filler(rng, lines, headers, taken)
        if filler is not None:
            lines.append(filler)
    return lines


def write_case(name, headers, lines, expect_solvable, ground_truth, note):
    out = os.path.join(BASE, name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, target, k in headers:
            w.writerow([hid, f"{target / 100:.2f}", k])
    with open(os.path.join(out, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for d, c in lines:
            w.writerow([d, f"{c / 100:.2f}"])
    with open(os.path.join(out, "expected.json"), "w") as f:
        json.dump({"expect_solvable": expect_solvable,
                   "ground_truth": ({str(hid): descs
                                     for hid, descs in ground_truth.items()}
                                    if ground_truth else None)},
                  f, indent=2)
        f.write("\n")
    print(f"wrote {name}: {len(lines)} lines, {note}")


# --------------------------------------------------------------------------
# the four decoy cases
# --------------------------------------------------------------------------

def main():
    rng = random.Random(SEED)

    # ---- 1. greedy-trap ------------------------------------------------
    # Easiest header H1 (k=2, 301.00) has exactly 2 candidate pairs, and its
    # FIRST pair (150.00+151.00, sitting first in the CSV) is poisoned: H2's
    # every candidate pair needs one of those two lines. H1's alternate pair
    # (100.00+201.00) touches nothing H2 needs -> the joint solution exists.
    price = [15000, 15100, 10000, 20100, 11000, 10900, 11000]
    taken = set()
    lines = [(unique_desc(rng, taken), p) for p in price]
    headers = [(1, 30100, 2), (2, 26000, 2)]
    lines = add_fillers(rng, lines, headers, taken, 2)
    gt = {1: [lines[2][0], lines[3][0]], 2: [lines[0][0], lines[4][0]]}

    sols, combos = all_solutions(headers, lines)
    check(len(combos[1]) == 2, "greedy-trap: H1 must have exactly 2 combos")
    check(combos[1][0] == (0, 1), "greedy-trap: H1's first combo is the poisoned pair (0,1)")
    check(len(combos[2]) > len(combos[1]), "greedy-trap: H1 must be strictly most-constrained")
    check(len(lines) <= 14, "greedy-trap: <= 14 lines")
    # poisoned claim: H1 taking (0,1) leaves H2 with zero viable combos,
    # i.e. no full solution contains that combo.
    check(not any(s[1] == (0, 1) for s in sols),
          "greedy-trap: poisoned pair must appear in no full solution")
    gti = gt_maps(gt, lines)
    check(gti in sols, "greedy-trap: ground truth must be a full solution")
    g1, _ = greedy_first_fit(headers, lines, mcf_order([1, 2])(headers, combos))
    check(not g1, "greedy-trap: myopic most-constrained-first + first combo must FAIL")
    g2, _ = greedy_first_fit(headers, lines, [1, 2])
    check(not g2, "greedy-trap: CSV-order first-fit must FAIL")
    write_case("greedy-trap", headers, lines, True, gt,
               "H1's obvious first combo starves H2; its alternate combo works")

    # ---- 2. near-miss-decoys -------------------------------------------
    # H1 (k=3, 500.00): truth x+y+z. Decoy triple u+v+t sums to 499.99
    # (0.01 short). H2 (k=1, 100.00): truth w; decoy singles at 99.99 and
    # 100.01 flank its target by exactly one cent. n=500.00 equals H1's
    # target as a single line -- seductive for the wrong k. All decoys are
    # inert: they appear in no solution.
    price = [10000, 10000, 15000, 25000, 11999, 18000, 20000, 9999, 10001, 50000]
    taken = set()
    lines = [(unique_desc(rng, taken), p) for p in price]
    headers = [(1, 50000, 3), (2, 10000, 1)]
    target1, target2 = 50000, 10000
    check(sum(price[i] for i in (4, 5, 6)) == target1 - 1,
          "near-miss: decoy triple must reach H1 target within 0.01")
    check(price[7] == target2 - 1 and price[8] == target2 + 1,
          "near-miss: H2 decoys must flank its target by 0.01")
    check(price[9] == target1,
          "near-miss: single line must equal H1's target (wrong-k seduction)")
    decoys = {4, 5, 6, 7, 8, 9}
    sols, combos = all_solutions(headers, lines)
    check(all(not (set(c) & decoys) for s in sols for c in s.values()),
          "near-miss: no decoy may appear in any full solution")
    check(len(sols) == 2 and len(combos[1]) == 2 and len(combos[2]) == 2,
          "near-miss: exactly the two twin-100 variants must solve")
    gti = {1: (0, 2, 3), 2: (1,)}
    check(gti in sols, "near-miss: ground truth must be a full solution")
    check(len(lines) <= 14, "near-miss: <= 14 lines")
    write_case("near-miss-decoys", headers, lines, True,
               {1: [lines[0][0], lines[2][0], lines[3][0]],
                2: [lines[1][0]]},
               "decoys off by 0.01 / wrong-k; none appears in a solution")

    # ---- 3. shared-line-contention --------------------------------------
    # H1 (k=2, 300.00) and H2 (k=2, 320.00) are each individually matchable
    # using popular line a (H1 also via a+b, H2 only via a+e), but a can
    # serve only one of them: the single cross-compatible assignment is
    # H1<-c+d, H2<-a+e. A decoy line at 100.01 sits 0.01 over H1's price of
    # a, so the near-miss swap looks locally right and is not.
    price = [10000, 20000, 14000, 16000, 22000, 10001]
    taken = set()
    lines = [(unique_desc(rng, taken), p) for p in price]
    headers = [(1, 30000, 2), (2, 32000, 2)]
    lines = add_fillers(rng, lines, headers, taken, 2)
    gt = {1: [lines[2][0], lines[3][0]], 2: [lines[0][0], lines[4][0]]}
    sols, combos = all_solutions(headers, lines)
    a_idx = {i for i, (_, p) in enumerate(lines) if p == 10000}
    check(len(combos[1]) == 2 and (0, 1) in combos[1] and (2, 3) in combos[1],
          "contention: H1 combos unchanged by fillers")
    check(len(combos[2]) == 1 and combos[2][0] == (0, 4),
          "contention: H2 must have exactly one combo, on popular line a")
    check(len(sols) == 1 and sols[0] == gt_maps(gt, lines),
          "contention: exactly one cross-compatible assignment must exist")
    check(any(p == 10001 for _, p in lines),
          "contention: 0.01-off twin of the popular line must be present")
    g1, _ = greedy_first_fit(headers, lines, [1, 2])
    check(not g1, "contention: CSV-order first-fit (H1 grabs 'a') must FAIL")
    g2, assign = greedy_first_fit(headers, lines,
                                  mcf_order([1, 2])(headers, combos))
    check(g2, "contention: most-constrained-first must succeed here")
    check(len(lines) <= 14, "contention: <= 14 lines")
    write_case("shared-line-contention", headers, lines, True, gt,
               "both headers need line a; only one joint assignment exists")

    # ---- 4. poisoned-k ---------------------------------------------------
    # H1 (k=2, 1000.00) has MANY (4) 2-subsets at target. H2 (k=2, 500.00)
    # is forced onto b1+c1 and H3 (k=1, 450.00) is forced onto d1, which
    # kills the b, c and d pairs -- only the a pair (placed LAST in the CSV,
    # behind three lookalike pairs) coexists.
    price = [20000, 80000, 30000, 70000, 45000, 55000, 10000, 90000]
    taken = set()
    lines = [(unique_desc(rng, taken), p) for p in price]
    headers = [(1, 100000, 2), (2, 50000, 2), (3, 45000, 1)]
    sols, combos = all_solutions(headers, lines)
    check(len(combos[1]) >= 4, "poisoned-k: k=2 header must have MANY combos")
    check(combos[1] == [(0, 1), (2, 3), (4, 5), (6, 7)],
          "poisoned-k: the four lookalike pairs, a-pair last")
    check(combos[2] == [(0, 2)] and combos[3] == [(4,)],
          "poisoned-k: H2/H3 must be forced")
    coexisting = {p for p in combos[1] if any(s[1] == p for s in sols)}
    check(coexisting == {(6, 7)},
          "poisoned-k: exactly one of H1's pairs must coexist")
    check(len(sols) == 1 and sols[0] == {1: (6, 7), 2: (0, 2), 3: (4,)},
          "poisoned-k: joint solution must be unique")
    g1, _ = greedy_first_fit(headers, lines, [1, 2, 3])
    check(not g1, "poisoned-k: CSV-order first-fit must FAIL")
    write_case("poisoned-k", headers, lines, True,
               {1: [lines[6][0], lines[7][0]],
                2: [lines[0][0], lines[2][0]],
                3: [lines[4][0]]},
               "4 pairs at target; only the last-in-CSV pair coexists")

    print("wrote 4 adversarial-decoy cases under", BASE)


if __name__ == "__main__":
    main()