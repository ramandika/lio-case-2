# Riset Mendalam: Algoritma Eksak untuk Order Header ↔ Order Line Matching

> Deep-research untuk Challenge 2 (rencana: mencocokkan ulang order header dengan order line yang koneksiannya hilang).
> Struktur masalah: **set partitioning dengan batasan kardinalitas** — tiap header butuh `total_lines` (1–10) line yang jumlahnya persis = `total_price`, dan tiap line hanya boleh dipakai satu header.
>
> Metodologi: 104 agent, 22 sumber (22 URL diambil), 109 klaim diekstrak, 25 klaim utama diverifikasi secara adversarial (3 pemilih, ≥2/3 untuk menolak). Hasil: **20 terkonfirmasi, 5 terbantahkan, 0 tak terverifikasi**, 12 temuan setelah sintesis.

---

## Gambaran besar: masalah terpecah jadi dua lapis

| Lapis | Bentuk masalah | Arti untuk order matching |
|---|---|---|
| **Pricing subproblem** | Cardinality-constrained k-Subset Sum (per header) | Mencari kombinasi 1–10 line yang jumlahnya = `total_price` |
| **Master problem** | Set partitioning | Menugaskan bundle ke header, tiap line tepat dipakai sekali |

Struktur ini **cocok persis** dengan formulasi set-partitioning umum Barnhart dkk. (*Operations Research* 46(3):316-329, 1998): ground set = order lines, subset feasible = bundle per header. Temuan penting: **saat semua subset punya aturan identik (kasus kita), formulasi berbasis kolom mengeliminasi simetri eksponensial** yang membuat branch-and-bound tampil buruk pada ILP biner kompak.

---

## 1. Subset-sum / k-SUM: batas kompleksitas teoritis

| Algoritma | Waktu | Ruang | Status |
|---|---|---|---|
| Schroeppel–Shamir (SIAM J. Comput. 1981) | O\*(2^{n/2}) | O\*(2^{n/4}) | Baseline klasik, **tidak terungguli >40 tahun** (sampai 2021) |
| Tradeoff keluarga S-S | T·S² = 2ⁿ | — | Dikonfirmasi Austrin dkk. (CCS 2013): T=2^{(n+g)/2}, S=2^{(n-g)/4} |
| Nederlof–Węgrzycki (STOC 2021) | O\*(2^{0.5n}) | O\*(2^{0.249999n}) (dirafinasi ke 2^{0.246n}, 2024) | Randomized, via reduksi ke Orthogonal Vectors |
| Bansal–Garg–Nederlof–Vyas (SICOMP 2018) | O\*(2^{0.86n}) | polynomial (randomized/Monte Carlo) | Menembus barier O\*(2ⁿ)-time + polynomial-space |
| Bellman-style DP, **k-Subset Sum** (Antonopoulos dkk., JCO 2022) | O(n·t^k), t = target maks | — | **Struktur sama persis dengan order matching** (k = jumlah header) |
| + batasan kardinalitas c | Õ((n^k·c^{k²})^{1/(k+1)} · t^k) | — | Blowup O(c^k) atas bound tanpa kardinalitas |

- k-Sum acak (model k-lists) bisa diselesaikan dengan probabilitas tinggi dalam Õ(n^{k-0.5}) waktu, O(log n) ruang — tapi modelnya beda dari subset-selection kita.
- **Semua varian DP pseudopolynomial terhadap nilai target `t`**: meledak saat nominal rupiah/dollar besar. Bitset DP menahan sampai t ~ 10⁸–10⁹ dengan n ratusan.

> ⚠️ **Model mismatch**: hampir semua bound teoritis di atas untuk model *decision single-target* / k-lists, bukan struktur "partisi semua line ke bundle fix-cardinality + fix-sum". Bound cardinality-aware juga belum punya validasi empiris — ini jaminan, bukan speedup terbukti.

---

## 2. Modeling solver: CP-SAT vs MIP

