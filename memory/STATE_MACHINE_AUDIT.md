# 🔀 STATE-MACHINE ADVERSARIAL SWEEP — Discovery Report (READ-ONLY on real data)

> Mode: **DISCOVERY** (tanpa perbaikan). Metode: fire endpoint transisi ke **ID hantu** (non-exist) → entitas nyata tak tersentuh. Ghost-keyed write dilacak & dipurge.

> Endpoint transisi total: **166** · dgn `{param}` (diprobe): **163** · tanpa param (di-skip demi keamanan): **3** · Login admin: OK

> Ghost-keyed writes ter-purge: **0** · **Residual data bisnis = 0 (PRISTINE)**. Catatan: koleksi `rate_limit_buckets` bertambah 163 = record infra rate-limiter (dibuat oleh SETIAP request, ber-TTL auto-expire) — **bukan** artefak bisnis; dikecualikan dari residual.


---


## 🔴 TEMUAN A — CRASH 500 saat transisi entitas tak-ada — **0**

> Semestinya 404/400. 500 = handler tak menangani entitas hilang / body → berpotensi bug guard.

✅ Tidak ada crash 500.


## 🔴 TEMUAN B — 2xx pada entitas TAK-ADA (guard 404 hilang) — **2**

> Kedua endpoint memanggil `update_one({id}, {$set:...})` **tanpa** `find_one`/cek `matched_count` & tanpa `upsert` → untuk id tak-ada: match 0 dokumen, **tak ada phantom-write** (diverifikasi: 0 dokumen hantu di DB), tetapi tetap balas **200 palsu** (semestinya 404). **Inkonsisten** dgn handler sibling di file yang sama (mis. reject/lain-nya sudah `find_one`→`raise 404`). Severity: **rendah** (menyesatkan, bukan korupsi data).

| Method | Path | HTTP | File | Akar |
|---|---|---:|---|---|
| POST | `/api/dewi/rnd/patterns/{pattern_id}/approve` | 200 | `dewi_rnd_design.py:195` | `update_one` tanpa guard not-found |
| POST | `/api/dewi/rnd/tech-packs/{tp_id}/approve` | 200 | `dewi_rnd_hpp.py:208` | `update_one` tanpa guard not-found |

**Rekomendasi (nanti, saat fix):** tambahkan `find_one` → `raise HTTPException(404)` (atau cek `result.matched_count == 0`) sebelum balas sukses — samakan dgn pola sibling.


## 🟢 AMAN (guard 4xx: 404/400/403/422/409) — **161** dari 163 endpoint ber-param



## ⚠️ TIDAK DIPROBE — transisi tanpa `{param}` (di-skip demi keamanan) — **3**

> Menembak ini bisa mengubah data NYATA (tak ada id hantu untuk disuntik). Perlu uji terarah dgn seed synthetic + cleanup.

| Method | Path | File |
|---|---|---|
| POST | `/api/acc/stock/receive` | dewi_accessories_full_backup.py |
| POST | `/api/marketing/livehost/training/assign` | marketing_livehost_training.py |
| POST | `/stock/receive` | dewi_accessories_stock.py |


## Batasan metodologi

- Sweep ini menguji **guard entitas-hilang** (universal & aman), BUKAN transisi antar-state valid (mis. double-approve, cancel-after-complete). Yang terakhir butuh seed synthetic per-entitas + cleanup (seperti R8/R9) dan schema-aware — direkomendasikan sebagai audit terarah untuk endpoint kritis.
- Semua write ber-ghost-id sudah dipurge; snapshot before/after membuktikan 0 residual.
