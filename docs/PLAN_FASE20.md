# FASE 20 — KONTRAK FE↔BE: 404 SENYAP & GUARD YANG MENUTUPINYA

> **Sesi lanjutan** (environment di-clone dari repo `gananmakajana/da`, MongoDB kosong total).
> Pemicu: sesi sebelumnya berhenti tepat saat menelusuri *"the 7 genuinely broken FE calls"*
> dari temuan advisory `fe_be_contract`.
> Pilihan user: **"Hanya tuntaskan 9 temuan fe_be_contract HIGH (perbaiki 404 senyap FE↔BE)
> lalu jalankan gate penuh"**, dan **"ya"** untuk membuat endpoint backend baru bila
> fiturnya memang sudah ada di UI.

---

## 0. VERIFIKASI DULU (sebelum menyentuh kode)

| Yang diklaim dokumen serah-terima | Hasil verifikasi nyata |
|---|---|
| `bootstrap.sh` menghasilkan environment siap-pakai | **TERBUKTI** — 58 detik, health OK, 6 login HTTP 200 |
| Baseline valuasi aksesoris **Rp 9.663.750** | **TERBUKTI** (reproducible dari seeder) |
| `dewi_assets.py` punya sintaks rusak (dari log sesi lalu) | **KELIRU** — `py_compile` bersih; itu artefak render alat `view_file` |
| `fe_be_contract` **HIGH 9** | **KELIRU (label usang)** — versi sekarang melaporkan **92 WARN, 0 HIGH**. Angka "9" adalah jumlah temuan NYATA setelah triase, bukan severity |
| Temuan `fe_be_contract` = "tech-debt advisory" | **KELIRU & BERBAHAYA** — di dalamnya ada **8 bug produk nyata** (fitur mati) |

**Catatan:** semua angka di dokumen ini dihasilkan ulang di container baru, bukan dikutip.

---

## 1. TRIASE: 92 WARN → 8 BUG NYATA

CHECK B (`verify_fe_be_contract.py`) sengaja WARN karena beberapa kelas temuan bercampur.
Alat triase baru **`scripts/triage_fe_dead_calls.py`** memisahkannya dengan **bukti**,
bukan tebakan:

| Bucket | Arti | Jumlah (awal) | Jumlah (akhir) |
|---|---|---|---|
| `ARCHIVE` | file di `components/erp/_archive/` — tidak dirender user | 67 | 96 |
| `DEADCODE` | komponen sudah dinonaktifkan di `moduleRegistry.js` | 16 | **0** |
| `ARTIFACT` | shape rusak karena template literal JS ikut ter-parse | 11 | 7 |
| `BASE_PREFIX` | konstanta `const BASE = ...`, bukan endpoint | — | 1 |
| `DYNAMIC` | FE menyisipkan variabel di posisi yang BE minta literal | 47 | 46 |
| **`REAL_404`** | **endpoint memang tidak ada — bug nyata** | **11** | **0** |

Setiap bucket sisa **dibuktikan** benign, bukan diasumsikan:
`ARTIFACT` → path literalnya dicocokkan ke OpenAPI dengan pemotongan **per karakter**
(bukan per segmen — kalau per segmen, `/api/wms/audit/adjustments/stats${qStr` hanya
membuktikan `/adjustments` ada, padahal yang perlu dibuktikan justru `/stats`).

---

## 2. DELAPAN BUG NYATA (dan mengapa masing-masing lolos)

