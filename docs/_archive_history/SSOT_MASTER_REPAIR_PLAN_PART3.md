# 🔧 SSOT MASTER REPAIR PLAN — PART 3
## Domain Deep-Dive: MARKETING · RnD · WMS

> **Status:** RENCANA + BUKTI EMPIRIS TERVERIFIKASI. **BELUM ada perubahan kode** (dokumen forensik).
> **Melanjutkan:** `SSOT_MASTER_REPAIR_PLAN.md` (RC-01…RC-07) & `SSOT_MASTER_REPAIR_PLAN_PART2.md` (RC-08…RC-14).
> **Repair Card baru:** RC-15 … RC-18 (+ Dormant Registry + False-Positive Registry).
> **Metodologi:** identik dengan Part 1 & 2 — 5 dimensi bukti:
> **D1** data DB nyata · **D2** kode backend baris-per-baris · **D3** frontend consumer (siapa yang memanggil) · **D4** linkage/idempotensi · **D5** semantik (bug nyata vs dormant vs false-positive).
> **Tanggal forensik:** 2026-07-02 — fresh clone repo `DAterbaru` → seed komprehensif (`POST /api/seed/production-full` + `POST /api/rahaza/seed-demo`), data ter-anchor **Mei–Juli 2026**.

---

## BAGIAN 0 — KONTEKS, METODOLOGI & ATURAN KLASIFIKASI

### 0.1 Mengapa Marketing / RnD / WMS belum tercakup di Part 1 & 2?
Part 1 & 2 fokus pada **jalur uang & operasi inti**: Finance (GL/AR/AP/Cashflow), HR (absensi/payroll), Produksi (WO/QC/WIP/variances), dan Dashboard eksekutif. Marketing/RnD/WMS hanya **disinggung tangensial**:
- `marketing_live_sessions` — disebut di RC-02 & RC-07 (field mismatch `gmv`/`total_orders`), **tanpa** deep-dive endpoint.
- `rahaza_products → rahaza_models` — RC-11 (produksi), bukan RnD.
- Beberapa koleksi WMS (`wh_fg_movements`, `wms_picklist`, `wms_fg_labels`, `universal_scan`) — RC-12/RC-14 sebagai kategori "orphan/misc".

**Tidak ada** Repair Card yang menelusuri Marketing, RnD, dan WMS **sebagai domain utuh**. Part 3 menutup celah ini dengan level forensik yang sama.

### 0.2 State DB saat forensik (seed matrix — ringkas)
| Koleksi kunci | Count | Koleksi kunci | Count |
|---|---|---|---|
| users (RBAC) | 6 | marketing_live_sessions | 24 |
| rahaza_employees | 25 | marketing_creator_sessions | 45 |
| rahaza_work_orders | 25 | marketing_kol_creators | 5 |
| rahaza_wip_events | 525 | marketing_orders | 60 |
| rahaza_qc_events | 34 | dewi_toko_orders | 240 |
| dewi_rnd_styles | 6 | dewi_rnd_samples | 4 |
| dewi_rnd_sample_requests | **0** | wh_positions | 36 |
| wh_racks | 6 | wh_fabric_rolls | 12 |
| wh_delivery_notes | 8 | wh_cmt_dispatches | 5 |
| wms_opname2 sessions | 3 | rahaza_materials | 25 |

> **Catatan:** semua data ber-tanggal Mei–Juli 2026. Tanpa seed ini, **semua endpoint akan 0** dan forensik empiris (Appendix D-3) mustahil.

### 0.3 Login / Role matrix yang dipakai
| Email | Role | Portal utama |
|---|---|---|
| admin@garment.com | superadmin | semua |
| hr@dewiaditya.id | hr | SDM/HRIS |
| (…5 akun test dari seed) | finance/produksi/gudang/marketing/… | per-portal |

Semua endpoint di Appendix D-3 dipanggil sebagai **superadmin** (akses penuh) untuk memisahkan "kosong karena bug" dari "kosong karena RBAC".

### 0.4 Aturan Klasifikasi (WAJIB dibaca sebelum eksekusi)
Sesuai **Golden Rules** Part 1 ("lulus tes ≠ benar" + "jangan repoint tanpa SSOT pasti"), setiap temuan diberi **satu** label:

