"""Industry-style staged order-matching engine.

Mirrors the practices verified in the industry deep-research
(deep-research-order-matching.md, riset #2):

  Stage 0  Policy check      — total_lines must be 1..10 (README rule); prices
                               must be positive. Violations go to review/blocked,
                               like an ERP hold instead of a crash.
  Stage R  Reference binding — exact document-number evidence extracted from
                               line descriptions ("PO 3", "#3", "ORDER 42"),
                               BC-style, explicitly NOT fuzzy (Microsoft Learn:
                               "It isn't fuzzy matching or an AI confidence
                               score"). Binds only when globally unambiguous.
  Stage S  Bounded search    — exact subset-sum over the remaining pool with
                               sum-feasibility bounds (prefix min/max), the way
                               the SSMP paper bounds its searches; a node budget
                               mirrors SupplierRecon's capped window: headers
                               that exceed it fall to review instead of grinding.
  Stage V  Review queue      — unresolved/blocked headers get ranked candidate
                               bundles (human review, never auto-matched) in a
                               side report, SAP-style payment-block rather than
                               a wrong auto-match.

Configurable tolerance (--tolerance-cents, default 0 = exact, the challenge's
rule) and duplicate-line detection report, both ERP-conventional.

Output: <out>.json is the matched-orders list (same schema as solve.py, plus
per-order status/resolved_by audit fields); <out>_report.json holds the audit
trail, detection notes, and the review queue.

Unresolved headers exit non-zero (mirroring an unpayable invoice), but the
report file is still written.
"""

import argparse
import csv
import json
import re
import sys

# Exact reference patterns only — no fuzzy matching, per BC's documented rule.
REF_PATTERNS = re.compile(
    r"#\s*(\d{1,6})\b|\bPO[-_ ]?(\d{1,6})\b|\border[-_ ]?no\.?\s*(\d{1,6})\b",
    re.IGNORECASE,
)


def cents(value: str) -> int:
    return round(float(value) * 100)


class SearchBudgetExceeded(Exception):
    """Raised when the engine-wide bounded-search node budget runs out."""


def load_headers(path):
    with open(path, newline="") as f:
        return [
            {"id": int(r["id"]), "target": cents(r["total_price"]),
             "k": int(r["total_lines"])}
            for r in csv.DictReader(f)
        ]


def load_lines(path):
    with open(path, newline="") as f:
        return [
            {"idx": i, "description": r["description"], "price": cents(r["price"])}
            for i, r in enumerate(csv.DictReader(f))
        ]


def extract_refs(description):
    """Exact order-reference evidence in a line description, or []."""
    refs = []
    for m in REF_PATTERNS.finditer(description):
        refs.append(int(next(g for g in m.groups() if g is not None)))
    return refs