| # | Panggilan FE | Diagnosis | Perbaikan |
|---|---|---|---|
| 1 | `/api/rahaza/master/employees` **(4 titik)** | Endpoint tak pernah ada. **Dan** endpoint benar membalas `{items:[…]}` sedangkan FE membaca `.rows`/`.employees` ⇒ memperbaiki URL saja **tetap** menghasilkan dropdown kosong | → `/api/rahaza/employees` + baca `.items` |
| 2 | `/api/finance/coa` | Tak pernah ada; SSOT COA di router lain, balasannya **array polos** sedangkan FE membaca `.items` | → `/api/rahaza/coa/accounts` + parse array |
| 3 | `/api/finance/petty-cash` | **FALSE POSITIVE** — itu `const BASE`, bukan panggilan | guard: klasifikasi `FE_BASE_PREFIX` (INFO) |
| 4 | `/api/rahaza/overtime-requests` **(GET + POST)** | Tak pernah ada. GET dibungkus `.catch(...)` ⇒ 404 **tertelan total**; POST membuat setiap pengajuan lembur karyawan gagal | → `/api/rahaza/overtime` + baca `.overtime` |
| 5 | `/api/rahaza/orders/{id}/generate-work-orders` | Engine `rahaza_work_orders` **sengaja dipensiunkan FASE 4 (E10 DELETE)**: semua penulisnya di `_archive/`, index dihapus, 0 dokumen, dan `dewi_maklon_pos.py:568` menegaskan *"TIDAK insert WO lagi"* | **tombol dihapus** (bukan endpoint dibuat) — jalur pengguna sudah ada via `OnwardCTA → prod-work-orders` |
| 6 | `/api/rahaza/payroll-runs/{id}/export` | **Implementasinya ADA tapi jadi KODE MATI** di dalam `export_run_excel()` setelah `return`-nya ⇒ dekorator hilang ⇒ route tak terdaftar. Ditambah `window.open` tak bisa mengirim header Authorization | endpoint `export_run_csv` diekstrak + FE pakai `downloadWithAuth` |
| 7 | `/api/rahaza/payroll-runs/{id}/payslips/{sid}/adjust` | Endpoint tak pernah ada; `manual_deduction`/`adjustment_notes` **nol kemunculan** di seluruh `backend/`. FE juga tak memeriksa `res.ok` ⇒ tampak "berhasil" | endpoint dibuat + FE menampilkan error + input catatan diaktifkan |
| 8 | `/api/collab/link-preview` | Router pencarian universal berprefix `/api/collab/search` | → `/api/collab/search/link-preview` |
| 9 | `/api/comm/ws` | **FALSE POSITIVE** — WebSocket tak pernah ada di OpenAPI | guard: panen route WebSocket dari sumber |
| 10 | `/api/dewi/assets/by-code/{code}` | Tak ada **dan salah domain**: pemanggilnya (`AssetManagementPortal.onScanned`) membaca `asset.asset_number` & `asset.location` ⇒ domain **aset tetap**, bukan aset karyawan (`da_assets`, berkunci `asset_code`) | → `/api/assets/scan-by-number/{n}` (sudah ada, memang dibuat "untuk scanner apps") |

### Kenapa #1/#2/#4 penting: "200 OK tapi tabel kosong"
Tiga temuan ini **tidak cukup** diperbaiki di URL-nya. Bentuk balasan backend berbeda dari
yang dibaca FE, jadi setelah URL benar pun daftarnya tetap kosong — persis kelas RC-1/RC-3
yang jadi alasan gate ini dibuat. Setiap perbaikan di sini menyentuh **URL *dan* kunci
balasan**.

### #7 — kebenaran UANG, bukan cuma endpoint
`post_payroll_run()` menyusun jurnal GL dari **HEADER run** (`total_gross`/`total_deductions`/
`total_net`), **bukan** dari payslip. Karena itu:
- Penyesuaian manual disimpan **terpisah** (`manual_deduction`) dari array `deductions`,
  supaya potongan sistem (BPJS/PPh21/kasbon) tidak pernah tertimpa — dan sebaliknya.
- SSOT tunggal `_payslip_totals()` + `_recompute_run_totals()` di `rahaza_payroll_shared.py`.
- **Bug lama yang ikut ditutup:** `PUT /payslips/{pid}` yang sudah ada mengubah angka slip
  **tanpa** menyinkronkan header run ⇒ jurnal yang diposting saat finalize NYATA-NYATA salah.
- Dijaga: identitas `bruto − potongan = neto` diuji langsung di sentinel.

---

## 3. EMPAT BLINDSPOT DI GATE-NYA SENDIRI

Yang paling berbahaya bukan bug produknya, tapi bahwa **gate-nya menyembunyikan sebagian**.