| Label | Definisi | Tindakan |
|---|---|---|
| 🔴 **REAL-BUG (MISROUTE)** | Kode membaca koleksi/fields yang salah, sedangkan **SSOT dengan data terbukti ada**. FE aktif mengonsumsi. | **Perbaiki** (repoint + verifikasi angka). |
| 🔴 **REAL-BUG (FIELD/TYPE)** | Koleksi benar, tapi nama field / tipe (string vs datetime) salah → 500 / all-zero. | **Perbaiki** field/tipe. |
| 🟠 **REAL-BUG (SEED↔SSOT)** | Seed menulis ke koleksi berbeda dari yang dibaca aplikasi. Data "ada" tapi tak tampil. | **Perbaiki seed** agar tulis ke SSOT app. |
| 🟡 **DORMANT / NO-SEED** | Modul FE+BE **self-consistent** (baca=tulis koleksi sama) tapi koleksi kosong karena belum di-seed / event runtime belum terjadi. Kosong = **jujur**. | **JANGAN repoint.** Opsional: seed demo. |
| ⚪ **FALSE-POSITIVE** | 401 (portal auth khusus), 422 (butuh query param), endpoint deprecated/di-`_archive`, atau tanpa consumer FE (dead code). | **JANGAN sentuh.** Dokumentasikan. |

> ⚠️ **Peringatan false-positive** (pelajaran RC-10 Part 1): mem-"perbaiki" item DORMANT/self-consistent dengan repoint ke koleksi lain justru **MERUSAK** siklus tulis→baca CRUD-nya. Contoh nyata di Part 3: `rahaza_styles` (Style Master 2.0) & `wh_unit_master` (unit conversions) — keduanya self-consistent & kosong, **bukan** bug.

---

## BAGIAN 1 — SSOT REGISTRY (Tambahan Domain Marketing/RnD/WMS)

### 1.A Marketing — Peta SSOT & Field
| Konsep | SSOT (koleksi) | Field kunci (schema NYATA di DB) | Catatan penting |
|---|---|---|---|
| Sesi Live Host | `marketing_live_sessions` | `gmv`, `total_orders`, `cr_rate`, `peak_viewers`, `session_date`(**string** "YYYY-MM-DD"), `host_name`, `platform`, `channel_key`, `duration_minutes`, `status` | **BUKAN** `revenue`/`orders`/`total_viewers`/`engagement_rate`/`conversion_rate`. |
| Sesi KOL/Creator | `marketing_creator_sessions` | `creator_id`, `creator_code`, `creator_name`, `revenue`, `viewers`, `orders`, `date`(**string**), `platform`, `account_id` | Skema **BERBEDA** dari live_sessions. |
| Master KOL | `marketing_kol_creators` | `id`, `creator_code`, `name`, `tier`, `followers`, `total_revenue_generated`, `campaigns_done`, `kpi_targets` | |
| Order marketplace | `marketing_orders` (60) & `dewi_toko_orders` (240) | — | Dua sumber; toko dashboard pakai `dewi_toko_orders`. |
| Target creator | `marketing_creator_targets` | self-consistent (baca=tulis) | **Kosong = dormant** (di-set user). |
| Katalog | `marketing_catalogs` | self-consistent | **Kosong = dormant.** |

### 1.B RnD — Peta SSOT & Field
| Konsep | SSOT (koleksi) | Reader/Writer file | Status data |
|---|---|---|---|
| Styles | `dewi_rnd_styles` (6) | `dewi_rnd_styles.py` (baca+tulis) | ✅ ada data |
| Sample **requests** | `dewi_rnd_sample_requests` (**0**) | `dewi_rnd_samples.py:26` (baca+tulis) | 🟠 seed salah koleksi (lihat RC-18) |
| Sample (seed) | `dewi_rnd_samples` (**4**) | ditulis oleh seed, **tidak dibaca** tab Samples | 🟠 mismatch |
| Materials | `dewi_rnd_materials` (0) | `dewi_rnd_materials.py` (baca+tulis) | 🟡 dormant |
| Patterns | `dewi_rnd_patterns` (0) | `dewi_rnd_design.py` (baca+tulis) | 🟡 dormant |
| Variants | `dewi_rnd_variants` (0) | `dewi_rnd_design.py` (baca+tulis) | 🟡 dormant |
| Tech-packs | `dewi_rnd_tech_packs` (0) | `dewi_rnd_hpp.py` (baca+tulis) | 🟡 dormant |
| HPP | `dewi_rnd_hpp` (0) | `dewi_rnd_hpp.py` (baca+tulis) | 🟡 dormant |
| Sample costing | `dewi_rnd_sample_costing` (0) | `dewi_rnd_materials.py` (baca+tulis) | 🟡 dormant |
| Revisions | `dewi_rnd_revisions` (0) | `dewi_rnd_samples.py` (baca+tulis) | 🟡 dormant |
| Style Master 2.0 | `rahaza_styles` (0) | `rahaza_styles.py` (baca+tulis) | ⚪ FE di `_archive` (dead) |