def suffix_bounds(prices, k):
    """mins[i][r] / maxs[i][r] = min/max sum of r elements from prices[i:]."""
    m = len(prices)
    mins = [[0] * (k + 1) for _ in range(m + 1)]
    maxs = [[0] * (k + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for r in range(1, k + 1):
            take = prices[i]
            if r > 1:
                take += mins[i + 1][r - 1] if i + 1 <= m else 0
            rest = mins[i + 1][r] if (m - i - 1) >= r else None
            mins[i][r] = take if rest is None else min(rest, take)
    for i in range(m - 1, -1, -1):
        for r in range(1, k + 1):
            take = prices[i]
            if r > 1:
                take += maxs[i + 1][r - 1]
            rest = maxs[i + 1][r] if (m - i - 1) >= r else None
            maxs[i][r] = take if rest is None else max(rest, take)
    return mins, maxs


def iter_bounded_subsets(candidates, k, target, tol, counter, budget):
    """Yield k-subsets of candidates summing into [target-tol, target+tol] in
    bounded-search order; DFS with sum-feasibility bounds. `counter`/`budget`
    cap total nodes across the whole run — the industry-style search window:
    exceeding it stops enumeration (caller falls back to the review queue).
    """
    c = sorted(candidates, key=lambda t: t[1])
    prices = [p for _, p in c]
    m = len(c)
    mins, maxs = suffix_bounds(prices, k)

    def dfs(start, depth, chosen, s):
        counter["nodes"] += 1
        if counter["nodes"] > budget:
            raise SearchBudgetExceeded
        r = k - depth
        if r == 0:
            if abs(s - target) <= tol:
                yield [c[i][0] for i in chosen]
            return
        if m - start < r:
            return
        for i in range(start, m - r + 1):
            v = prices[i]
            s1 = s + v
            lo = s1 + mins[i + 1][r - 1]
            hi = s1 + maxs[i + 1][r - 1]
            if lo - tol > target:
                break  # prices ascending: nothing further can help
            if hi + tol < target:
                continue
            chosen.append(i)
            yield from dfs(i + 1, depth + 1, chosen, s1)
            chosen.pop()

    yield from dfs(0, 0, [], 0)


def rank_review_bundles(lines, target, k, tol, top=3):
    """Top candidate bundles for human review, closest-sum first."""
    by_price = sorted(((l["idx"], l["price"]) for l in lines),
                      key=lambda t: t[1])
    results = []
    for combo_idx, combo in enumerate(_iter_k_subsets(by_price, k, limit=20000)):
        s = sum(p for _, p in combo)
        if abs(s - target) <= tol or True:  # rank by closeness always
            results.append((abs(s - target), s, [i for i, _ in combo]))
    results.sort(key=lambda t: (t[0], t[1]))
    return results[:top]


def _iter_k_subsets(by_price, k, limit):
    import itertools
    count = 0
    for combo in itertools.combinations(by_price, k):
        count += 1
        if count > limit:
            break
        yield combo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("headers")
    ap.add_argument("lines")
    ap.add_argument("out")
    ap.add_argument("--tolerance-cents", type=int, default=0,
                    help="ERP-style tolerance band around each total (default 0 = exact)")
    ap.add_argument("--node-budget", type=int, default=500000,
                    help="max search nodes per header before review queue")
    ap.add_argument("--max-lines-per-header", type=int, default=10)
    args = ap.parse_args(argv)

    tol = args.tolerance_cents
    headers = load_headers(args.headers)
    all_lines = load_lines(args.lines)
    report = {"config": {"tolerance_cents": tol,
                         "node_budget": args.node_budget},
              "policy_flags": [], "duplicates": [], "audit": [],
              "review": []}

    used = {l["idx"] for l in all_lines
            if l["price"] <= 0}
    if used:
        report["policy_flags"].append(
            f"excluded {len(used)} non-positive-price lines (policy: prices are positive)")

    # Duplicate-line detection (ERP-conventional duplicate check, report only).
    sigs = {}
    for l in all_lines:
        sigs.setdefault((l["description"], l["price"]), []).append(l["idx"])
    report["duplicates"] = [
        {"description": d, "price_cents": p, "count": len(idxs)}
        for (d, p), idxs in sigs.items() if len(idxs) > 1
    ]

    lines = [l for l in all_lines if l["idx"] not in used]
    refs = {l["idx"]: extract_refs(l["description"]) for l in lines}
    with_refs = {i: rs for i, rs in refs.items() if rs}
    if with_refs:
        report["audit"].append({"stage": "R", "note":
            f"{len(with_refs)} line(s) carry exact order-reference evidence"})

    def take(idxs, hid, stage):
        for i in idxs:
            used.add(i)
        report["audit"].append({"header": hid, "stage": stage,
                                "lines": idxs})

    orders = []
    stage = "R"
    # Stage R: bind references only when globally unambiguous (k=1, exactly
    # one line carries exactly this header's reference, price matches).
    for h in sorted(headers, key=lambda x: x["id"]):
        if h["k"] != 1:
            continue
        cand = [l for l in lines if l["idx"] not in used
                and len(refs[l["idx"]]) == 1 and refs[l["idx"]][0] == h["id"]]
        if len(cand) == 1 and abs(cand[0]["price"] - h["target"]) <= tol:
            take([cand[0]["idx"]], h["id"], stage)
            orders.append(_order(h, [cand[0]], "MATCHED_EXACT_REF", stage))

    stage = "P"
    # Stage 0: policy check.
    ok_headers, blocked = [], []
    for h in headers:
        if any(o["id"] == h["id"] for o in orders):
            continue
        if not (1 <= h["k"] <= args.max_lines_per_header):
            blocked.append(h)
            report["policy_flags"].append(
                f"header {h['id']}: total_lines={h['k']} outside 1..{args.max_lines_per_header} -> BLOCKED")
        else:
            ok_headers.append(h)

    stage = "S"
    # Stage S: bounded search with GLOBAL backtracking across headers.
    # A first-found bundle is committed tentatively; on a dead end the engine
    # undoes it and tries the header's next candidate (the exact trap the
    # adversarial test suite encodes for naive greedy fills).
    free0 = [l for l in lines if l["idx"] not in used]
    remaining = sorted(
        ok_headers,
        key=lambda h: (h["k"],
                       sum(1 for l in free0 if l["price"] <= h["target"]),
                       h["id"]))
    search_state = {"nodes": 0}

    def solve_from(i):
        if i == len(remaining):
            return True
        h = remaining[i]
        free = [l for l in lines if l["idx"] not in used]
        cands = [(l["idx"], l["price"]) for l in free]
        header_nodes = {"nodes": 0}
        it = iter_bounded_subsets(cands, h["k"], h["target"], tol,
                                  header_nodes, args.node_budget)
        try:
            for idxs in it:
                chosen = sorted((l for l in free if l["idx"] in idxs),
                                key=lambda l: l["idx"])
                take([l["idx"] for l in chosen], h["id"], stage)
                orders.append(_order(h, chosen, "MATCHED_BOUNDED_SEARCH",
                                     stage))
                if solve_from(i + 1):
                    return True
                # undo this tentative binding and try this header's next bundle
                for l in chosen:
                    used.discard(l["idx"])
                report["audit"] = [a for a in report["audit"]
                                   if a.get("header") != h["id"]]
                orders[:] = [o for o in orders if o["id"] != h["id"]]
        except SearchBudgetExceeded:
            # Industry-style cap: this header's window is too wide right now —
            # park it in review and let the rest of the headers proceed.
            budget_limited.append(h)
            return solve_from(i + 1)
        return False

    budget_limited = []
    unmatched = []
    if not solve_from(0):
        # No global matching exists for the remaining headers within the
        # bounded window — industry behavior: review queue + non-zero exit
        # (an unpayable invoice), never a silently dropped header.
        unmatched = list(remaining)
    unmatched.extend(h for h in budget_limited
                     if h["id"] not in {u["id"] for u in unmatched})

    stage = "V"
    # Stage V: review queue for unmatched headers (never auto-matched).
    free = [l for l in lines if l["idx"] not in used]
    for h in blocked:
        report["review"].append({"header_id": h["id"],
                                 "status": "BLOCKED_POLICY",
                                 "reason": "total_lines outside allowed range"})
    for h in unmatched:
        status = ("NEEDS_REVIEW_BUDGET" if h in budget_limited
                  else "NO_VALID_COMBINATION")
        cands = rank_review_bundles(free, h["target"], h["k"], tol)
        report["review"].append({
            "header_id": h["id"], "status": status,
            "closest_candidates": [
                {"sum": s / 100, "delta_cents": d,
                 "descriptions": [next(l["description"] for l in free
                                       if l["idx"] == i) for i in idxs]}
                for d, s, idxs in cands]})

    orders.sort(key=lambda o: o["id"])
    with open(args.out, "w") as f:
        json.dump(orders, f, indent=2)
    report_path = args.out.rsplit(".json", 1)[0] + "_report.json"
    report["summary"] = {
        "matched": len(orders),
        "blocked": len(blocked),
        "review": len(unmatched),
        "lines_used": len(used),
        "lines_total": len(lines),
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    s = report["summary"]
    print(f"[industry] matched {s['matched']}/{len(headers)} headers "
          f"({s['blocked']} blocked, {s['review']} to review) -> {args.out}")
    print(f"[industry] report -> {report_path}")
    review_or_block = s["blocked"] + s["review"]
    if review_or_block:
        sys.exit(f"No valid matching for {review_or_block} header(s) — "
                 f"see review queue in {report_path}")


def _order(h, chosen, status, stage):
    return {
        "id": h["id"],
        "total_price": h["target"] / 100,
        "total_lines": h["k"],
        "order_lines": [{"description": l["description"],
                         "price": l["price"] / 100} for l in chosen],
        "status": status,
    }


if __name__ == "__main__":
    main(sys.argv[1:])