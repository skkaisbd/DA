# 14 — ANTI-UNDER-DELIVERY & EFFORT PROTOCOL
**CV. Dewi Aditya ERP** · Status: **TIER 0** (prioritas tertinggi perilaku agent)

> Diadopsi dari repo referensi (Rahaza-Travel doc 14). Latar: pain-point owner — agent AI
> sering **tidak memberi effort penuh**, mengerjakan setengah, lalu berdalih "konteks kurang".
> Ditegakkan mesin: `scripts/meta/effort_gate.py` (git-diff, 5 lensa) + `scripts/guardrails/
> verify_effort_quality.py` (statik, INV-QUALITY-01) + `scripts/gate.sh` → `memory/GATE_RECEIPT.md`.

---

## 1. ⛔ ANTI-EXCUSE CLAUSE
DALIL berikut **DILARANG** dipakai untuk berhenti / menurunkan kualitas:
- ❌ "Konteks/instruksi kurang" → kerjakan seadanya / berhenti.
- ❌ "Mungkin maksud user begini" → ambil yang termudah.
- ❌ "HTTP 200 / tak ada error" dianggap bukti selesai.

**WAJIB saat info terasa kurang:** (1) GALI dulu sumber yang ADA (docs/, codebase, grep, screenshot). Mayoritas "konteks kurang" = "belum dibaca". (2) Bila ada celah keputusan → tulis **ASSUMPTION LEDGER** lalu tetap maju. (3) STOP & ASK hanya untuk hal kritis tak-bisa-diasumsikan (kredensial, biaya, breaking-change, pilihan produk besar) dengan pertanyaan bernomor + opsi.

---

## 2. 📏 DEPTH STANDARD per jenis tugas
- **ANALISIS:** pembedahan per-bagian; ≥8 temuan konkret + implikasi; identifikasi kontradiksi/risiko/celah; kutip lokasi (path/baris/endpoint); rekomendasi actionable. (Bukan ringkasan 3 kalimat.)
- **BUILD:** Backend + Frontend + seed + states (loading/empty/error) + `data-testid`; tanpa orphan endpoint / ghost page; lolos gate.
- **DEBUG:** RCA sampai akar (petakan ke RC/INV) + kuatkan gate agar tak terulang; catat di `BUG_REGISTRY.md`.
- **DESIGN/UI:** ikuti design guidelines penuh; bukan UI datar asal jadi.

---

## 3. 🧾 ASSUMPTION LEDGER (template)
```
ASUMSI (agar tetap maju):
1. [asumsi] — alasan — risiko bila salah — mudah diubah? [ya/tidak]
YANG PERLU KONFIRMASI (kritis saja):
1. [pertanyaan bernomor + opsi a/b/c]
RENCANA: lanjut membangun X dgn asumsi di atas; bila (1) beda, dampak terbatas di [file/area].
```

---

## 4. ✅ EVIDENCE-BASED COMPLETION
"Selesai" sah bila SEMUA ada:
- `memory/GATE_RECEIPT.md` HIJAU (dari `bash scripts/gate.sh`, cakupan non-skip).
- `python scripts/meta/effort_gate.py --strict` HIJAU (Grade ≥ B).
- Nilai data benar + invarian lulus (bukan cuma 200).
- Screenshot preview URL benar (untuk UI).
- `testing_agent` dijalankan utk perubahan signifikan; bug high/medium difix.
- Laporan JUJUR: sebut yang MOCKED/limitasi (HURUF KAPITAL).

---

## 5. 🧮 SELF-AUDIT (sebelum klaim "selesai")
```
□ Sudah GALI semua sumber yang ADA sebelum bilang "kurang konteks"?
□ Kedalaman memenuhi DEPTH STANDARD (§2)?
□ Ada deliverable yang diam-diam dilewati?
□ gate.sh + effort_gate HIJAU (bukan asumsi)?
□ Menulis Assumption Ledger alih-alih berhenti?
□ Jujur soal yang belum beres / MOCKED?
```
Ada □ tak terpenuhi → JANGAN klaim selesai; perbaiki atau lapor jujur.

---

## 6. ESKALASI (bukan menyerah)
self-debug 2× → `troubleshoot_agent` → `testing_agent` → `web_search` → `integration_playbook_expert` → lapor jujur + opsi + bukti. DILARANG klaim selesai tanpa bukti; DILARANG menyerah diam-diam.