> **Kesimpulan RnD:** seluruh modul RnD **self-consistent** (baca koleksi yang sama dengan yang ditulis). Kosong = belum di-seed, **BUKAN** phantom — **KECUALI** RC-18 (sample requests) yang benar-benar mismatch seed↔app.

### 1.C WMS — Peta SSOT & Field
| Konsep | SSOT (koleksi) | Count | Status |
|---|---|---|---|
| Struktur gudang | `wh_buildings`(1) / `wh_zones`(3) / `wh_racks`(6) / `wh_positions`(36) | ✅ | Sehat. |
| Stok unified | `rahaza_material_stock` / `material_stock_canonical`(12) | ✅ | `/wms/stock/unified` = 29 rows. |
| Movements | `rahaza_material_movements`(22) | ✅ | Sehat. |
| Receiving/Putaway | `wh_grn`(8) / `wh_putaway`(5) | ✅ | Sehat. |
| Fabric rolls | `wh_fabric_rolls`(12) | ✅ | Sehat. |
| Delivery notes | `wh_delivery_notes`(8) | ✅ | Sehat. |
| CMT dispatch | `wh_cmt_dispatches`(5) | ✅ | Sehat. |
| **Opname (SSOT)** | `wms_opname2` sessions (3) | ✅ | **Canonical.** Endpoint lama (`/warehouse/opname`, `/wms/opname`, `/wms/legacy/opname`) = deprecated. |
| Kapasitas | membaca `production_work_orders` (**MISSING**) | ❌ | 🔴 **phantom** — SSOT = `rahaza_work_orders`(25). Lihat RC-17. |
| Unit master/konversi | `wh_unit_master` / `wh_unit_conversions` (MISSING) | — | 🟡 dormant (self-consistent). |
| Pending movements | `wh_pending_movements` (MISSING) | — | 🟡 runtime/event-driven (kosong=normal). |

---

## BAGIAN 2 — REPAIR CARDS (RC-15 … RC-18)

### 🔴 RC-15 — Marketing "Live Summary" CRASH 500 + Semua Angka Nol
- **Severity:** HIGH (error merah ke user + KPI nol total).
- **Endpoint:** `GET /api/marketing/live/summary`
- **Consumer FE (D3):** `components/erp/marketing/LiveSessionModule.jsx` (aktif di nav — bukan archive).
- **Bukti empiris (D1):** memanggil endpoint → **HTTP 500** `{"detail":"Internal server error"}`.
- **Root cause (D2):** `routes/marketing_live_sessions_routes.py`
  - baris 123 `"total_revenue": {"$sum": "$revenue"}` → field `revenue` **tidak ada** (SSOT: `gmv`) → hasil 0.
  - baris 124 `"$sum": "$orders"` → SSOT: `total_orders` → 0.
  - baris 125 `"$sum": "$total_viewers"` → SSOT: `peak_viewers` → 0.
  - baris 126 `"avg_engagement": {"$avg": "$engagement_rate"}` → field **tidak ada** → `$avg` = `None`.
  - baris 127 `"avg_conversion": {"$avg": "$conversion_rate"}` → SSOT: `cr_rate` → `None`.
  - baris **173** `round(stats["avg_engagement"], 2)` → `round(None,2)` → **`TypeError: type NoneType doesn't define __round__`** → 500.
