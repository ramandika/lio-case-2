# Test Suite — Order Header ↔ Order Line matching

Validate everything:

```bash
python3 -I tests/validate.py tests
```

Validator (`validate.py`) runs `solve.py` on every case, then enforces the
README criteria: per-header line count == `total_lines`, cent-exact sum ==
`total_price`, no line reused, and for `expect_solvable: false` cases the
solver must report no matching. A case's `ground_truth` is sanity-checked but
the solver's assignment may differ — duplicate prices often admit many valid
matchings (counts verified by brute force are noted below).

Each category has a deterministic `generate.py` (fixed seed) that regenerates
its cases and self-verifies (brute-force proofs of infeasibility/uniqueness/
matching counts).

## Categories (44 cases)

| Kategori | Case | Cakupan |
|---|---|---|
| `baseline-original` / `sanity-infeasible` | 2 | dataset asli challenge + infeasible minimal |
| `baseline-minimal` | 4 | 1 header/1 line … partition penuh |
| `duplicates-symmetry` | 4 | harga duplikat; jumlah matching valid global 4–2.160 (brute force) |
| `infeasible-varieties` | 5 | sum/count impossible, resource exhaustion, contention murni, jebakan float > 2^53 (beda 1 sen tapi float-nya tampak cocok) |
| `forced-unique` | 4 | solusi global unik, dibuktikan brute-force (superincreasing, pinning chain, dll.) |
| `money-precision` | 5 | carry chain .99, total ~$96 rb, bundle beda persis 0.01, sum yang bergeser 1.562 sen pada float ~$88 T |
| `boundary-cardinality` | 4 | k=1 semua, k=10 (maks README), campuran k=1/2/9/10, perfect assignment |
| `dense-hard` | 4 | dekat phase-transition; jumlah matching valid global 2–64 |
| `constructed-large` | 4 | 20–115 line dengan decoy; runtime 0.1s–18.8s |
| `perf-stress` | 4 | 100–300 line; runtime 4.3s–221.4s |
| `adversarial-decoys` | 4 | decoy anti-greedy; solver backtracking lolos semua trap, greedy/ordering naif jatuh |

## Temuan kinerja (dari perf-stress)

Biaya dominan solver adalah enumerasi per header, Σ C(n,k) — jadi **k
(number of lines per header), bukan jumlah line total, yang mendominasi**.
Pada n≈300 dan k=10, C(300,10) ≈ 1.6×10^17 kombinasi membuat solver naif tak
pernah selesai (`wide-k10` dikunci ke n=32, masih 221s). Langkah optimasi
berikutnya: enumerasi sadar-sum (prune k feasibility via prefix bounds /
meet-in-the-middle), atau CP-SAT dengan table constraint per header.