- Panduan resmi Google OR-Tools: untuk struktur *non-convex allowed-group* (kasus kita), **CP-SAT biasanya lebih cepat dari solver MIP**.
- Fitur kunci: `AddAllowedAssignments` (table constraint) — batasi kombinasi feasible **per grup** tanpa enumerasi cross-product penuh (contoh vendor: hindari 125 = 5×5×5 kombinasi).
- Benchmark vendor pada 12 worker / 6 task: **CP-SAT 0.0113 s vs SCIP-MIP 0.3281 s** (gap 29×), biaya optimal sama (239). Satu instans mainan — arah, bukan benchmark skala besar.
- Kontra: pada instans sulit Nurse Rostering (primer CP-SAT), **hanya Gurobi** yang mampu membuktikan optimal; CP-SAT gagal. (Caveat zaman: perbandingan ini sebelum symmetry handling modern Gurobi/CPLEX — *orbital fixing* — yang bisa menebus sebagian penalti simetri formulasi kompak.)

Ilustrasi praktis: CP-SAT membuktikan optimal knapsack 100 item (kapasitas 2000) dalam **0.01 s** meski ruang cari sekitar 2¹⁰⁰.

---

## 3. Column generation & branch-and-price (skala besar)

- **Jangan pernah enumerasi kolom lalu sembukan ke IP** ("fixed-pool" gagal): instans crew pairing 400 flight — 9,400 pairing pra-generasi memberi solusi IP biaya 13,000, ditinggalkan setelah **2 hari CPU**; generasi kolom inside-the-tree mencapai biaya 800. (Barnhart dkk. 1998; angka 1990-an, hardware lama.)
- Branch-and-price (branch-and-bound + column generation di tiap node) dan **Ryan–Foster branching** (together/apart) adalah mesin standar untuk menugaskan elemen ke subset — cocok secara struktur dengan pemilihan bundle per header.
- OpenBP (github.com/miladbarooni/openbp): framework C++/Python branch-and-price, built on OpenCG + HiGHS, implementasi Ryan–Foster untuk set partitioning. **Angka benchmark-nya sendiri DIBANTAHKAN (0-3)** — pakai sebagai kode contoh, bukan data.
- 🚩 **Risk flag untuk masalah ini**: massive degeneracy pada master set-partitioning, ambang informal ± **10 elemen non-nol per kolom** — *tepat di batas 1–10 line per header*. Mitigasi: dynamic row aggregation (Elhallaoui dkk. 2003) memangkas waktu RMP **8×** pada instans 1,600 constraint.

---

## 4. Empiris: kapan backtracking runtuh

- Instans 30 transaksi: recursive backtracking mengenumerasi semua kombinasi-target dalam ~15 ms. Real workload pembayaran riil ~740 transaksi/hari (max ~6,000) = titik runtuh praktis backtracking tak-terprune.
- **Phase transition** subset-sum: probabilitas solusi ada melintas 50% empiris di n ≈ 18 (max range m = 100,000) atau m ≈ 334,000 (n = 20) — konsisten teori crossover m ≈ 2ⁿ (Mertens: κc(18)≈0.88, κc(20)≈0.89; empiris κ≈0.92). Instans **di dekat crossover = yang paling keras** untuk enumerasi; jauh di bawahnya solusi berlimpah.
  - Dataset Challenge 2 (13 line, harga $13–85 berhadapan dengan target) jauh di sisi kaya-solusi → wajar solver backtracking kita tidak pernah backtrack.
- Claim empiris "backtracking mengalahkan DP di semua instans" **TERBANTAHKAN (0-3)** — jangan diulang.

---

## Klaim yang DIBANTAHKAN oleh verifikasi adversarial (jangan disebarkan)

1. Color-coding (CardColorCodingLayer) menyelesaikan cardinality-constrained k-Subset Sum dalam Õ(n + t^k·c^k) — ditolak.
2. Solver adaptif subset-sum O\*(U·n²) diparameterisasi struktur — ditolak.
3. "Kompleksitas column generation = kompleksitas pricing subproblem-nya" (1-2) — terlalu kuat.
4. Angka benchmark OpenBP pada crew pairing (1013 flight, 40 s / 3 menit) — ditolak.
5. "Backtracking unggul atas DP di semua instans uji" — ditolak.