- **SSOT truth (D1):** 24 sesi dengan `gmv` nyata (~8.2 juta/sesi), `total_orders`, `cr_rate`, `peak_viewers`.
- **Perbaikan:**
  1. Ganti pemetaan agregasi: `revenue→gmv`, `orders→total_orders`, `total_viewers→peak_viewers`, `avg_conversion←$avg:$cr_rate`. Hapus/rename `engagement_rate` (tidak ada di SSOT).
  2. Guard null: `round(stats.get("avg_conversion") or 0, 2)` untuk semua field numerik.
  3. Samakan `by_platform` & `top_hosts` (baris 142/150/159) ke `gmv`.
- **Definition of Done:** `/live/summary` → 200, `total_revenue` = Σ `gmv` (bandingkan dengan `db.marketing_live_sessions.aggregate([{$group:{_id:null,g:{$sum:"$gmv"}}}])`), `top_hosts[0].revenue` > 0, LiveSessionModule menampilkan angka nyata (bukan 0/blank).
- **Risiko/Rollback:** rendah — hanya rename field agregasi. Rollback = revert file tunggal.
- **Referensi silang:** menegaskan catatan field-mismatch di RC-02/RC-07 Part 1 (belum di-fix di jalur ini).

### 🔴 RC-16 — KOL Leaderboard Kosong (Salah Koleksi + Field + Tipe Tanggal)
- **Severity:** HIGH (leaderboard KOL tampil kosong padahal ada 5 creator & 45 sesi).
- **Endpoint:** `GET /api/marketing/kol-leaderboard/`
- **Consumer FE (D3):** `components/erp/marketing/KOLLeaderboardModule.jsx` (aktif).
- **Bukti empiris (D1):** 200 tapi `data: []` (kosong) — padahal `marketing_creator_sessions`=45, `marketing_kol_creators`=5.
- **Root cause (D2):** `routes/marketing_kol_leaderboard.py`
  - baris 113 `db.marketing_live_sessions.aggregate(...)` → **koleksi SALAH**. `marketing_live_sessions` = sesi **livehost** (skema `gmv`/`host_name`, **tanpa** `kol_id`).
  - baris 64 `"session_date": {"$gte": start_date, "$lte": end_date}` → membandingkan **datetime** terhadap field `session_date` bertipe **string** → **tidak match** → hasil kosong.
  - baris 69–73 group `$kol_id` + sum `$revenue`/`$viewers`/`$orders` → field-field ini milik `marketing_creator_sessions`, **bukan** `marketing_live_sessions`.
- **SSOT truth (D1):** `marketing_creator_sessions` PUNYA `creator_id`, `creator_name`, `revenue`, `viewers`, `orders`, `date`(string) — persis yang dibutuhkan. (Bandingkan: `/api/marketing/kol/leaderboard` di `marketing_kol_ops.py` **sudah benar** & mengembalikan data.)
- **Perbaikan:**
  1. Baris 113 → `db.marketing_creator_sessions.aggregate(...)`.
  2. Group `_id: "$creator_id"`, `kol_name: {"$first": "$creator_name"}`.
  3. Match `date` sebagai **string** range (`{"$gte": start_str, "$lte": end_str}` dengan `start_str = start_date.strftime("%Y-%m-%d")`), atau hilangkan filter tanggal jika seluruh periode.
- **Definition of Done:** `/kol-leaderboard/` → `data` berisi ≥1 baris; `overall_stats.total_revenue` = Σ `revenue` `marketing_creator_sessions`; KOLLeaderboardModule menampilkan ranking dengan angka.
- **Risiko/Rollback:** rendah (satu file). **Guard false-positive:** JANGAN hapus `marketing_kol_ops.py` `/kol/leaderboard` (dipakai `KOLCreatorModule.jsx`, sudah benar) — ini endpoint berbeda.