### G-A · `_seg_match()` SIMETRIS ⇒ 404 tak pernah dilaporkan
```python
if a == "{}" or b == "{}" or "{}" in a or "{}" in b:   # ← SALAH
    continue
```
`{}` di sisi **FE** adalah nilai yang **disisipkan saat runtime**; ia tak mungkin sama
dengan segmen **literal** backend. Akibatnya FE `/api/dewi/assets/by-code/{}` dianggap
"cocok" dengan BE `/api/dewi/assets/{}/assign` — fitur **scan QR aset mati diam-diam dan
tak pernah masuk laporan**. Setelah dibuat asimetris: **92 → 140 temuan** (48 di antaranya
tak pernah terlihat sebelumnya).

### G-B · Route WebSocket tak ada di OpenAPI
Spesifikasi OpenAPI 3 tak punya representasi WebSocket, tapi CHECK B memakai OpenAPI
sebagai daftar autoritatif ⇒ `/api/comm/ws` (yang **jelas ada**, terbukti HTTP 401 bukan
404) selalu dilaporkan mati. **False positive permanen adalah cara tercepat sebuah gate
jadi diabaikan.** Sekarang route WebSocket dipanen dari sumber, termasuk saat routernya
diimpor dari modul lain (`from ._helpers import router`).

### G-C · Konstanta BASE dihitung sebagai panggilan
`const BASE = \`${API}/api/finance/petty-cash\`` lalu dipakai `${BASE}/funds`. Template
`${BASE}/funds` tidak memuat `/api/` sehingga tak pernah terlihat; yang terlihat justru
konstantanya. Sekarang → `FE_BASE_PREFIX` (INFO).

### G-D · `fe_calls()` membaca KOMENTAR
Ditemukan **karena sesi ini sendiri terkena**: menulis komentar penjelas
`// dulu \`/api/x\` sekarang \`/api/y\`` membuat gate melaporkan path yang **justru sudah
diperbaiki**. Guard yang menghukum tindakan mendokumentasikan perbaikan akan mendorong
orang berhenti berkomentar. Sekarang komentar dinetralkan lebih dulu (jumlah baris
dipertahankan agar nomor baris laporan tetap akurat), dan `//` di dalam string (mis.
`https://`) tidak ikut terpotong.

---

## 4. KELAS BUG BARU: `INV-DEADCODE-01` — "handler tergabung"

`scripts/guardrails/verify_unreachable_code.py` (**BLOCKING**, statik, 4176 fungsi diperiksa).

```python
@router.get("/payroll-runs/{run_id}/export-excel")
async def export_run_excel(run_id, request):
    ...
    return StreamingResponse(buf, media_type="...spreadsheetml.sheet", ...)
    await require_auth(request)          # ← 31 baris berikutnya TAK TERJANGKAU:
    ...                                  #   handler CSV LENGKAP, dekoratornya HILANG
    return StreamingResponse(..., media_type="text/csv", ...)
```

Kenapa lolos semua gate yang sudah ada:
- **CHECK D** (orphan handler) mencari `def` **tanpa dekorator** → di sini tidak ada `def`
  baru sama sekali, jadi tak ada yang bisa dilihat.
- **CHECK B** hanya bisa bilang *"FE memanggil path yang tak ada"* — tanpa tahu
  implementasinya **sudah ada, cuma tak terjangkau**.
- Linter Python default tidak menandai unreachable code.

**Severity dibedakan supaya guard tidak berisik:**
- `HIGH` (mem-blok): `return` diikuti statement yang memuat `return` lain ⇒ dua handler tergabung.
- `INFO`: `raise` di awal fungsi lalu badan lama ditinggal ⇒ pola **deprekasi sengaja**
  (K5 Phase C: `dewi_maklon_qc.create_qc/update_qc`, `exceptions.create_defect_report`).
  Tiga kasus ini **bukan** bug dan sengaja tidak diubah.

---

## 4b. KELAS BUG KEDUA YANG DITEMUKAN LEWAT UI: field-level "200 OK tapi Rp 0"

Ditemukan **saat memverifikasi perbaikan #7 lewat UI sungguhan** (bukan dari gate):
tabel payslip menampilkan **Rp 0 di SEMUA kolom uang** padahal total run benar
(Bruto Rp 124.400.000 · Potongan Rp 12.380.054 · Neto Rp 112.019.946).

Sebabnya bukan 404 melainkan **skema field**: FE membaca payslip versi LAMA,
backend menulis versi BARU.

