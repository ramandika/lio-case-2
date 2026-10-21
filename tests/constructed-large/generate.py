"""Generate medium-size realistic order-matching test cases.

For each sub-case the generator samples ground-truth bundles FIRST
(k lines per header, k in 1..10 subject to k_max for solver runtime),
sets total_price to the exact bundle sum, then adds random decoy lines
that belong to no bundle.  This guarantees every instance is solvable
and that ground truth is a valid matching.

Output per sub-case directory:
  order_headers.csv  (id,total_price,total_lines)
  order_lines.csv    (description,price)
  expected.json      {"expect_solvable": true, "ground_truth": {...}}

Usage: python3 -I tests/constructed-large/generate.py   (from repo root)
"""

import csv
import json
import os
import random

SEED = 20260715
BASE = os.path.dirname(os.path.abspath(__file__))

ADJECTIVES = [
    "Premium", "Ergonomic", "Wireless", "Compact", "Durable", "Organic",
    "Refurbished", "Industrial", "Portable", "Heavy-duty", "Foldable",
    "Adjustable", "Stainless", "Recycled", "Professional", "Lightweight",
    "Digital", "Modular", "Insulated", "Reinforced", "Smart", "Solar",
    "Bluetooth-enabled", "Anti-static", "Weatherproof", "Stackable",
    "Collapsible", "Artisanal", "Matte-finish", "Cushioned", "Vented",
    "Water-resistant", "Brushed-steel", "Silicone-grip", "Double-wall",
    "Magnetic", "Tamper-proof", "Low-profile", "Wide-mouth", "Self-sealing",
]

NOUNS = [
    "keyboard", "mouse", "backpack", "notebook", "water bottle", "cable",
    "wall charger", "tripod", "headphones", "webcam", "desk lamp",
    "stapler", "clipboard", "marker set", "utility knife", "power bank",
    "tool kit", "thermos", "laptop stand", "label maker", "calculator",
    "padlock", "extension cord", "work gloves", "safety goggles",
    "storage bin", "whiteboard", "printer ink", "paper ream", "binder",
    "envelope pack", "laminator", "hand scanner", "projector",
    "wireless router", "keyboard tray", "footrest", "desk organizer",
    "tape dispenser", "index cards", "clipboard holder", "usb hub",
]

# Case spec: (dir name, #headers, #decoys, k max, k weights, max truth lines)
CASES = [
    ("1-small-medium", 5, 8, 10, [3, 3, 2, 2, 1, 1, 1, 0.5, 0.5, 0.5], 14),
    ("2-medium", 10, 20, 5, [2, 3, 3, 2, 1], 30),
    ("3-medium-large", 20, 70, 4, [2, 3, 5, 1], 48),
    ("4-decoy-heavy", 8, 65, 4, [0, 0, 1, 5], 32),
]


def sample_ks(rng, n, k_max, weights, truth_cap):
    """Draw n header sizes, shrinking until the truth-line budget holds."""
    ks = rng.choices(range(1, k_max + 1), weights=weights, k=n)
    while sum(ks) > truth_cap:
        i = max(range(n), key=lambda i: ks[i])
        if ks[i] <= 1:
            break
        ks[i] -= 1
    return ks


def fmt(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def generate_case(rng, name, n_headers, n_decoys, k_max, weights, truth_cap):
    out_dir = os.path.join(BASE, name)
    os.makedirs(out_dir, exist_ok=True)

    ks = sample_ks(rng, n_headers, k_max, weights, truth_cap)
    header_ids = rng.sample(range(101, 900), n_headers)

    bundles = []        # list of (header_id, k, total_cents, [prices])
    sku = 10000
    for hid, k in zip(header_ids, sorted(ks, reverse=True)):
        k = max(1, min(10, int(k)))
        prices = [rng.randint(300, 30000) for _ in range(k)]
        bundles.append((hid, k, sum(prices), prices))

    n_truth = sum(b[1] for b in bundles)
    n_decoys_used = max(n_decoys, 1) if n_truth < 1 else n_decoys

    lines = []  # (description, price_cents, header_id or None)
    truth = {}
    for hid, k, total, prices in bundles:
        descs = []
        for p in prices:
            sku += rng.randint(1, 97)
            desc = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} (SKU {sku})"
            lines.append((desc, p, hid))
            descs.append(desc)
        truth[str(hid)] = descs

    for _ in range(n_decoys_used):
        sku += rng.randint(1, 97)
        desc = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} (SKU {sku})"
        lines.append((desc, rng.randint(300, 30000), None))

    rng.shuffle(lines)

    headers_path = os.path.join(out_dir, "order_headers.csv")
    lines_path = os.path.join(out_dir, "order_lines.csv")
    expected_path = os.path.join(out_dir, "expected.json")

    with open(headers_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "total_price", "total_lines"])
        for hid, k, total, _ in sorted(bundles):
            w.writerow([hid, fmt(total), k])

    with open(lines_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["description", "price"])
        for desc, price, _ in lines:
            w.writerow([desc, fmt(price)])

    with open(expected_path, "w") as f:
        json.dump({"expect_solvable": True, "ground_truth": truth}, f, indent=2)
        f.write("\n")

    print(f"{name}: {n_headers} headers, {len(lines)} lines "
          f"({n_truth} truth + {n_decoys_used} decoys), "
          f"ks={sorted(ks, reverse=True)}")


def main():
    rng = random.Random(SEED)
    for name, n_headers, n_decoys, k_max, weights, truth_cap in CASES:
        generate_case(rng, name, n_headers, n_decoys, k_max, weights, truth_cap)


if __name__ == "__main__":
    main()