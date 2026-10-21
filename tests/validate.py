"""Validate one or more test-case directories against ../solve.py.

A case directory must contain:
  order_headers.csv   (id,total_price,total_lines)
  order_lines.csv     (description,price)
  expected.json       {"expect_solvable": bool,
                       "ground_truth": {"<header id>": [descriptions]} or null}

Validation (README criteria):
  - if expect_solvable: solver must succeed and its output must be a valid
    matching (exact count per header, exact cent sum, no line reused).
    The solver's assignment may differ from ground_truth (README allows
    multiple valid combinations); ground_truth is checked separately as a
    generator sanity assertion.
  - if not expect_solvable: solver must exit non-zero (no matching).

Usage: python3 -I tests/validate.py <case_dir> [<case_dir> ...]
       python3 -I tests/validate.py tests            # all cases under tests/
"""

import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOLVER = os.path.join(os.path.dirname(HERE), "solve.py")


def cents(value: str) -> int:
    return round(float(value) * 100)


def load_headers(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return ({int(r["id"]): cents(r["total_price"]) for r in rows},
            {int(r["id"]): int(r["total_lines"]) for r in rows})


def load_lines(path):
    with open(path, newline="") as f:
        return [(r["description"], cents(r["price"])) for r in csv.DictReader(f)]


def run_case(case_dir):
    errors = []
    headers_dir = os.path.join(case_dir, "order_headers.csv")
    lines_dir = os.path.join(case_dir, "order_lines.csv")
    expected_path = os.path.join(case_dir, "expected.json")
    if not all(os.path.exists(p) for p in (headers_dir, lines_dir, expected_path)):
        return [f"missing input file(s) in {case_dir}"]

    target, k = load_headers(headers_dir)
    lines = load_lines(lines_dir)
    desc_set = {d for d, _ in lines}
    with open(expected_path) as f:
        expected = json.load(f)

    # Generator sanity: ground truth (if given) must itself be valid.
    if expected.get("ground_truth") is not None:
        used = set()
        for hid, descs in expected["ground_truth"].items():
            hid = int(hid)
            if hid not in target or len(descs) != k[hid]:
                errors.append(f"ground_truth invalid for header {hid}")
                continue
            prices = []
            for d in descs:
                if d not in desc_set:
                    errors.append(f"ground_truth line '{d}' not in order_lines.csv")
                elif d in used:
                    errors.append(f"ground_truth reuses line '{d}'")
                else:
                    used.add(d)
                    prices.append(next(p for dd, p in lines if dd == d))
            if sum(prices) != target[hid]:
                errors.append(f"ground_truth sum mismatch for header {hid}: "
                              f"{sum(prices)} != {target[hid]}")

    out_path = os.path.join(case_dir, "solver_output.json")
    proc = subprocess.run([sys.executable, "-I", SOLVER,
                           headers_dir, lines_dir, out_path],
                          capture_output=True, text=True, cwd=case_dir)
    solvable = expected["expect_solvable"]

    if proc.returncode != 0:
        if solvable:
            errors.append(f"solver failed on a solvable instance: "
                          f"{proc.stderr.strip() or proc.returncode}")
        return errors

    if not solvable:
        errors.append("solver claims a matching exists on an infeasible instance")
        return errors

    with open(out_path) as f:
        matched = json.load(f)

    used = set()
    seen_ids = set()
    for entry in matched:
        hid = entry["id"]
        seen_ids.add(hid)
        got_cents = round(entry["total_price"] * 100)
        if got_cents != target[hid]:
            errors.append(f"order {hid}: reported total {got_cents} != {target[hid]}")
        if entry["total_lines"] != k[hid]:
            errors.append(f"order {hid}: total_lines {entry['total_lines']} != {k[hid]}")
        if len(entry["order_lines"]) != k[hid]:
            errors.append(f"order {hid}: {len(entry['order_lines'])} lines != {k[hid]}")
        s = 0
        for ln in entry["order_lines"]:
            d, c = ln["description"], cents(str(ln["price"]))
            if d not in desc_set:
                errors.append(f"order {hid}: unknown line '{d}'")
            elif d in used:
                errors.append(f"order {hid}: line '{d}' reused across orders")
            else:
                used.add(d)
            if c != next((p for dd, p in lines if dd == d), None):
                errors.append(f"order {hid}: price mismatch for '{d}'")
            s += c
        if s != target[hid]:
            errors.append(f"order {hid}: line sum {s} != {target[hid]}")

    expected_ids = set(target) if solvable else set()
    missing = expected_ids - seen_ids
    if missing:
        errors.append(f"headers not matched: {sorted(missing)}")

    return errors


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    # Solver runs with cwd=case_dir, so cases must be resolved absolutely.
    args = [os.path.abspath(a) for a in args]
    dirs = []
    for a in args:
        if os.path.isdir(a) and not os.path.exists(os.path.join(a, "expected.json")):
            for root, _, _files in os.walk(a):
                if os.path.exists(os.path.join(root, "expected.json")):
                    dirs.append(root)
        else:
            dirs.append(a)
    dirs.sort()
    failed = 0
    for case in dirs:
        errs = run_case(case)
        if errs:
            failed += 1
            print(f"FAIL {case}")
            for e in errs:
                print(f"     - {e}")
        else:
            print(f"PASS {case}")
    print(f"\n{len(dirs) - failed}/{len(dirs)} cases passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()