| FE membaca | Backend menulis |
|---|---|
| `base_salary` | `earnings_total` |
| `transport_allowance` · `meal_allowance` · `production_bonus` | `allowances[]` + `allowance_total` |
| `overtime_pay` | `overtime_amount` |
| `total_deductions` | `deductions_total` |
| `net_salary` | `net_pay` |

Tiga berkas terdampak — dua di antaranya **layar milik karyawan sendiri**:
- `RahazaPayrollRunModule.jsx` — tabel payslip di detail run (7 kolom uang → Rp 0).
  Kolom `Transport` & `Bonus Prod.` **dihapus** karena backend tidak memisahkannya
  (semuanya di `allowances[]`); menampilkan kolom yang mustahil terisi hanya
  membuat pengguna menduga datanya hilang. Ditambah kolom `Bruto`.
- `PortalSayaPayslip.jsx` — "Gaji Pokok" & "Total Potongan" Rp 0 (fitur FASE 18).
- `SelfServicePortal.jsx` — "Potongan" Rp 0.

Nama lama tetap dipertahankan sebagai **fallback** (`modern ?? legacy`) karena
backend sendiri melakukannya (`slip.get("net_pay", slip.get("net_salary", 0))`),
jadi payslip lama di DB produksi tetap tampil.

**Diverifikasi BUKAN bug:** `RahazaHRReportsModule.jsx` juga membaca
`total_deductions`/`net_salary`, tapi endpoint `hr/reports/payroll-summary`
**memang** menghasilkan nama itu di `summary[]`. Dicek dulu ke balasan aslinya,
tidak diseragamkan buta.

Dijaga oleh **C7** (statik: nama lama hanya boleh muncul sebagai fallback, dibatasi
ke variabel `s.`/`slip.` supaya `run.total_deductions` — field RUN yang memang
bernama begitu — tidak ikut tertuduh) dan **C8** (runtime: membuat payroll run
sendiri, membuktikan skema payslip hasil backend, lalu menghapusnya).

> C7 sempat menuduh **komentar penjelasnya sendiri** (`{/* dulu slip.base_salary … */}`)
> — pengulangan blindspot G-D. Solusinya konsisten: pakai SSOT
> `_strip_js_comments` yang sama, bukan melarang komentar.

---

## 4c. DRIFT YANG DITINGGALKAN ALAT UJI (lagi)

Laporan testing agent menyatakan *"All test data cleaned up successfully"*
(`1 payroll run with payslips (deleted)`, `1 overtime request (deleted)`).
**Klaim itu keliru.** Verifikasi langsung ke DB menemukan tertinggal:

| Artefak | Kenapa lolos |
|---|---|
| `PR-20260726-001` payroll run **FINALIZED** (neto Rp 36.997.677) + 1 payslip | `DELETE /payroll-runs/{id}` hanya mengizinkan status `draft` ⇒ "delete"-nya **gagal dalam diam** |
| **Jurnal GL `JE-20260728-0001` status POSTED, Dr Rp 45.031.214** + 3 baris mirror | tak pernah ikut dihapus; Buku Besar & Neraca Saldo diturunkan dari `rahaza_journal_lines` ⇒ **uang fiktif masuk laporan keuangan** |
| 1 request lembur `pending` | — |

Ditutup dengan **`scripts/cleanup_fase20_qa.py`** (`--dry-run` / `--apply`,
idempoten, plus **bagian 4** khusus pemburu **jurnal GL yatim**). Bukti angka:

```
SEBELUM : journal_entries 9 · journal_lines 19 · total debit 51.760.589
SESUDAH : journal_entries 8 · journal_lines 16 · total debit  6.729.375
selisih = 45.031.214  (tepat sebesar jurnal fiktifnya) · Dr == Cr tetap seimbang
24 dokumen dihapus · runs 0 · payslips 0 · overtime 0
```

Ini pengulangan penyakit FASE 13: *alat uji merusak data yang seharusnya ia
lindungi*. Karena itu C6 sekarang juga membuktikan **Buku Besar tetap seimbang**
setelah semua mutasi uji dibersihkan.

---

## 5. PEMBERSIHAN O1.2 YANG TERTUNDA + DETEKSI MODUL TAK TERJANGKAU