### 🔴 RC-17 — Capacity Planning Baca Koleksi Phantom `production_work_orders`
- **Severity:** MEDIUM (utilization & bottlenecks kosong; overview tetap tampil).
- **Endpoint:** `GET /api/capacity/utilization`, `GET /api/capacity/bottlenecks` (juga dipakai `/overview`).
- **Consumer FE (D3):** `components/erp/CapacityPlanningModule.jsx` (aktif).
- **Bukti empiris (D1):** `/capacity/utilization` & `/capacity/bottlenecks` → `data: []` (kosong). `/capacity/overview` → 200 (sebagian dari config default).
- **Root cause (D2):** `routes/wms_capacity_planning.py:62` `db.production_work_orders.aggregate(pipeline)` → koleksi `production_work_orders` **TIDAK ADA** (MISSING). SSOT WO = `rahaza_work_orders` (25 dokumen).
  - (Pola identik RC-11 Part 2 untuk `production_pos`/`production_work_orders` di jalur produksi — di sini muncul lagi di modul kapasitas.)
- **SSOT truth (D1):** `rahaza_work_orders` = 25 WO aktif Mei–Juli 2026.
- **Perbaikan:**
  1. Baris 62 → `db.rahaza_work_orders.aggregate(pipeline)`.
  2. Verifikasi nama field pipeline (`qty`, `status`, `line_id`/`machine`, tanggal) cocok dengan schema `rahaza_work_orders`; sesuaikan bila perlu (lakukan D1 pada satu dokumen `rahaza_work_orders` sebelum edit).
  3. `capacity_config` MISSING → biarkan default (bukan bug), atau seed profil kapasitas (opsional).
- **Definition of Done:** `/capacity/utilization` & `/bottlenecks` mengembalikan baris per line/mesin dengan angka >0; CapacityPlanningModule menampilkan grafik utilisasi.
- **Risiko/Rollback:** sedang — perlu cek kecocokan field WO (jangan asumsi). Rollback = revert baris 62 & mapping.

### 🟠 RC-18 — RnD Samples: Seed Menulis ke Koleksi Berbeda dari yang Dibaca App
- **Severity:** MEDIUM (tab "Sample Requests" kosong walau seed mengklaim membuat 4 sample).
- **Endpoint terdampak:** `GET /api/dewi/rnd/sample-requests` (+ turunannya).
- **Consumer FE (D3):** `components/erp/RnDSamplesTab.jsx`, `RnDCostingTab.jsx` (aktif).
- **Bukti empiris (D1):**
  - `db.dewi_rnd_samples` = **4** (ditulis oleh seed).
  - `db.dewi_rnd_sample_requests` = **0** (yang dibaca app).
  - `/api/dewi/rnd/sample-requests` → `[]`.
- **Root cause (D2):**
  - App (SSOT sebenarnya): `routes/dewi_rnd_samples.py:26` baca `db.dewi_rnd_sample_requests` (dan tulis di baris 64) → **self-consistent** pada `dewi_rnd_sample_requests`.
  - Seed menulis ke koleksi **`dewi_rnd_samples`** (nama beda) → data tidak pernah terbaca tab.
- **SSOT truth:** SSOT aplikasi = `dewi_rnd_sample_requests` (dipakai CRUD nyata + dashboard). `dewi_rnd_samples` = artefak seed yatim.
- **Perbaikan (pilih satu; rekomendasi A):**
  - **A (fix seed):** ubah seeder agar menulis sample ke `dewi_rnd_sample_requests` (skema sesuai `dewi_rnd_samples.py`), dan hapus penulisan ke `dewi_rnd_samples`.
  - **B (jangan):** repoint app baca `dewi_rnd_samples` → **DITOLAK** (akan memutus siklus tulis CRUD tab yang pakai `dewi_rnd_sample_requests`).
- **Definition of Done:** setelah re-seed, `/api/dewi/rnd/sample-requests` mengembalikan ≥1 item; RnDSamplesTab menampilkan sample; dashboard `recent_samples` konsisten dengan tab.
- **Risiko/Rollback:** rendah (perubahan di seeder saja). Ini bertipe **[+SEED]** (perbaikan data-generator, bukan runtime app).

---

## BAGIAN 3 — DORMANT REGISTRY (Fitur Jujur-Kosong — JANGAN Repoint)

Modul-modul berikut **self-consistent** (baca=tulis koleksi sama) & kosong **karena belum di-seed / menunggu event runtime**. Ini **BUKAN bug**; mem-"perbaiki" dengan repoint akan merusak. Opsi legit: buat seed demo bila ingin data contoh.

