"""Generate duplicate-price / symmetry stress cases for the order matcher.

Writes, inside tests/duplicates-symmetry/, one sub-case directory each:
  all-identical        8 lines, all the SAME price; k=1..3, targets = exact multiples
  few-distinct-prices  13 lines, only 3 distinct prices; several headers (colliding targets)
  mirror-pairs         two headers whose targets stay satisfied if a line is swapped between them
  one-duplicate-target two headers with the SAME total_price AND total_lines, from duplicated pairs

Each sub-case gets order_headers.csv (id,total_price,total_lines),
order_lines.csv (description,price) and expected.json
{"expect_solvable": true, "ground_truth": {<id>: [desc, ...]}}.

Also reports the exact number of distinct full matchings per case
(brute-forced with itertools.combinations over the small instances),
since in these categories many valid matchings coexist.
"""

import csv
import json
import os
import random
from itertools import combinations

SEED = 20261021
BASE = os.path.dirname(os.path.abspath(__file__))

ADJ = ["adaptive", "business-focused", "centralized", "digitized", "exclusive",
       "fluctuating", "grid-enabled", "horizontal", "integrated", "managed"]
NOUN = ["matrix", "projection", "synergy", "database", "circuit", "protocol",
        "archive", "interface", "benchmark", "firmware"]


def fmt(cents):
    return f"{cents / 100:.2f}"


def make_case(rng, prices, counts, headers, gt):
    """prices: list of distinct cent values; counts: multiplicity per price.

    headers: list of (target_cents, k). gt: list of cent-value lists per header.
    Returns (header_rows, lines, ground_truth dict).
    """
    pool = []
    for cents_val, n in zip(prices, counts):
        pool += [cents_val] * n
    lines_used = sum(len(x) for x in gt)
    assert sum(counts) >= lines_used

    descs, seen = [], set()
    n = sum(counts)
    for i in range(n):
        while True:
            d = f"{rng.choice(ADJ)} {rng.choice(NOUN)} {i:03d}"
            if d not in seen:
                seen.add(d)
                descs.append(d)
                break

    # Order lines grouped by price; descriptions were randomized above.
    _ = rng  # keep rng referenced for clarity
    lines = list(zip(descs, pool))[:n]

    header_rows = [{"id": hid, "total_price": fmt(t), "total_lines": k}
                   for hid, (t, k) in enumerate(headers, start=1)]

    # Ground truth: assign the (already valid) groups to descriptions.
    assigned = []  # per header: list of chosen line indices
    avail = list(range(n))
    for hidx, ((t, k), group) in enumerate(zip(headers, gt)):
        assert sum(group) == t and len(group) == k
        # pick unused lines whose values match this group exactly
        need = list(group)
        chosen = []
        for idx in avail:
            if not need:
                break
            p = lines[idx][1]
            if p in need:
                need.remove(p)
                chosen.append(idx)
        assert not need, f"no lines for header {hidx + 1}: {group}"
        for idx in chosen:
            assert idx in avail and avail.remove(idx) is None
        assigned.append((hidx, [lines[i][0] for i in chosen]))
    assert len(assigned) == len(headers)
    ground_truth = {str(hid + 1): descs for hid, descs in assigned}
    return header_rows, lines, ground_truth


def count_matchings(headers, lines, cap=1000000):
    """Exact brute-force count of full matchings (all headers matched)."""
    combos = {}
    for (target, k) in headers:
        cs = [c for c in combinations(range(len(lines)), k)
              if sum(lines[i][1] for i in c) == target]
        if not cs:
            return 0
        combos[(target, k)] = cs
    used = [False] * len(lines)
    total = 0

    def dfs(i):
        nonlocal total
        if i == len(headers):
            total += 1
            return total < cap
        for c in combos[headers[i]]:
            if not any(used[j] for j in c):
                for j in c:
                    used[j] = True
                ok = dfs(i + 1)
                for j in c:
                    used[j] = False
                if not ok:
                    return False
        return True

    dfs(0)
    return total


CASES = {
    "all-identical": dict(
        prices=[1000], counts=[8],
        headers=[(1000, 1), (2000, 2), (3000, 3)],
        gt=[[1000], [1000, 1000], [1000, 1000, 1000]],
    ),
    "few-distinct-prices": dict(
        prices=[500, 750, 1225], counts=[5, 4, 3],
        headers=[(1250, 2), (1250, 2), (2500, 4), (2450, 2), (1725, 2)],
        gt=[[500, 750], [500, 750], [500, 500, 750, 750],
            [1225, 1225], [500, 1225]],
    ),
    "mirror-pairs": dict(
        prices=[300, 700, 400, 600, 900, 1100], counts=[2, 2, 2, 2, 1, 1],
        headers=[(1000, 2), (1000, 2), (900, 1), (1100, 1)],
        gt=[[300, 700], [400, 600], [900], [1100]],
    ),
    "one-duplicate-target": dict(
        prices=[500, 600, 700], counts=[2, 2, 2],
        headers=[(1100, 2), (1100, 2), (1400, 2)],
        gt=[[500, 600], [500, 600], [700, 700]],
    ),
}


def write_case(name, header_rows, lines, ground_truth):
    d = os.path.join(BASE, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "order_headers.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for r in header_rows:
            w.writerow([r["id"], r["total_price"], r["total_lines"]])
    with open(os.path.join(d, "order_lines.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for desc, price in lines:
            w.writerow([desc, fmt(price)])
    with open(os.path.join(d, "expected.json"), "w") as f:
        json.dump({"expect_solvable": True, "ground_truth": ground_truth},
                  f, indent=2)


def main():
    rng = random.Random(SEED)
    for name, spec in CASES.items():
        header_rows, lines, gt = make_case(
            rng, spec["prices"], spec["counts"], spec["headers"], spec["gt"])
        n_match = count_matchings(spec["headers"], lines)
        assert n_match > 0, f"{name}: ground truth cannot exist (unsolvable)"
        write_case(name, header_rows, lines, gt)
        print(f"{name}: {len(header_rows)} headers, {len(lines)} lines, "
              f"distinct full matchings = {n_match}")


if __name__ == "__main__":
    main()