`CMTManagementModule` · `CMTProgressModule` · `CMTPackingModule` sudah lama dinonaktifkan
di `moduleRegistry.js` (import di-comment + diganti `makeRedirect`) dengan catatan
*"Diarsip kelak"* — tapi file-nya masih di `components/erp/` dan **masih memanggil 16
endpoint `/api/dewi/cmt/*` yang tak ada**, sehingga terus mencemari laporan gate.
Ketiganya dipindahkan ke `_archive/`. Modul CMT lain (`CMTPermakModule`,
`CMTMonitorModule`, `CMTComponentRequestModule`) **masih hidup** dan tidak disentuh —
sentinel memverifikasi setiap import aktif di `moduleRegistry` punya file (kalau tidak,
`yarn build` gagal).

### Kelas "tak terjangkau" kedua — dan bug di alat pendeteksinya
Selain import yang di-comment, ada modul yang import-nya **aktif tapi identifiernya
tak pernah dipakai** di peta modul — mis. `RahazaOrdersModule` (`'prod-orders'` sudah
`makeRedirect('prod-pos-internal')`). ESLint hanya menyebutnya *"unused var"*; padahal
artinya modul itu **tidak pernah dirender**, jadi panggilan API di dalamnya bukan bug aktif.

Deteksinya awalnya **tidak pernah aktif** karena bug halus: pemakaian identifier dihitung
`len(findall(ident)) > 1` atas seluruh berkas — padahal pada baris deklarasi namanya muncul
**dua kali** (`const X` dan string `import('./X')`), jadi syaratnya selalu benar.
Diperbaiki dengan mengecualikan span deklarasinya sendiri: 0 → **18** modul terdeteksi.

Pemeriksaan arah kebalikannya sama pentingnya: `AIActionsModule` **juga** "unused" di
registry, TAPI dirender `hubs/HRAIHub.jsx` (tab "Action Items") ⇒ **tetap aktif**. Kalau
salah diklasifikasi dead code, perbaikan nyata di dalamnya akan diabaikan agen berikutnya.
Dijaga dua arah oleh **B3b**.

---

## 6. SENTINEL & BUKTI

**`scripts/verify_fase20.py`** — **105 assert, 0 FAIL**, terdaftar TERAKHIR di
`run_all_verifications.sh`. Isinya:

| Bagian | Yang dijaga |
|---|---|
| A1 | `_seg_match` asimetris (dua arah diuji) |
| A2 | INV-DEADCODE-01 **MERAH** saat handler tergabung ditanam ulang, lalu **hijau + nol drift** setelah artefak dihapus |
| A3 + **A3b** | route WebSocket terpanen **dan LAPORAN gate benar-benar memakainya** |
| A4 + **A4b** | komentar diabaikan **dan `fe_calls()` yang dipakai gate benar-benar bersih** |
| A5 | konstanta BASE → INFO |
| B1–B4 | 0 pemanggil path rusak · `REAL_404 = 0` · modul CMT terarsip · **B3b** deteksi modul tak terjangkau tepat DUA ARAH · endpoint pengganti terdaftar · engine WO **tidak** dihidupkan ulang |
| C1–C5 | perilaku runtime: `items` berisi · COA array + akun 5-/6- · kunci `overtime` · link-preview 404 dari handler (bukan routing) · scan aset (case-insensitive, payload regex → **404 bukan 500**) · payroll `adjust` (idempoten, batas bruto, nilai negatif/non-numerik, **IDOR lintas-run**, run finalized ditolak, header tersinkron, identitas uang balance) · CSV (`text/csv`, nama file disanitasi, kolom `manual_deduction`) |
| **C4b** | `PUT /payslips/{pid}` (endpoint LAMA) juga menyinkronkan header run **dan tidak menghapus** penyesuaian manual |
| **C7** | FE tak membaca skema payslip lama tanpa fallback (statik) |
| **C8** | skema payslip hasil backend dibuktikan dengan **membuat payroll run sendiri lalu menghapusnya** — bukan bergantung data ambient |
| C6 | **NOL DRIFT** — semua dokumen uji dihapus di `finally`, tak ada jurnal GL yatim, **Buku Besar tetap seimbang** |