### RnD (semua self-consistent, kosong)
| Endpoint | Koleksi | Kenapa kosong |
|---|---|---|
| `/api/dewi/rnd/materials` | `dewi_rnd_materials` | belum di-seed |
| `/api/dewi/rnd/patterns` | `dewi_rnd_patterns` | belum di-seed |
| `/api/dewi/rnd/variants` | `dewi_rnd_variants` | belum di-seed |
| `/api/dewi/rnd/tech-packs` | `dewi_rnd_tech_packs` | belum di-seed |
| `/api/dewi/rnd/hpp-calculator` | `dewi_rnd_hpp` | belum di-seed |
| `/api/dewi/rnd/sample-costing` | `dewi_rnd_sample_costing` | belum di-seed |
| `/api/dewi/rnd/revisions` | `dewi_rnd_revisions` | dibuat saat revisi sample |
| `/api/rahaza/boms`, `/api/rahaza/hpp/snapshots*` | `rahaza_boms`, `rahaza_hpp_snapshots` | belum di-seed |

### Marketing (dormant/no-seed & runtime)
| Endpoint | Koleksi | Kenapa kosong |
|---|---|---|
| `/api/marketing/targets/creator` | `marketing_creator_targets` | di-set user (self-consistent) |
| `/api/marketing/catalogs/fg-products`, `/kol/catalog`, `/kol/fg-products` | `marketing_catalogs` | katalog belum diisi |
| `/api/marketing/import/*`, `/import-templates` | koleksi import | tidak ada job import |
| `/api/marketing/ai-content/history`, `/livehost/scripts`, `/livehost/training*` | konten AI/skrip | belum digenerate |
| `/api/marketing/task-templates`, `/tasks-stats` | template/tasks | belum diisi |
| `/api/marketing/webhooks/events`, `/webhooks/stats` | events | belum ada webhook masuk |
| `/api/dewi/toko/flashsales`, `/toko/pack-batches` | flashsale/pack | belum ada campaign |

### WMS (dormant/no-seed & runtime/event-driven)
| Endpoint | Koleksi | Kenapa kosong |
|---|---|---|
| `/api/wms/units`, `/unit-conversions`, `/units/all-codes` | `wh_unit_master`, `wh_unit_conversions` | belum di-seed (self-consistent) |
| `/api/wms/pending`, `/pending/summary` | `wh_pending_movements` | **event-driven** — dibuat saat WO selesai / shipment; belum ada handoff |
| `/api/wms/rack-alerts`, `/warehouse/alerts` | alerts | dihitung runtime; tak ada alert = normal |
| `/api/wms/audit/adjustments*`, `/stock/unified/adjustments` | audit adjustments | belum ada penyesuaian stok |
| `/api/acc/opname` | opname aksesoris | belum ada sesi |

---

## BAGIAN 4 — FALSE-POSITIVE REGISTRY (JANGAN Sentuh)

| Item | Kategori | Alasan |
|---|---|---|
| `/api/marketing/creator-portal/*` (401) | Auth-scoped | Butuh JWT **creator** (bukan token admin). Perilaku benar. |
| `/api/marketing/livehost/portal/*` (401) | Auth-scoped | Butuh JWT **livehost**. Perilaku benar. |
| `/api/marketing/dashboard/comparison`, `/livehost/payment/status`, `/livehost/shifts/calendar` (422) | Validasi param | Wajib query param → 422 tanpa param = benar. |
| `/api/rahaza/boms/versions` (422) | Validasi param | Butuh `bom_id`/`version`. |
| `/api/rahaza/styles` (Style Master 2.0) | Dead/archived | Consumer hanya `erp/_archive/StyleMasterModule.jsx`. Self-consistent & kosong. **JANGAN repoint** ke `rahaza_models`/`dewi_rnd_styles`. |
| `/api/warehouse/opname`, `/api/wms/opname`, `/api/wms/legacy/opname` | Deprecated | Digantikan **opname2** (`/api/wms/opname2` = 3 sesi, SSOT). FE utama pakai opname2. |
| `/api/marketing/live/analytics/product-performance`, `/returns/credit-notes`, `/product-variants` | Dead/backend-only | Tidak ada consumer FE aktif. |

