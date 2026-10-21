"""Match order headers with order lines (Challenge 2).

Each header must be matched with exactly `total_lines` lines whose prices
sum to `total_price`, and every line can belong to at most one order.
Prices are handled as integer cents to avoid floating-point drift.
"""

import csv
import json
import os
import sys
from itertools import combinations


def cents(value: str) -> int:
    return round(float(value) * 100)


def load_headers(path):
    with open(path, newline="") as f:
        return [
            {"id": int(row["id"]), "target": cents(row["total_price"]),
             "k": int(row["total_lines"])}
            for row in csv.DictReader(f)
        ]


def load_lines(path):
    with open(path, newline="") as f:
        return [
            {"description": row["description"], "price": cents(row["price"])}
            for row in csv.DictReader(f)
        ]


def candidate_combos(lines, target, k):
    """All k-line subsets summing to target, as index tuples."""
    results = []
    for combo in combinations(range(len(lines)), k):
        if sum(lines[i]["price"] for i in combo) == target:
            results.append(combo)
    return results


def solve(headers, lines):
    """Exact backtracking: assign the most-constrained header first."""
    combos = {h["id"]: candidate_combos(lines, h["target"], h["k"])
              for h in headers}
    for h in headers:
        if not combos[h["id"]]:
            return None  # this header can never be matched

    order_lines = [None] * len(lines)
    solution = {}

    def backtrack(remaining):
        if not remaining:
            return True
        # Most-constrained-first: fewest candidate combos left.
        hid = min(remaining, key=lambda i: len(combos[i]))
        rest = [i for i in remaining if i != hid]
        for combo in combos[hid]:
            if any(order_lines[i] is not None for i in combo):
                continue
            for i in combo:
                order_lines[i] = hid
            solution[hid] = combo
            if backtrack(rest):
                return True
            for i in combo:
                order_lines[i] = None
            del solution[hid]
        return False

    if not backtrack([h["id"] for h in headers]):
        return None

    return solution


def main(argv):
    base = os.path.dirname(os.path.abspath(__file__))
    headers_path = argv[1] if len(argv) > 1 else os.path.join(base, "order_headers.csv")
    lines_path = argv[2] if len(argv) > 2 else os.path.join(base, "order_lines.csv")
    out_path = argv[3] if len(argv) > 3 else os.path.join(base, "matched_orders.json")

    headers = load_headers(headers_path)
    lines = load_lines(lines_path)

    solution = solve(headers, lines)
    if solution is None:
        sys.exit("No valid matching exists for the given input.")

    output = [
        {
            "id": h["id"],
            "total_price": h["target"] / 100,
            "total_lines": h["k"],
            "order_lines": [
                {"description": lines[i]["description"],
                 "price": lines[i]["price"] / 100}
                for i in solution[h["id"]]
            ],
        }
        for h in sorted(headers, key=lambda h: h["id"])
    ]
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    matched = sum(len(v) for v in solution.values())
    print(f"Matched {len(solution)}/{len(headers)} headers "
          f"using {matched}/{len(lines)} lines -> {out_path}")
    for entry in output:
        got = sum(l["price"] for l in entry["order_lines"])
        print(f"  order {entry['id']}: {entry['total_lines']} lines, "
              f"sum {got:.2f} (target {entry['total_price']:.2f})")


if __name__ == "__main__":
    main(sys.argv)