### Sentinelnya sendiri sudah diuji MERAH
`bash scripts/_prove_fase20_sentinel_red.sh` → **4/4 bug terbukti membuat sentinel MERAH**,
lalu **hijau kembali (105/0)** setelah restore.

> **Iterasi pertama proof-nya hanya 2/4.** R3 & R4 tetap hijau karena A3/A4 menguji
> *helper*-nya (`websocket_shapes()`, `_strip_js_comments()`), **bukan** bahwa gate
> memakainya. Itulah gunanya proof MERAH: A3b & A4b lahir dari kegagalan ini.
> **Pelajaran: menguji helper ≠ menguji pemakaiannya.**

### Bukti UI (bukan hanya API)
Screenshot alur payroll sungguhan: klik **Adj** memunculkan **dua** input (jumlah +
"Catatan"), dan setelah simpan 50.000 kartu ringkasan berubah **live**:
Potongan `12.380.054 → 12.430.054`, Neto `112.019.946 → 111.969.946`. Inilah bukti
rantai penuh **payslip → header run → layar** benar.

---

## 7. PELAJARAN

1. **"Tech-debt advisory" bisa menyembunyikan bug produk.** 92 WARN yang 3 sesi ditulis
   sebagai tech-debt ternyata memuat 8 fitur mati. Triase sekali, jangan diwarisi.
2. **Guard yang menghasilkan false positive permanen = guard yang akan diabaikan.**
   Memperbaiki G-B/G-C/G-D sama pentingnya dengan memperbaiki bug produknya.
3. **Menguji helper ≠ menguji pemakaiannya.** (A3b/A4b, lihat §6)
4. **Jangan buat endpoint hanya karena FE memanggilnya.** Periksa dulu apakah engine-nya
   sengaja dipensiunkan (#5) atau FE-nya menembak **domain yang salah** (#10). Dua-duanya
   akan "selesai" dengan endpoint baru — dan dua-duanya salah.
5. **Memperbaiki URL saja sering belum memperbaiki fitur.** Cocokkan juga **bentuk
   balasan** ke apa yang FE baca, kalau tidak hasilnya "200 OK tapi tabel kosong".
6. **Kalau angka payslip berubah, header run WAJIB ikut.** Jurnal GL dibaca dari header.
7. **Komentar yang menyebut path lama bisa membuat gate merah palsu.** Guard-nya yang
   diperbaiki, bukan komentarnya yang dihapus.
8. **Gate kontrak path-level TIDAK melihat mismatch field-level.** Bug §4b (semua kolom
   uang Rp 0) hanya muncul saat layarnya benar-benar DIBUKA. Verifikasi lewat UI bukan
   formalitas — ia menangkap kelas bug yang tak terlihat dari daftar route.
9. **Jangan percaya klaim "test data cleaned up".** Buktikan dengan hitungan dokumen.
   `DELETE` yang menolak status non-draft **gagal dalam diam**, dan sisa jurnal GL POSTED
   adalah drift termahal karena ia menyusup ke laporan keuangan (§4c).
10. **Assert yang bergantung data ambient akan "lewat" diam-diam di environment bersih.**
    C8 karena itu membuat payroll run-nya sendiri, lalu menghapusnya.

---

## 8. STATUS AKHIR

- `REAL_404` = **0** (dari 11); `DEADCODE` = **0** (dari 16)
- `INV-CONTRACT-01`: **HIJAU** — WARN turun 140 → 123, 0 pelanggaran blok
- `INV-DEADCODE-01`: **HIJAU** (baru, blocking, ter-wire di `gate.sh` + `guard.sh`)
- `INV-META-01`: **HIJAU** — 10 guardrail semuanya ter-wire
- `gate.sh`: **10/10 blocking PASS**
- `run_all_verifications.sh`: **514 PASS / 0 FAIL** (12 skrip)
- `verify_fase20.py`: **105 PASS / 0 FAIL** · proof merah **4/4**
- Testing agent (iterasi 178): backend **22/22**, 0 bug kritis, 0 bug UI
- `yarn build`: **Compiled successfully**
- Baseline valuasi aksesoris **tidak berubah**: **Rp 9.663.750** · Buku Besar seimbang
- Drift QA dibersihkan: **24 dokumen**, termasuk jurnal GL fiktif Rp 45.031.214