> ⚠️ **Aksi teknis untuk item deprecated:** boleh **hapus/redirect** endpoint opname lama & modul `_archive` **secara terpisah** (housekeeping), TAPI itu **bukan** bagian dari repair SSOT dan **tidak** boleh mengubah `opname2`.

---

## BAGIAN 5 — INTEGRASI ROADMAP (dengan Wave Part 1 & 2)

Menambahkan **Wave I** (khusus 3 domain) ke roadmap eksekusi utama:

| Wave | Isi | Risiko | Prasyarat data |
|---|---|---|---|
| **W-I.1** | RC-15 (Live Summary field) + RC-16 (KOL Leaderboard koleksi/field/tipe) | Rendah | `marketing_live_sessions`, `marketing_creator_sessions` (sudah ada) |
| **W-I.2** | RC-17 (Capacity → `rahaza_work_orders`) | Sedang (cek field WO) | `rahaza_work_orders` (25) |
| **W-I.3** | RC-18 (seed RnD sample requests) [+SEED] | Rendah | re-run seeder |
| **W-I.4** (opsional) | Seed demo untuk fitur DORMANT (RnD materials/patterns/HPP, marketing katalog, WMS units) bila ingin data contoh | Rendah | — |

**Urutan disarankan:** W-I.1 (dampak visual tertinggi, risiko terendah) → W-I.2 → W-I.3. Semua **independen** dari Wave A–H Part 1/2 (tidak ada tumpang tindih file), sehingga bisa dieksekusi paralel/kapan saja.

**Definition of Done tiap Wave (WAJIB, sesuai Golden Rules):**
1. Endpoint 200 **dan** angka nyata > 0 (dibandingkan langsung dengan agregasi DB).
2. Consumer FE menampilkan data (screenshot/testing_agent), bukan sekadar "200 OK".
3. Re-run scanner `migrations/ssot_scanner_part3.py` → flag hilang untuk item ybs.
4. Tidak ada regresi pada endpoint yang sudah sehat (Appendix D-3).

---

## APPENDIX D-3 — BUKTI EMPIRIS (Endpoint Test Matrix, 2026-07-02)

Semua GET (tanpa path-param) dipanggil sebagai superadmin. Legenda: ✅ 200+data · ⚠️ 200 tapi kosong/all-zero · ❌ 500 · 🔒 401 (auth-scoped) · ⛔ 422 (butuh param).

### Marketing — 110 endpoint diuji (36 "problem")
- ❌ `GET /api/marketing/live/summary` → **500** (RC-15).
- ⚠️ `GET /api/marketing/kol-leaderboard/` → `data[0]` (RC-16).
- ✅ `GET /api/marketing/kol/leaderboard` → berisi data (endpoint pembanding yang BENAR).
- ✅ `GET /api/marketing/live/sessions` → data · `GET /api/marketing/livehost` → 4 · `GET /api/marketing/kol/creators` → 5 · `GET /api/marketing/kol/sessions` → 45 · `GET /api/marketing/accounts` → 5 · `GET /api/marketing/dashboard/overview` → data · `GET /api/marketing/live/analytics/*` → data (2/8/10 baris).
- 🔒 `creator-portal/*` (5), `livehost/portal/*` (6) → 401 (auth-scoped, benar).
- ⛔ `dashboard/comparison`, `livehost/payment/status`, `livehost/shifts/calendar` → 422 (butuh param).
- 🟡 dormant (kosong, self-consistent): `import/*`, `ai-content/history`, `livehost/scripts`, `livehost/training*`, `targets/creator`, `task-templates`, `tasks-stats`, `webhooks/*`, `catalogs/fg-products`, `kol/catalog`, `kol/fg-products`, `toko/flashsales`, `toko/pack-batches`, `returns/credit-notes`.