---

## Ladder praktis (rekomendasi sintesis)

1. **Skala kecil (dataset sekarang: 5 header, 13 line)** → enumerasi integer-cent + backtracking most-constrained-first. Selesai dalam mikrodetik. *(solve.py sudah melakukan ini)*
2. **Skala menengah (puluhan–ratusan line)** → CP-SAT kompak dengan table constraint per header, atau pruned enumeration (bounds: k·min ≤ target ≤ k·max + prefix-sum feasibility). Pertimbangkan meet-in-the-middle per header.
3. **Skala besar (banyak header, target nominal besar)** → column generation + branch-and-price; pricing = cardinality-constrained subset-sum per header. Siapkan mitigasi degeneracy (row aggregation, dual stabilization).

## Pertanyaan terbuka

1. Pricing terbaik empiris untuk bundle 1–10 line dengan target dalam sen: MITM per header, bounded-cardinality DP, atau CP-SAT submodel — dan bagaimana skalanya vs magnitudo target & duplikasi nilai?
2. Berapa sisa penalti simetri formulasi kompak di bawah symmetry handling modern (orbital fixing Gurobi/CPLEX, symmetry breaking CP-SAT)?
3. Apakah mitigasi degeneracy (row aggregation, dll.) tertransfer ke order matching, dan pada ukuran instans berapa degeneracy mulai dominan?
4. **Tidak ada benchmark publik untuk masalah order matching ini secara spesifik** — tiga arsitektur (ILP/CP-SAT kompak, enumerasi penuh + satu IP, branch-and-price) belum pernah dibandingkan di data nyata, apalagi dengan duplikasi jumlah yang menciptakan simetri solusi.

---

## Sumber utama

| # | Sumber | Kualitas |
|---|---|---|
| 1 | [Schroeppel & Shamir 1981 (SIAM)](https://epubs.siam.org/doi/10.1137/0210033) | Primary |
| 2 | [Nederlof & Węgrzycki, STOC 2021 (arXiv:2010.08576)](https://arxiv.org/abs/2010.08576) | Primary |
| 3 | [Bansal dkk., SICOMP 2018 (DOI 10.1137/17M1158203)](https://doi.org/10.1137/17m1158203) | Primary |
| 4 | [Antonopoulos dkk., JCO 2022 (arXiv:2112.04244)](https://link.springer.com/article/10.1007/s10878-022-00928-0) | Primary |
| 5 | [Barnhart dkk., OR 1998 (branch-and-price)](https://pubsonline.informs.org/doi/abs/10.1287/opre.46.3.316) | Primary |
| 6 | [Lübbecke & Desrosiers, OR 2005 (column generation survey)](https://optimization-online.org/wp-content/uploads/2002/12/580.pdf) | Primary |
| 7 | [OR-Tools: assignment groups / AllowedAssignments](https://developers.google.com/optimization/assignment/assignment_groups) | Primary (vendor) |
| 8 | [MICS 2013: phase transition subset-sum](https://micsymposium.org/mics_2013_Proceedings/submissions/mics20130_submission_13.pdf) | Primary (regional) |
| 9 | [CP-SAT primer (benchmarking & NRP)](https://d-krupke.github.io/cpsat-primer/benchmarking.html) | Secondary |
| 10 | [OpenBP (branch-and-price framework)](https://github.com/miladbarooni/openbp) | Primary (⚠️ 1-star repo, benchmark direbut) |
| 11 | [SSMP: subset-sum matching untuk rekonsiliasi (ECAI 2025, arXiv:2508.19218)](https://arxiv.org/abs/2508.19218v1) | Primary |
| 12 | [Austrin dkk., CCS 2013 (arXiv:1303.0609)](https://arxiv.org/abs/1303.0609) | Primary |

*Laporan penuh: 12 temuan terverifikasi, 5 refutasi, 22 sumber disaring dari 5 sudut pencarian (akademik/kompleksitas, solver modeling, column generation, benchmark empiris, domain praktisi).*