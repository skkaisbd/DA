# 🔬 DEEP ANALYSIS PLAYBOOK
**CV. Dewi Aditya ERP** — memaksa analisis MENDALAM (bukan permukaan).

> Diadopsi dari repo referensi (Rahaza-Travel). Dipakai sebelum merombak fitur besar / analisis
> referensi / keputusan trade-off. Mnemonik 6 tahap: **B-T-K-S-R-A**.

---

## A. 10 PRINSIP KEDALAMAN (non-negotiable)
1. Bukti dulu, opini belakangan (baca kode/dokumen/data NYATA + KUTIP lokasi).
2. Telusuri sumber primer (codebase, skema DB, URL, log) — bukan ingatan.
3. Telusuri batasan sebelum solusi (apa yang TIDAK boleh rusak? guardrail? kontrak API?).
4. Traceability: tiap poin kebutuhan → solusi konkret → fase → file.
5. Spesifik, bukan normatif (sebut file/komponen/endpoint).
6. Sintesis komparatif (ekstrak pola referensi → strategi spesifik).
7. Manfaatkan aset existing (jangan bangun ulang).
8. Kuantifikasi & benchmark (angka/target, bukan kata sifat).
9. Keputusan ber-trade-off (alasan + alternatif ditolak).
10. Artefak + checkpoint (dokumen review + KONFIRMASI sebelum eksekusi).

---

## B. PIPELINE 6 TAHAP
0. **Intent & Batasan** — baca permintaan mentah tanpa parafrase; tandai tujuan/kata-kunci eksplisit/ambiguitas.
1. **Bukti** — eksplor codebase/dokumen/URL; ringkas "yang SUDAH ADA & cara kerjanya" + kutip lokasi.
2. **Traceability Matrix** — pecah jadi poin atomik; tiap poin → kondisi kini → akar → solusi (file) → fase. (Tak boleh ada poin terlewat.)
3. **Kendala & Arsitektur** — guardrail/kontrak/yang-tak-boleh-rusak + strategi kepatuhan.
4. **Sintesis & Keputusan** — decision log (opsi+alasan+alternatif ditolak); benchmark; NOW vs LATER.
5. **Rencana Berfase + Risiko** — fase (tujuan/file/testing/maps ke poin) + tabel risiko/mitigasi.
6. **Artefak + Checkpoint** — tulis artefak (plan.md, blueprint) + pertanyaan berpilihan (a/b/c). Tunggu GO.

---

## C. DEFINITION OF DONE — RUBRIK (lulus ≥ 85/100)
| Kriteria | Bobot |
|---|---:|
| Berbasis bukti (kutip sumber primer) | 20 |
| Traceability point-by-point | 20 |
| Sadar kendala/guardrail | 15 |
| Spesifik & dapat dieksekusi | 15 |
| Trade-off & alternatif | 10 |
| Kuantifikasi/benchmark | 5 |
| Leverage aset existing | 5 |
| NOW vs LATER beralasan | 5 |
| Artefak + checkpoint | 5 |

---

## D. ANTI-PATTERN → PENANGKAL
| Dangkal | Penangkal |
|---|---|
| "Buat UI modern" (normatif) | Sebut pola+komponen+file |
| Menebak isi kode | Baca sumber primer + kutip |
| Lewatkan poin permintaan | Traceability Matrix lengkap |
| Abaikan yang bisa rusak | Tahap 3 kendala wajib |
| Langsung koding | Artefak + checkpoint dulu |
| Berhenti di permukaan saat diminta "lebih dalam" | Tambah riset/benchmark/tie-in; perinci tiap poin |

> One-liner penegas bila tetap dangkal: *"Untuk SETIAP klaim: bukti (path/endpoint) + solusi spesifik (file) + trade-off + angka. Hapus kalimat normatif tanpa bukti. Lengkapi Traceability sampai tak ada poin terlewat."*