### RnD — 23 endpoint diuji (18 "problem")
- ✅ `GET /api/dewi/rnd/styles` → 6 · `GET /api/dewi/rnd/dashboard` → data · `GET /api/dewi/rnd/analytics` → data · `GET /api/dewi/maklon/samples` → 6.
- 🟠 `GET /api/dewi/rnd/sample-requests` → `[]` (RC-18 — data ada di `dewi_rnd_samples`=4).
- 🟡 dormant (self-consistent, no-seed): `materials`, `patterns`, `variants`, `tech-packs`, `hpp-calculator`, `sample-costing`, `revisions`, `styles/pending-review`, `rahaza/boms`, `rahaza/hpp/snapshots*`, `rahaza/costing-settings`.
- ⚪ `GET /api/rahaza/styles` → `[]` (Style Master 2.0 — FE archived; false-positive).
- ⛔ `rahaza/boms/versions` → 422 (butuh param). ⚪ `product-variants` → dead.

### WMS — 56 endpoint diuji (16 "problem") — **domain paling sehat**
- ✅ Sehat: `warehouse/dashboard`, `warehouse/locations`(8), `warehouse/movements`(6), `warehouse/putaway`(5), `warehouse/receiving`(12), `warehouse/stock`(14), `warehouse/smart-reorder`(25), `wms/buildings`(1), `wms/racks`(6), `wms/positions`(36), `wms/zones`(3), `wms/fabric-rolls`(12), `wms/delivery-notes`(8), `wms/cmt-dispatches`(5), `wms/opname2`(3), `wms/stock/unified`(29), `wh/returns`(6).
- ⚠️ `capacity/utilization`, `capacity/bottlenecks` → kosong (RC-17).
- 🟡 dormant/runtime: `wms/units`, `wms/unit-conversions`, `wms/units/all-codes`, `wms/pending`, `wms/pending/summary`, `wms/rack-alerts`, `warehouse/alerts`, `wms/audit/adjustments*`, `wms/stock/unified/adjustments`, `acc/opname`.
- ⚪ deprecated: `warehouse/opname`, `wms/opname`, `wms/legacy/opname` (→ opname2 SSOT).

---

## APPENDIX — PERINTAH VERIFIKASI (Read-Only, Ulangi Kapan Saja)

```bash
# 1) Scanner phantom per-domain (non-destruktif, output /tmp/ssot_part3_raw.json)
cd /app/backend && python3 migrations/ssot_scanner_part3.py

# 2) Test matrix empiris seluruh GET endpoint 3 domain
#    (butuh token admin di /tmp/admin_token.txt)
cd /app/backend && python3 migrations/test_domain_endpoints.py

# 3) Cross-check angka SSOT (contoh RC-15)
python3 - <<'PY'
from dotenv import load_dotenv; load_dotenv('/app/backend/.env')
import os; from pymongo import MongoClient
db=MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
print("Σ gmv live_sessions:", list(db.marketing_live_sessions.aggregate([{"$group":{"_id":None,"g":{"$sum":"$gmv"}}}])))
print("creator_sessions:", db.marketing_creator_sessions.count_documents({}))
print("rahaza_work_orders:", db.rahaza_work_orders.count_documents({}))
print("dewi_rnd_samples vs sample_requests:",
      db.dewi_rnd_samples.count_documents({}), db.dewi_rnd_sample_requests.count_documents({}))
PY
```

---

### RINGKASAN EKSEKUTIF PART 3
- **4 REAL-BUG** untuk diperbaiki: **RC-15** (Live Summary 500 — HIGH), **RC-16** (KOL Leaderboard kosong — HIGH), **RC-17** (Capacity phantom WO — MED), **RC-18** (seed RnD sample mismatch — MED).
- **Marketing** = paling banyak field/koleksi-mismatch nyata (2 HIGH). **WMS** = paling sehat (hasil konsolidasi SSOT sebelumnya). **RnD** = mayoritas **dormant** (fitur jujur-kosong), hanya 1 mismatch seed.
- **Kritis:** mayoritas endpoint "kosong" adalah **DORMANT / FALSE-POSITIVE**, bukan bug. Repoint membabi buta akan **merusak** modul self-consistent (spt Style Master 2.0, WMS Units) — persis peringatan Golden Rules Part 1.

> **Tools forensik baru** (dibuat untuk Part 3, read-only): `migrations/ssot_scanner_part3.py`, `migrations/test_domain_endpoints.py`, `migrations/extract_domain_endpoints.py`.
>
> *Dokumen ini adalah RENCANA + BUKTI. BELUM ada perubahan kode runtime. Eksekusi perbaikan menunggu persetujuan (lihat BAGIAN 5).*
