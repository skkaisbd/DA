#!/usr/bin/env bash
###############################################################################
# gate.sh — SATU perintah verifikasi. CV. Dewi Aditya ERP.
#
#   bash scripts/gate.sh          # cepat (statik + runtime inti)   ~60 detik
#   bash scripts/gate.sh --full    # + alur produk HR (absen/cuti/payslip)
#
# ─────────────────────────────────────────────────────────────────────────────
# FASE 21 — KENAPA GATE INI JAUH LEBIH KECIL DARIPADA SEBELUMNYA
# ─────────────────────────────────────────────────────────────────────────────
# Sebelumnya: 12 gate + 54 skrip alat (~16.000 baris). Akibat nyatanya:
#   · run_all_verifications.sh butuh >20 menit (12 skrip + jeda 25 detik/skrip)
#   · penjaganya sendiri jadi sumber bug: `_seg_match` simetris menyembunyikan
#     48 temuan · `fe_calls()` membaca komentar → merah palsu ·
#     `audit_duplication.py` membaca DOCSTRING sebagai penulis DB ·
#     `verify_phase_g_acc_opname.py` membocorkan stok + jurnal GL yatim ·
#     `cleanup_*_qa.py` mencocokkan teks penanda ⇒ selalu satu alat di belakang
#   · ada penjaga yang menjaga penjaga (`INV-META-01`) dan polisi "kualitas AI"
#     (`INV-QUALITY-01`) — nol nilainya bagi pengguna aplikasi
#
# 52 skrip (13.327 baris) DIHAPUS. Kriteria yang dipakai — hanya SATU pertanyaan:
#   "Kalau pemeriksaan ini hilang, apakah UANG, DATA, KEAMANAN, atau ALUR
#    PRODUK bisa rusak tanpa ada yang tahu?"
# Kalau tidak → dibuang. Pemeriksaan gaya kode, meta, dan audit duplikat tidak
# lolos kriteria itu.
###############################################################################
set -uo pipefail
CYAN='\033[96m'; GREEN='\033[92m'; RED='\033[91m'; YEL='\033[93m'; BOLD='\033[1m'; RST='\033[0m'
cd "$(dirname "$0")/.." || exit 1
RECEIPT="memory/GATE_RECEIPT.md"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
FULL=0
for a in "$@"; do [ "$a" = "--full" ] && FULL=1; done
declare -a NAMES RESULTS
OVERALL=0
START=$(date +%s)

run_gate () {  # $1=label  $2=perintah
  local label="$1"; shift
  local t0=$(date +%s)
  echo -e "\n${CYAN}${BOLD}▶ ${label}${RST}"
  bash -c "$*"
  local rc=$? t1=$(date +%s)
  if [ $rc -eq 0 ]; then
    echo -e "  ${GREEN}✓ ${label} PASS ($((t1-t0))s)${RST}"; NAMES+=("$label"); RESULTS+=("PASS")
  else
    echo -e "  ${RED}✗ ${label} FAIL (rc=$rc, $((t1-t0))s)${RST}"; NAMES+=("$label"); RESULTS+=("FAIL"); OVERALL=1
  fi
}
skip_gate () { echo -e "\n${YEL}▶ $1 — SKIP ($2)${RST}"; NAMES+=("$1"); RESULTS+=("SKIP"); }

echo -e "${CYAN}${BOLD}\n=============================================================="
echo "  GATE — CV. Dewi Aditya — $TS$([ $FULL -eq 1 ] && echo '  (--full)')"
echo -e "==============================================================${RST}"

# --- deteksi kesiapan backend + auth --------------------------------------
BACKEND_UP=0; AUTH_READY=0
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health 2>/dev/null | grep -qE "^[2-4]"; then
  BACKEND_UP=1; echo -e "${GREEN}  Backend RUNNING${RST}"
  ACODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/auth/login \
          -H "Content-Type: application/json" \
          -d '{"email":"admin@garment.com","password":"Admin@123"}' 2>/dev/null)
  [ "$ACODE" = "200" ] && { AUTH_READY=1; echo -e "${GREEN}  Admin login OK${RST}"; } \
                       || echo -e "${YEL}  Admin login HTTP $ACODE — gate runtime di-SKIP${RST}"
else
  echo -e "${YEL}  Backend down — gate runtime di-SKIP${RST}"
fi

# ══ 1. UANG & DATA (yang paling mahal kalau salah) ═══════════════════════════
run_gate "UANG/DATA — invarian GL, stok, AR/AP (verify_data_integrity)" \
         "python3 scripts/verify_data_integrity.py"
run_gate "UANG — baseline valuasi aksesoris (SSOT acc_baseline)" \
         "python3 scripts/lib/acc_baseline.py >/dev/null"

if [ $AUTH_READY -eq 1 ]; then
  run_gate "UANG — state machine jurnal (draft→posted→voided)" \
           "python3 scripts/verify_state_machine.py"
  run_gate "UANG — nomor dokumen tak boleh kembar saat balapan (RC-5)" \
           "python3 scripts/verify_concurrency.py"
  run_gate "UANG — batas nilai AR/AP/maklon (round6)" \
           "python3 scripts/round6_verify.py"
  # ══ 2. KEAMANAN ═══════════════════════════════════════════════════════════
  run_gate "KEAMANAN — akses lintas-role & tanpa token (RBAC/IDOR)" \
           "python3 scripts/guardrails/verify_rbac_idor.py"
  run_gate "KETAHANAN — input jahat harus 4xx, bukan 500" \
           "python3 scripts/guardrails/verify_adversarial_5xx.py"
  # ══ 3. BISA DIPAKAI ═══════════════════════════════════════════════════════
  run_gate "BISA DIPAKAI — endpoint kritis terjangkau" \
           "python3 scripts/health_check.py"
  # ══ ALUR PRODUK: PRODUKSI · MAKLON · CMT (audit 2026-07-31) ════════════════
  # Menjaga 12 invarian yang cacatnya TERBUKTI merusak angka lintas portal:
  # reject hilang, produced berkurang karena reject, stok FG di luar SSOT,
  # permak tidak berefek, SJ gabungan tak bisa dibaca. Lihat
  # docs/AUDIT_PRODUKSI_MAKLON_CMT.md — jangan hapus gate ini.
  run_gate "ALUR — produksi/maklon/CMT: reject, rework, stok FG, SJ gabungan" \
           "python3 scripts/verify_produksi_maklon_invariants.py"
  # ══ R&D (2026-08-07): DATA spesifikasi ukuran + UANG HPP hybrid ════════════
  # Cacat yang dijaga terbukti nyata sebelum perbaikan ini:
  #   · `measurements.values` dikunci NAMA kolom ⇒ ganti nama kolom membuat
  #     seluruh nilai ukuran YATIM tanpa peringatan (spesifikasi jahit lenyap).
  #   · SKU R&D `{STYLE}-{SIZE}-{COLOR}` terbalik dari SSOT ⇒ tak pernah cocok SKU FG.
  #   · Baris BOM tanpa tautan master tidak punya harga & konversi satuan ⇒ HPP
  #     salah DIAM-DIAM (keluhan asli owner).
  #   · HPP hybrid: total harus = Σ SEMUA baris, dan dokumen HPP lama tidak boleh bergeser.
  # Lihat memory/PROPOSAL_RND_WARNA_UKURAN_TECHPACK_HPP.md — jangan hapus gate ini.
  run_gate "DATA/UANG — R&D: ukuran tech pack, SKU SSOT, HPP hybrid (INV-RND)" \
           "python3 scripts/verify_rnd_invariants.py"
  # ══ R&D (2026-08-08): SSOT WARNA — palet master tidak boleh tercemar ════════
  # Bug NYATA yang membuat gate INV-RND-4 MERAH di DB hasil bootstrap bersih:
  # `rahaza_colors` di-seed lazy HANYA bila kosong, dan dulu penyemaian itu hanya
  # dipasang di endpoint DAFTAR. `utils.variant_ssot.ensure_color()` (dipakai
  # importir Excel + promosi varian R&D → master) tidak menyemai, sehingga
  # pemanggil pertama membuat warna SAMPAH ('NVY'/'NVY'/#CCCCCC) dan palet 15
  # warna asli TIDAK PERNAH ter-seed lagi ⇒ dropdown warna R&D kosong-makna dan
  # satu warna pecah dua kode ('NVY' + 'NAV') ⇒ SKU R&D tak cocok SKU FG.
  # Berjalan di DB SEMENTARA, tidak menyentuh data aplikasi.
  run_gate "DATA — SSOT warna: palet master bebas warna sampah (INV-COLOR)" \
           "python3 scripts/verify_color_palette_seed.py"
  # ══ R&D (2026-08-08): Padankan Ukuran + peringatan harga master basi ════════
  # Menjaga dua alat yang menutup konsekuensi kebijakan B1 & D1:
  #   · ukuran R&D "belum dipadankan" MEMBLOKIR PO produksi internal
  #     (`production_internal_adapter.py` mewajibkan `size_id` sah) — layar
  #     Padankan Ukuran harus benar-benar membuat `matched:true`, dan TIDAK
  #     boleh mengubah `size_list` style (ukuran tetap teks bebas).
  #   · daftar HPP harus menandai baris yang harga masternya sudah berubah
  #     TANPA menggeser satu rupiah pun angka tersimpan.
  run_gate "DATA/UANG — R&D: padankan ukuran + harga master basi (INV-RND2)" \
           "python3 scripts/verify_rnd_size_mapping_stale.py"
  # ══ CMT (2026-08-08): PORTAL CMT OVERRIDE — staf DA mengisi atas nama vendor ═
  # Fitur ini membolehkan staf DA MENULIS dokumen produksi atas nama vendor CMT
  # yang tidak memakai sistem — termasuk PROGRESS PRODUKSI, dasar tagihan CMT.
  # Tiga kelas kerusakan yang dijaga (semuanya pernah nyata saat dibangun):
  #   · KEWENANGAN — header `X-CMT-Override-Vendor` hanya boleh dihormati untuk
  #     role di core/cmt_override.OVERRIDE_ROLES, dan role lain harus DITOLAK 403
  #     (bukan "diabaikan diam-diam", karena kesalahan itu tak akan pernah terlihat);
  #     akun vendor pun tidak boleh memakainya (mustahil menyamar jadi vendor lain).
  #   · SCOPING — baca & tulis wajib terkurung ke vendor yang diwakili. Salah
  #     vendor = salah tagihan = uang keluar ke pihak yang salah.
  #   · JEJAK — setiap dokumen hasil override WAJIB berstempel `entered_by_staff`
  #     + `on_behalf_of_vendor` (keputusan owner 3a), dan layar monitoring/invoice
  #     harus MENERIMA bahan badge "diinput staf DA" (tanpa itu badge mustahil).
  # Ikut menjaga 2 bug pre-existing yang ditutup bersamaan: riwayat progress portal
  # vendor pernah SELALU KOSONG (filter `garment_id` yang tak pernah ditulis) dan
  # inbox reminder pernah BOCOR ke semua vendor (scoping role `vendor` saja).
  run_gate "KEAMANAN/UANG — Portal CMT Override: kewenangan, scoping, jejak (INV-CMTOV)" \
           "python3 scripts/verify_cmt_override.py"
  # ── INV-REKAP (2026-08-08) — Rekap Harian CMT ────────────────────────────────
  # Layar "vendor mana yang belum diisi hari ini" dipakai staf tiap pagi untuk
  # memutuskan siapa yang dikejar. Yang dijaga:
  #   · UANG — vendor yang belum setor progress tidak boleh tampak beres (progress
  #     = dasar tagihan CMT); dan vendor yang sudah setor tidak boleh tampak merah,
  #     karena sekali staf ditegur salah, alatnya ditinggalkan.
  #   · BATAS HARI WIB — jam container UTC; kalau batasnya bukan WIB maka selama
  #     07 jam tiap hari (00:00–07:00 WIB, persis jam produksi mulai) rekap "hari
  #     ini" menampilkan hari kemarin dan SEMUA vendor tampak belum mengisi.
  #   · SATU ANGKA — layar, Excel/PDF, dan sasaran tombol reminder wajib sama.
  #   · TIPE `received_at` — dulu hanya ditulis BROWSER sebagai STRING sehingga
  #     query rentang hari tidak pernah cocok (kolom "Terima" abadi ✗).
  #   · ANTI-SPAM — reminder idempoten per vendor per tanggal, dan reminder yang
  #     dilahirkannya sendiri tidak boleh membuat vendor abadi-merah.
  run_gate "UANG/PRODUK — Rekap Harian + Mingguan CMT: batas WIB, definisi terisi, SSOT export (INV-REKAP)" \
           "python3 scripts/verify_rekap_harian.py"
  # ── INV-PRODUK + INV-KATALOG (2026-08-10) — master produk ↔ katalog ↔ order ──
  # Semua yang dijaga di sini SUDAH pernah terbukti rusak di repo ini:
  #   · KODE PRODUK KEMBAR (T1) — form manual menulis `active`, promosi R&D hanya
  #     `status`, sementara index unik `code` memakai partialFilterExpression
  #     {active:true} ⇒ produk promosi di LUAR index ⇒ POST kode sama balas 200.
  #     Dua master untuk satu barang = stok/BOM/laporan pecah tanpa ada yang tahu.
  #   · KATEGORI BASI (P2b) & TEKS BEBAS (P3) — kategori dipakai filter/grouping
  #     katalog marketing; kalau tidak divalidasi & tidak dipropagasi, laporan
  #     per-kategori berbohong dengan sopan.
  #   · HPP 0 UNTUK PRODUK MANUAL (P1) & BERAT FG 0 (P4) — margin katalog mustahil
  #     dihitung dan biaya kirim salah.
  #   · OVERSELLING (M3) — `sync-from-wms` dulu mengabaikan `reserved_quantity` dan
  #     menaikkan stok katalog di atas yang tersedia (terbukti 5000 vs 4999).
  #   · ITEM LAHIR STOK 0 (M2) — "lokasi default" salah pilih ⇒ produk baru tampak
  #     habis ⇒ kehilangan penjualan TANPA pesan error.
  #   · ORDER TANPA TAUTAN (M9) — fulfillment mencocokkan order→barang dengan tangan
  #     setiap pesanan; salah pilih = stok salah turun.
  run_gate "UANG/DATA — Master Produk: kode kembar, kategori, HPP, berat, SKU (INV-PRODUK)" \
           "python3 scripts/verify_master_produk.py"
  run_gate "UANG — Katalog: satu rumus stok jual, anti-overselling, tautan order (INV-KATALOG)" \
           "python3 scripts/verify_katalog_stok.py"
  # ── INV-MKTSCOPE (2026-08-11) — lingkup toko marketing + mesin impor ─────────
  # Semua yang dijaga di sini TERBUKTI rusak sebelum F14 (audit terukur, bukan
  # dugaan — lihat memory/AUDIT_MARKETING_PORTAL_2026-08-11.md):
  #   · LINGKUP TOKO — 60/60 order, 25/25 iklan, 18/18 sesi live, 35/35 sample,
  #     30/30 konten, 10/10 diskon, 8/8 peluncuran TANPA `account_id`. Layar yang
  #     difilter per toko mengembalikan KOSONG dan laporan per akun Rp 0, tanpa
  #     satu pun error. Angka nol yang salah tetap ikut ke rapat.
  #   · TUJUAN IMPOR — mesin impor lama menulis kampanye diskon ke
  #     `marketing_discount_campaigns` dan sample ke `marketing_sample_shipments`,
  #     dua koleksi yang TIDAK PERNAH dibaca layar mana pun: impor "berhasil",
  #     datanya hilang.
  #   · ANGKA — "Rp 1.250.000" yang terbaca 1.25 salah dengan sopan.
  #   · TANPA AI — pemetaan kolom wajib jalan tanpa layanan luar; kalau tidak,
  #     impor harian staf mati begitu kuota AI habis.
  #   · KEWENANGAN — host/kreator yang belum di-assign ke toko harus DITOLAK,
  #     kalau tidak jam kerja & komisi bisa dibebankan ke toko yang salah.
  # Gate ini menguji dirinya sendiri dengan pelanggaran sintetis (MKS-22).
  run_gate "DATA/UANG — Marketing: lingkup toko + impor tanpa AI (INV-MKTSCOPE)" \
           "python3 scripts/verify_marketing_scope.py"
  # ── INV-MKTCYCLE (2026-08-13, F5) — siklus target · anggaran · omzet ─────────
  # Yang dijaga di sini juga TERBUKTI rusak sebelum F5 (bukan dugaan):
  #   · TIGA PULAU ANGKA — layar Target, layar Anggaran, dan Laporan menghitung
  #     sendiri-sendiri, jadi satu bulan bisa punya tiga kesimpulan. Gate menuntut
  #     `cycle/summary` = `budget/summary` = Σ baris `cycle/overview`.
  #   · DISKON SELALU Rp 0 — realisasi diskon hanya bisa masuk lewat entri manual
  #     yang tidak pernah diisi, padahal satu bulan memuat Rp 48 juta diskon
  #     penjual. Anggaran yang selalu "aman" membuat keputusan diskon diambil
  #     tanpa tahu biayanya. Gate memastikan angka otomatis TIDAK ditulis sebagai
  #     entri belanja (kalau ditulis, biaya yang sama dihitung dua kali).
  #   · TIDAK ADA KUNCI PERIODE — angka bulan yang sudah dirapatkan masih bisa
  #     berubah seminggu kemudian. Gate menutup periode sintetis lalu MENUNTUT 423
  #     (kunci yang tidak menolak tulisan sama dengan tidak ada kunci).
  #   · MARJIN TANPA CAKUPAN HPP — marjin 57% pernah tampil padahal HPP hanya
  #     diketahui untuk 0% unit terjual.
  run_gate "UANG/ARAH — Marketing: siklus target·anggaran·omzet + kunci periode (INV-MKTCYCLE)" \
           "python3 scripts/verify_marketing_cycle.py"
  # ── INV-KPIIMPOR (2026-08-13, F7.2/F6.4/F7.4) — impor KPI Seller Center ──────
  # Yang dijaga di sini adalah kerusakan yang PASTI terjadi tanpa gate ini:
  #   · BERKAS KPI TERBACA 0 KOLOM — seluruh ekspor KPI Shopee menaruh judul grup
  #     kolom di baris 0 (Live/Video), 6 baris metadata (laporan iklan), atau
  #     tanggal berbentuk RENTANG (statistik toko). Mesin impor generik mengambil
  #     baris pertama sebagai header ⇒ tidak satu pun kolom terpetakan.
  #   · GMV KPI DIJUMLAH DENGAN OMZET — angka "Penjualan" ekspor Shopee memakai
  #     definisi platform (pesanan dibuat/siap dikirim/dibayar). Kalau ia masuk ke
  #     `marketing_sales_data`, satu penjualan dihitung dua kali dan omzet turunan
  #     (F2) rusak. Gate menuntut koleksi terpisah + penanda `is_platform_kpi`.
  #   · BIAYA IKLAN DOBEL — laporan iklan dipilih per RENTANG; mengunggah "1–31
  #     Agu" setelah "7–13 Agu" menaikkan realisasi anggaran tanpa satu pun galat.
  #     Gate menuntut 409 untuk periode beririsan dan menuntut realisasi F5 = Σ biaya.
  #   · KPI KONTEN MENIMPA RENCANA STAF — impor memakai `published_url` sebagai
  #     kunci; kalau dokumen ditimpa utuh, judul & rencana konten staf hilang.
  #   · ASSIGN TOKO TIDAK ADA JALANNYA — F6 menjaga visibilitas per toko, tetapi
  #     `assigned_staff` sebelumnya hanya bisa diubah lewat skrip seed: aturan benar
  #     di kode, tidak bisa dipakai di lapangan. Gate menuntut assign/unassign
  #     berjejak dan efek 403 yang langsung.
  run_gate "DATA/UANG — Marketing: impor KPI Seller Center + assign toko + scorecard (INV-KPIIMPOR)" \
           "python3 test_core_f7_kpi_impor.py"
  # ── INV-MKTFULFILL (2026-08-14, F3) — impor Ekspor B/C + "Batalkan impor" ────
  # Tiga kerusakan yang TERBUKTI mahal dan hanya gate ini yang menahannya
  # (rinciannya di kepala test_core_f3_fulfillment.py):
  #   · PESANAN HANTU — berkas "Dikirim/Selesai" yang boleh membuat baris baru
  #     melahirkan pesanan tanpa item, tanpa uang, tanpa kreator: jumlah pesanan
  #     bulan itu naik tanpa satu pun penjualan.
  #   · STATUS MUNDUR — ekspor yang sama diunduh berkali-kali dan urutan barisnya
  #     tidak dijamin; baris kemarin menimpa hari ini ⇒ pesanan yang sudah sampai
  #     muncul lagi di daftar "belum dikirim", dan gudang mengirim dua kali.
  #   · "BATALKAN IMPOR" YANG TIDAK MENEPATI JANJI — impor ini tidak MEMBUAT
  #     baris, jadi rollback gaya lama melaporkan "0 baris dihapus" sambil
  #     membiarkan SELURUH perubahan status di tempatnya.
  # Plus dua kejujuran yang wajib dipertahankan: pesanan yang sudah batal/retur
  # TIDAK dihidupkan lagi oleh undo (stoknya sudah dilepas — menjanjikan barang
  # yang sama ke dua pembeli), dan usulan pemetaan kolom tidak boleh HILANG saat
  # staf memperbaiki satu kolom.
  run_gate "DATA/UANG — Marketing: status pengiriman (Ekspor B/C) + pemulihan impor (INV-MKTFULFILL)" \
           "python3 test_core_f3_fulfillment.py"
  # ── INV-MKTOPS (2026-08-14, F8) — Assign Toko · Ingat Pemetaan · Scorecard ───
  # Tiga janji layar yang sebelumnya tidak dijaga apa pun:
  #   · ALASAN WAJIB — kepala berkas `marketing_account_assign.py` menulis "setiap
  #     simpan wajib membawa alasan", padahal `reason` opsional. Jejak lengkap tanpa
  #     sebab tetap tidak menjawab "kenapa akses toko saya dicabut?".
  #   · GATE YANG MEMUSNAHKAN BUKTI — pembersihan gate F7.2 dulu menghapus SELURUH
  #     riwayat pemegang toko NYATA (`delete_many` per `account_id`). Satu kali
  #     `gate.sh` = riwayat toko hilang. Gate ini menjaganya secara statik.
  #   · INGATAN PEMETAAN YANG SENYAP & PERMANEN — pemetaan tersimpan dipakai ulang
  #     tanpa memberitahu siapa pun dan tidak bisa dilupakan, sehingga satu
  #     kesalahan yang pernah di-commit terpasang otomatis setiap hari. Ditambah
  #     pemetaan BASI (field sudah tidak ada di skema) yang dulu diterima apa adanya
  #     ⇒ kolomnya hilang dari hasil tanpa satu pun galat.
  #   · SCORECARD YANG TIDAK BISA DITELUSURI — total rincian WAJIB sama persis
  #     dengan baris scorecard, tiga sumber uang tidak boleh dijumlah, pesanan yang
  #     dikecualikan tetap tampil beserta sebabnya, kreator tanpa target ditandai
  #     "belum ada target" (bukan 0%).
  run_gate "DATA/KEWENANGAN — Marketing: assign toko · ingat pemetaan · scorecard kreator (INV-MKTOPS)" \
           "python3 test_core_f8_assign_ingat_scorecard.py"
  # ── INV-RETUR (2026-08-14, sesi #9) — OMZET BRUTO vs OMZET SETELAH RETUR ─────
  # Keputusan pemilik: tampilkan DUA angka, JANGAN geser angka lama. Yang dijaga
  # justru cara paling mudah melanggarnya tanpa satu pun galat:
  #   · memasukkan `returned` ke `EXCLUDED_FOR_REVENUE` "supaya lebih benar" ⇒
  #     SELURUH angka historis (target, capaian, pace, ROAS, lampiran rapat yang
  #     sudah beredar) berubah arti dalam senyap;
  #   · mengurangi "order amount retur" dari "omzet produk" ⇒ net terlalu kecil,
  #     dan tidak ada yang tahu karena keduanya "angka retur";
  #   · rumus retur kedua: dua pembaca lama memakai `revenue_product or revenue`
  #     yang memberi Rp 0 untuk pesanan yang diinput staf lewat layar;
  #   · hari yang rekapnya DIIMPOR/DIKETIK tidak tahu soal retur — melaporkannya
  #     sebagai "0 retur" adalah kebohongan yang paling mudah dipercaya;
  #   · angka yang hanya ada di JSON: gate memeriksa layar Siklus · Scorecard ·
  #     Rapat Mingguan (termasuk CSV/Excel/PDF) benar-benar memuatnya;
  #   · retur harus TETAP melepas reservasi stok & TERMINAL (anti-overselling).
  run_gate "UANG/ARAH — Marketing: omzet bruto vs setelah retur (INV-RETUR)" \
           "python3 test_core_returns_visibility.py"
  # ── INV-F6RBAC (2026-08-14, sesi #9) — LINGKUP TOKO PER PEMAKAI + JEJAK ──────
  # Aturan "siapa boleh melihat toko yang mana" sudah ada sejak F6, tetapi hanya
  # 7 dari 54 berkas route marketing memanggilnya. Diukur dengan dua token (staf
  # pemegang SATU toko vs admin), 14 endpoint memberi jawaban yang PERSIS SAMA:
  # omzet, biaya iklan, komplain, ulasan, sesi live, peringkat kreator, dan
  # RIWAYAT IMPOR (dari sana ada tombol "Batalkan & pulihkan" ⇒ jalan pintas
  # mengubah data toko orang lain). Yang dijaga gate ini:
  #   · jaring pengaman middleware: menukar `account_id` di path/query/body ⇒ 403,
  #     admin tidak terpengaruh, dan toko yang tidak ada TIDAK dibelokkan jadi 403;
  #   · endpoint DAFTAR/RINGKAS wajib menyaring sendiri — dibuktikan dengan
  #     membandingkan jawaban staf vs admin (identik pada data tak kosong = bocor);
  #   · layar "siapa mengubah apa": `total` jujur (bukan len(rows)), filter
  #     toko/aksi/pelaku/tanggal/teks, nilai LAMA→BARU per field, id user
  #     diterjemahkan jadi NAMA, dan jejak TIDAK punya endpoint tulis.
  run_gate "KEAMANAN/DATA — Marketing: lingkup toko per pemakai + jejak perubahan (INV-F6RBAC)" \
           "python3 test_core_f6_rbac_scope.py"

  # ── INV-F10 (2026-08-14, sesi #10) — LAYAR DAFTAR YANG BISA DIPAKAI ──────────
  # Audit 25 pintu Portal Marketing: hanya 2 yang bisa DIUNDUH. Angka yang benar
  # di layar tetapi tidak bisa dibawa ke rapat berakhir diketik ulang dengan
  # tangan (sumber salah-ketik paling umum). Juga ditemukan: Laporan Harian
  # MENYEMBUNYIKAN `sales_status.entered_live` yang sudah dikirim backend ⇒ toko
  # yang belum mengisi omzet LIVE tampak "sudah beres". Yang dijaga gate ini:
  #   · setiap pintu DAFTAR punya tabel nyata + cara menyempitkan + tombol unduh
  #     (dan pintu yang bukan daftar terdaftar BESERTA alasannya);
  #   · SATU pembuat CSV (`lib/csv.js`: escaping + BOM Excel) dan yang diunduh =
  #     baris yang TERLIHAT (bukan kueri ulang yang bisa berbeda dari layar);
  #   · tidak ada field respons yang tidak punya rumah di layar Laporan Harian.
  run_gate "BISA DIPAKAI — Marketing: layar daftar (tabel · cari · unduh) + field tak disembunyikan (INV-F10)" \
           "python3 test_core_f10_layar_daftar.py"

  # ── INV-F11 (2026-08-14, sesi #11) — PRATINJAU IMPOR **PER BARIS** ──────────
  # Mode "Perbarui yang lama" bisa mengubah STATUS pesanan (`paid → cancelled`).
  # Perubahan itu MELEPAS reservasi stok dan menurunkan omzet bulan yang mungkin
  # sudah dirapatkan. Sebelum Fase 4 satu-satunya cara melihat akibatnya adalah
  # "commit dulu, kalau salah tekan Batalkan impor" — memakai data sungguhan
  # sebagai kelinci percobaan. Yang dijaga gate ini justru cara paling mudah
  # merusaknya TANPA satu pun galat:
  #   · PRATINJAU YANG MENULIS — satu `update_one` menyelinap ke jalur pratinjau
  #     ⇒ membuka layar = mengubah data (penjaga statik atas 10 fungsi + pas
  #     runtime yang menghitung `marketing_orders` sebelum/sesudah pratinjau);
  #   · PRATINJAU YANG BERBEDA DARI KENYATAAN — lebih berbahaya daripada tidak
  #     punya pratinjau: keempat angka (baru/diperbarui+sebagian/dilewati/ditolak)
  #     dibandingkan dengan hasil commit SUNGGUHAN pada 6 keadaan berbeda;
  #   · PENGHALANG YANG DISALIN — pesan "periode sudah DITUTUP" ditulis dua kali
  #     ⇒ pratinjau & commit bercerita beda; di sini wajib SATU sumber, dan
  #     pesan di pratinjau harus SAMA PERSIS dengan penolakan 423 commit;
  #   · JANJI LAYAR YANG HILANG SAAT "DIRAPIKAN" — tabel baris, chip saring 5
  #     akibat (termasuk `ditolak`), pencarian, halaman, dan unduhan CSV; plus
  #     `total` halaman WAJIB dari server (bukan panjang satu halaman — cacat
  #     "Halaman 1 dari 1" untuk berkas 5.000 baris);
  #   · CSV RENCANA YANG KOSONG BERJUDUL BENAR — kolom "Nilai lama/Nilai baru"
  #     ada tetapi tanpa satu pun nilai; dan laporan HASIL tidak boleh bisa
  #     diunduh SEBELUM commit (laporan yang mengarang hasil).
  # Uji ini membuat sesi impor DEMO dan MEMBATALKANNYA SENDIRI lewat rollback
  # resmi (aturan: gate hanya boleh menghapus dokumen bertanda gate).
  run_gate "DATA/UANG — Marketing: pratinjau impor per baris = kenyataan (INV-F11)" \
           "python3 test_core_f11_pratinjau_impor.py"

  # ── INV-F12 (2026-08-14, sesi #11) — BERKAS YANG DIUNGGAH KE TOKO SALAH ─────
  # Sebelum ini hanya ada dua penjaga toko, dan KEDUANYA cuma pada satu jenis data
  # (`marketplace_orders`): `platform_guard` ("berkas Shopee masuk toko TikTok")
  # dan `shop_guard` (gudang platform di berkas bukan gudang toko tujuan). Yang
  # masih terbuka justru kesalahan harian: memilih toko yang salah dari 12 toko
  # yang namanya mirip (Shopee Daluna vs TikTok Daluna vs Shopee Moen vs TikTok
  # Style by Moen). Yang dijaga gate ini:
  #   · EKSPOR B/C TANPA SIDIK APA PUN — berkas toko A yang diunggah ke toko B
  #     dulu hanya menjawab "3 baris ditolak: belum pernah diimpor". Kalimat itu
  #     BENAR tetapi menyembunyikan sebabnya ⇒ staf mengira berkasnya rusak, atau
  #     (lebih mahal) memilih jenis "Pesanan Marketplace" supaya "mau masuk" ⇒
  #     pesanan HANTU tanpa item & tanpa omzet;
  #   · BUKTI, BUKAN DUGAAN — tanda pengenal GLOBAL (`SourceType.identity`: nomor
  #     pesanan / nomor komplain / URL konten) yang sudah tercatat pada toko LAIN.
  #     Jenis yang isinya memang tanpa penanda toko (mis. statistik toko Shopee =
  #     tanggal + kanal saja) WAJIB terdaftar di `NO_IDENTITY_REASON` beserta
  #     alasannya — kalau tidak, penjaganya sendiri yang akan MENUDUH SALAH;
  #   · AMBANG YANG TIDAK BOLEH DIBALIK — mayoritas baris milik toko lain ⇒
  #     PENGHALANG (commit 409); minoritas ⇒ PERINGATAN yang tetap boleh disimpan
  #     (berkas gabungan & staf yang sedang memperbaiki keadaan tidak boleh
  #     terkunci di luar). Peringatan TIDAK boleh mematikan tombol Simpan;
  #   · SATU SUMBER — pesan di pratinjau harus SAMA PERSIS dengan penolakan commit,
  #     dan jalur pratinjau TIDAK boleh menulis apa pun (versi pertama sempat
  #     menulis cache sidik isi berkas ke sesi milik toko LAIN).
  run_gate "DATA/UANG — Marketing: berkas ekspor tidak boleh masuk toko yang salah (INV-F12)" \
           "python3 test_core_f12_sidik_toko.py"

  # ── INV-F16 (2026-08-15, Fase E) — SATU RUMUS KAPASITAS KIRIM KE BUYER ─────
  # Keluhan pemilik yang dijaga di sini, tiga-tiganya PERNAH NYATA:
  #   · layar mem-prefill 100 lalu Simpan ditolak "maksimal 50" — karena layar
  #     dan pagar backend memakai RUMUS BERBEDA;
  #   · chip penerimaan tertulis "90" tapi tabel jadi "80" — karena layar
  #     memotong `reject_qty` dari `qty_actual` yang SUDAH netto lolos QC
  #     (dokumen bukti: `arrived = qty_actual + reject_qty`);
  #   · reject yang sudah DIPERBAIKI tidak pernah bisa dikirim — karena
  #     `apply_rework_outcome()` tidak menyentuh `cmt_receipt_lines` sementara
  #     pagar kirim membacanya. Sudah dibuktikan MERAH lewat sabotase.
  # Penjaga ini MEMBANGUN skenario 100 = 90 lolos + 10 reject lewat endpoint
  # asli, jadi ia menguji perilaku, bukan membaca kode.
  run_gate "UANG/STOK — Dispatch ke buyer: satu rumus sisa kirim + hasil permak bisa dikirim (INV-F16)" \
           "python3 scripts/verify_fase_e_kapasitas_kirim.py"

  # ── INV-F17 (2026-08-15, Fase F) — DOKUMEN PDF TIDAK TUMPANG TINDIH ────────
  # Diukur dari PDF SUNGGUHAN (bbox tiap potongan teks), bukan dari membaca kode:
  # tumpang tindih = 0, tabel mengisi ≥97% lebar konten, tidak ada teks keluar
  # margin, dan dokumen kumulatif tidak lagi memuat SUBTOTAL per PO.
  # Sebabnya dulu: baris "SUBTOTAL {po}" ditulis ke kolom selebar 44 pt memakai
  # `Table()` mentah berisi STRING (tanpa word-wrap) + lebar kolom hardcode 569
  # pt padahal lebar konten A4 landscape 773,8 pt.
  run_gate "DOKUMEN — PDF rapi: 0 tumpang tindih + tabel penuh lebar halaman (INV-F17)" \
           "python3 scripts/verify_fase_f_pdf_rapi.py"

  # ── INV-F18 (2026-08-15, Fase H-1) — KIRIM MATERIAL KE CMT MEMOTONG STOK ───
  # Keluhan pemilik: "kirim material ke cmt — bahan dikirimkan dan berkurang,
  # tidak perlu ada ketik ketik lagi". Yang DIUKUR sebelum perbaikan:
  # `POST /api/vendor-shipments` hanya menulis surat jalan + item GARMEN, NOL
  # mutasi `rahaza_material_stock`, NOL dokumen pengeluaran, NOL jurnal ⇒ kain &
  # aksesoris keluar gudang tanpa jejak dan nilai persediaan menggelembung.
  # Penjaga ini juga menahan DUA arah salah:
  #   · stok kurang harus MENOLAK surat jalan tanpa meninggalkan dokumen yatim;
  #   · MAKLON tidak boleh memotong stok DA (materialnya milik klien).
  # Sudah dibuktikan MERAH lewat sabotase (stok "turun 0").
  run_gate "STOK/UANG — Kirim material ke CMT menerbitkan MI + memotong stok + jurnal (INV-F18)" \
           "python3 scripts/verify_fase_h1_kirim_material_potong_stok.py"

  # ── INV-F19 (2026-08-16, Fase H-2/H-3/H-4) — PORTAL GUDANG: PINTU YANG HIDUP ─
  # Tiga keluhan pemilik dijaga sekaligus, dan ketiganya PERNAH terukur:
  #   · "pengeluaran material tidak ada tombol buatnya" — layar MI 488 baris tanpa
  #     satu pun jalur create; gerbang POST-nya hanya meloloskan admin/superadmin
  #     sehingga ADMIN GUDANG & SUPERVISOR PRODUKSI (yang mengerjakannya) 403;
  #   · "buat barcode belum ada menunya" — endpoint label bahan & FG ada
  #     berbulan-bulan dengan 0 pemanggil UI, hanya 1 label per item, dan jalur FG
  #     membaca `rahaza_fg_matrix` yang KOSONG ⇒ SELALU 404 untuk barang yang ADA;
  #   · "kirim cmt & scan gudang menu mati" — keduanya menunjuk koleksi 0 dokumen.
  # Penjaga ini juga menahan dua arah salah: kode di luar master tidak boleh
  # dicetak (barcode harus bisa discan jadi item nyata) dan pintu yang dilepas dari
  # sidebar TIDAK boleh hilang dari moduleRegistry (deep-link lama mati diam-diam).
  run_gate "PRODUK/STOK — Gudang: tombol buat MI, Buat Barcode, menu mati dilepas (INV-F19)" \
           "python3 scripts/verify_fase_h_gudang.py"

  # ── INV-F20 (2026-08-16, Fase D) — DASHBOARD MARKETING: PINTU + ANGKA RESMI ──
  # `toko-dashboard` sudah lama jadi modul BAWAAN Portal Marketing tetapi TIDAK
  # tercantum di satu pun sidebar ⇒ tidak ada jalan pulang ke dashboard selain
  # memuat ulang portal ("dashboardnya hilang dari menu"). Dan isinya tidak pernah
  # memuat target/anggaran/ROI — hanya penjumlahan input harian 30 hari terakhir,
  # rentang yang selalu menyerempet dua bulan sehingga omzet mustahil disandingkan
  # dengan targetnya. Gate ini menahan tiga arah salah sekaligus: pintu menghilang
  # lagi, angka resmi dijumlah ulang di browser (layar vs ekspor bisa beda), dan
  # ROI diklaim sahih padahal HPP belum tertaut (−100% terbaca sebagai kerugian).
  run_gate "LAYAR/UANG — Dashboard Marketing: ada pintunya + angka resmi dari SSOT siklus (INV-F20)" \
           "python3 scripts/verify_fase_d_dashboard_marketing.py"

  # ── INV-F21 (2026-08-16, Fase G) — NOMOR DOKUMEN: OTOMATIS vs MANUAL ────────
  # Pondasi penomoran (47 jenis dokumen, satu generator race-safe, layar format)
  # sudah lama ada, tetapi MODE-nya cuma implisit: kolom nomor diisi ⇒ dipakai apa
  # adanya TANPA pemeriksaan. `production_pos` — sumber nomor SPP — bahkan
  # MEWAJIBKAN nomor diketik tangan, dan arsipnya kini bercampur `PO-INT-DEMO-1`,
  # `PO-MK-DEMO-1`, `PO-MKL-GAB-A`: tiga pola untuk satu jenis dokumen, tidak bisa
  # diurutkan maupun dicari. Gate ini menahan empat arah salah: nomor bebas lolos,
  # nomor ganda, penolakan diam-diam (nomor ketikan diabaikan tanpa pesan), dan
  # penomoran GANDA pada dokumen cermin PO Maklon.
  run_gate "DATA — Nomor dokumen: mode Otomatis/Manual ditegakkan, nomor bebas ditolak (INV-F21)" \
           "python3 scripts/verify_fase_g_penomoran.py"

  # ── INV-F22 (2026-08-16, Fase H-5/H-6) — GULUNGAN KAIN: LAHIR & MATI ────────
  # Terukur sebelum perbaikan: `wh_fabric_rolls` hanya bisa diisi MANUAL dengan
  # nomor DIKETIK (dua gulungan fisik bisa bernomor sama), penerimaan kain menambah
  # stok TANPA pernah menyentuh roll (420 kg kain di sistem, NOL gulungan yang bisa
  # ditunjuk), dan Cutting mengurangi roll HANYA kalau `roll_id` dikirim — padahal
  # memilihnya opsional, jadi kain bisa dipotong tanpa satu gulungan pun berkurang.
  # Sesi lalu bahkan berhenti dengan 4 `undefined name` di jalur roll (backend tetap
  # start ⇒ kerusakan tak terlihat sampai GR kain dijalankan). Gate ini menahan lima
  # arah salah: import jalur roll hilang lagi, nomor roll diketik/kembar, stok naik
  # tanpa gulungan, penolakan rincian roll yang menyisakan stok setengah jalan, dan
  # cutting memotong kain tanpa bisa membuktikan gulungan mana yang dipakai.
  run_gate "STOK/PRODUK — Gulungan kain: lahir dari penerimaan, wajib ditunjuk saat dipotong (INV-F22)" \
           "python3 scripts/verify_fase_h5_h6_roll.py"

  # ── INV-F23 (2026-08-16, Fase H-7/H-8) — SURAT JALAN & PINTU MENU ───────────
  # Terukur sebelum perbaikan: layar "Surat Jalan" HANYA membaca `wh_delivery_notes`
  # (2 dokumen DEMO), sementara surat jalan operasional hidup di `vendor_shipments` (4)
  # dan `buyer_shipment_items` (8 pengiriman) ⇒ satu pertanyaan ("surat jalan apa saja
  # yang keluar?") butuh tiga layar di dua portal. Dan empat alias lama
  # (`cmt-progress`, `do-management`, `prod-cmt-packing`, `maklon-packing`) diarahkan ke
  # `wms-cmt-dispatches` yang koleksinya 0 dokumen — empat pintu ke layar kosong.
  # Gate ini menahan: dokumen hilang dari daftar gabungan, pengiriman buyer ke-2/ke-3
  # tersembunyi, baris yang tak bisa dicetak, rekap PDF tumpang tindih/kekecilan,
  # agregasi yang ternyata MENULIS, dan alias yang kembali menunjuk modul kosong.
  run_gate "DOKUMEN/NAVIGASI — Surat jalan satu daftar lintas sumber + pintu lama tak kosong (INV-F23)" \
           "python3 scripts/verify_fase_h7_h8_surat_jalan.py"

  # ── INV-F24 (2026-08-17, Fase H-6b) — ARUS KELUAR CUTTING BERDOKUMEN ────────
  # Terukur sebelum perbaikan: Portal Cutting memotong stok kain + sisa gulungan
  # dengan benar, tetapi TIDAK PERNAH menulis dokumen `rahaza_material_issues` dan
  # tidak satu baris pun ke kartu stok ⇒ arus keluar kain lewat Cutting TIDAK ADA
  # di layar "Pengeluaran Material" (dua pintu keluar lain sudah berdokumen), jadi
  # jawaban atas "material apa saja yang keluar hari ini?" salah secara sistematis.
  # Gate ini menahan enam arah salah yang semuanya bisa terjadi diam-diam: stok/
  # gulungan dipotong DUA KALI, beban hantu di buku besar (dokumen cutting ikut
  # dijurnal Dr WIP/Cr Persediaan padahal nilai kain hanya BERPINDAH jadi nilai
  # potongan), dokumen arus keluar bisa dihapus/di-approve, penyaring sumber yang
  # bohong, lapisan rekap yang ternyata MENULIS, dan dokumen kembar saat backfill
  # dijalankan berulang. Plus dua pemeriksaan statik: urutan route literal (pelajaran
  # sesi #16) dan LAYAR benar-benar memakai fiturnya (anti "backend jadi, UI tidak").
  run_gate "STOK/DOKUMEN — Arus keluar Cutting berdokumen, stok turun sekali (INV-F24)" \
           "python3 scripts/verify_fase_h6b_cutting_issue.py"

  # ── INV-F25 (2026-08-17, Fase G lanjutan) — SETELAN PENOMORAN TIDAK BERBOHONG ─
  # Terukur sebelum perbaikan: layar Penomoran Dokumen menampilkan pilihan
  # Otomatis/Manual untuk 49 jenis dokumen, tetapi hanya DUA jalur tulis yang
  # benar-benar memanggil `issue_number`. Untuk 47 jenis lain owner bisa memindah ke
  # "Manual", setelan itu TERSIMPAN dan tampil di layar — lalu dokumennya tetap
  # bernomor otomatis. Setelan yang tidak ditegakkan lebih buruk daripada setelan yang
  # tidak ada. Ditambah: Kasbon & Pinjaman berbagi satu field sehingga satu kebijakan
  # dipaksa untuk dua jenis dokumen, dan nomor yang lahir (`KSB-00001`) tidak mengikuti
  # format yang tertulis di layar. Gate ini menahan: jenis yang MENGAKU ditegakkan
  # padahal jalur tulisnya tidak, mode manual/otomatis yang tidak berlaku, nomor kembar,
  # kebijakan dua dokumen yang tercampur, dan layar yang tidak membaca kebijakan.
  run_gate "DATA — Setelan penomoran dokumen benar-benar ditegakkan (INV-F25)" \
           "python3 scripts/verify_fase_g2_penomoran_ditegakkan.py"

  # ── INV-F26 (2026-08-18, SESI #19) — TEMPLATE PDF TERCETAK & SATU PINTU ─────
  # Keluhan pemilik: "editor pdf masih sangat buruk", "ada dua halaman berbeda ui
  # ux-nya", "header surat sangat buruk sekali". Yang TERUKUR sebelum perbaikan:
  # dua koleksi setelan (`pdf_document_settings` untuk kop/TTD, `pdf_export_configs`
  # untuk kolom) dengan dua layar berbeda mengatur SATU dokumen; kop tidak bisa
  # memuat LOGO sama sekali (`show_logo` disimpan tetapi tidak ada generator yang
  # menggambar gambar); kolom hanya bisa disembunyikan (urutan selalu urutan kode,
  # kolom baru tidak mungkin); blok tanda tangan dipotong tiga (`sig_defs[:3]`)
  # sehingga blok keempat hilang tanpa pesan; Pick List tanpa kop sama sekali dan
  # tabelnya 174 mm dari 186 mm lebar konten.
  # Gate ini MENGUKUR DARI PDF JADI (pymupdf): kop+logo dari konfigurasi benar-benar
  # tercetak di dokumen sungguhan, urutan/tampil-tidak kolom berlaku, jumlah blok
  # tanda tangan sesuai setelan, 0 tumpang tindih, tabel ≥97% lebar konten, logo
  # divalidasi, dan endpoint warisan membaca template yang sama (bukan sumber kedua).
  run_gate "DOKUMEN — Template PDF (kop/logo/kolom/TTD) benar-benar tercetak (INV-F26)" \
           "python3 scripts/verify_fase_i_pdf_template.py"

  # ── INV-F27 (2026-06, keluhan pemilik) — PERMAK ↔ REJECT, DISPATCH LANJUTAN,
  #    AKSESORIS BOM & KIRIMAN PENGGANTI ────────────────────────────────────────
  # Lima cacat yang TERUKUR sebelum perbaikan (bukti "sebelum" tetap disimpan di
  # `scripts/_repro_5bug_produksi_maklon.py`):
  #   · permak yang dibuat dari form "Buat Permak Baru" tersimpan TANPA tautan
  #     baris penerimaan ⇒ permak berhasil tidak pernah menaikkan hasil permak,
  #     stok FG tidak dilepas dari karantina, dan barang yang sudah bagus MUSTAHIL
  #     dikirim ke buyer (pagar kirim membaca baris penerimaan);
  #   · pengiriman bertahap tidak bisa dilanjutkan: setiap simpan melahirkan surat
  #     jalan BARU dengan nomor baru dan dispatch_seq kembali ke 1, jadi satu PO
  #     punya beberapa surat jalan dan tidak satu pun mencapai 100%;
  #   · form buat PO maklon tidak menampilkan aksesoris BOM katalog sama sekali ⇒
  #     pemakai menyangka BOM belum kena lalu mengetik ulang (baris kembar);
  #   · vendor CMT tidak punya SATU pintu pun untuk meminta material PENGGANTI
  #     (jalur lamanya sudah dimatikan backend dengan HTTP 410);
  #   · surat jalan ANAK (pengganti) tetap membawa daftar aksesoris PO ⇒ form
  #     inspeksi vendor memuat aksesoris yang tak pernah dikirim.
  # Gate ini menguji PERILAKU lewat endpoint asli (memakai pembangun skenario yang
  # sama dengan INV-F16, bukan skenario kedua) + memastikan pintunya ADA di layar.
  run_gate "STOK/DOKUMEN — Permak menaikkan sisa kirim · dispatch lanjutan · aksesoris BOM (INV-F27)" \
           "python3 scripts/verify_permak_dispatch_aksesoris.py"

  # ── INV-F28 (2026-06, keluhan pemilik) — MONITORING CMT: POTONGAN SESUAI ORDER
  # Angka di Monitoring CMT dipakai owner untuk menagih vendor, jadi kalau ia
  # membengkak sendiri, keputusannya salah. Yang TERUKUR sebelum perbaikan:
  #   · "Potongan ke CMT" menjumlahkan SEMUA `vendor_shipment_items` termasuk surat
  #     jalan ANAK (pengganti/tambahan) ⇒ order 100 dilaporkan 105, dan
  #     "Sisa di CMT" memunculkan 5 pcs HANTU walau CMT sudah menyetor semuanya;
  #   · papan hanya membuang PO Closed/Cancelled/Selesai — PO **Completed** tetap
  #     ikut dihitung, jadi angka "yang sedang berjalan" tidak pernah bisa dilihat;
  #   · tidak ada angka "belum dikirim ke CMT" (masih di gudang) maupun "sudah
  #     dikirim ke buyer", padahal keduanya ada di SSOT yang sudah dipakai layar lain;
  #   · permintaan PENGGANTI yang disetujui menerbitkan surat jalan anak tetapi
  #     rantainya tidak terlacak di layar (tidak ada penunjuk balik & rekap qty).
  # Gate ini menguji lewat endpoint asli + memastikan pintunya ADA di layar.
  run_gate "UANG/DATA — Monitoring CMT: potongan sesuai order · scope PO · lacak pengganti (INV-F28)" \
           "python3 scripts/verify_monitoring_cmt_potongan.py"

  # ── INV-F29 (2026-08-18, SESI #20 — keluhan pemilik) — SATU IDENTITAS BARANG ──
  # Keluhan verbatim: "list barang dari marketing untuk dikirimkan oleh tim gudang
  # tidak ada yang sama, id-nya antara gudang dan marketing tidak sinkron".
  # Yang TERUKUR sebelum perbaikan (tests/poc_sync_forensic.py, data hidup):
  #   · 0 dari 601 baris pesanan marketing menunjuk master gudang (fg_material_id);
  #   · 83 SKU platform dipesan pembeli tanpa dikenal master, dan tabel jembatan
  #     `marketing_catalog_items.platform_sku_ids[]` KOSONG — satu-satunya pintu
  #     pemetaan menempel pada SESI IMPOR, jadi SKU dari sesi terhapus mustahil
  #     dipetakan (pemetaan identitas barang adalah MASTER, bukan lampiran unggahan);
  #   · 559 pesanan "Perlu dikirim" tersimpan `fulfillment_status='unallocated'`
  #     sementara antrean gudang hanya mencari 'pending_fulfillment' ⇒ layar gudang
  #     menampilkan 0 pekerjaan. Dua penulis, dua kamus, yang membaca kalah.
  # Gate ini menjaga: satu kosakata status, jembatan mandiri ber-index unik, 0
  # rujukan menggantung, satu pemetaan menautkan SELURUH pesanan (idempoten), mesin
  # usulan yang menolak menebak, laporan audit yang angkanya sama dengan DB, dan
  # pintunya benar-benar ada di layar.
  run_gate "DATA — Sinkronisasi identitas barang Marketing ⇄ Gudang (INV-F29)" \
           "python3 scripts/verify_sinkronisasi_marketing_gudang.py"

  # ── INV-F30 (2026-08-19, SESI #28) — IDENTITAS BARANG TIDAK BOLEH MENABRAK ───
  # Jembatan #20 (INV-F29) terbukti BENAR, tetapi tidak satu barang pun pernah
  # dijembatani: `sync-audit` melaporkan `A1 CRITICAL: NOL dari 601 baris pesanan
  # menunjuk master gudang` dan `A5: 553 pesanan di antrean gudang, tidak satu pun
  # siap dialokasikan`. Sebabnya diukur pada 83 SKU nyata:
  #   · mesin identitas lama menabrakkan 83 SKU menjadi 35 identitas — 16 kelompok
  #     tabrakan, 63 SKU (76%) & 489 pcs (81%) tertimpa. Terburuk: 8 SKU berbeda
  #     jatuh ke satu `hitam/XL` (BLACK…PAKAI KARET · POLKA BLACK…SMOOK ·
  #     POLKA BLACK…TANPA KARET · BLACK…TANPA KARET …) ⇒ gudang mengambil BARANG
  #     YANG SALAH untuk 4 dari 5 pesanan;
  #   · dua akar: (1) warna majemuk dipotong pencocokan substring (`POLKA WHITE`
  #     menemukan alias `white` ⇒ jadi `putih`, motif polkadot HILANG); (2)
  #     `PAKAI/TANPA KARET` & `(SMOOK)` tidak dibaca sama sekali, dan skema varian
  #     hanya punya 2 sumbu sehingga tidak ada tempat menyimpannya;
  #   · `clean_product_name` justru MEMBUANG nama produknya ("ONA DRESS - Midi
  #     Dress Salur…" → "Midi Dress Salur…") sehingga 4 produk bisa jadi 1 model.
  # Gate ini menjaga: identitas INJEKTIF (variasi beda ⇒ identitas beda, variasi
  # sama ⇒ identitas sama), dimensi ke-3 "Opsi" hidup & berasal dari master, index
  # unik 4 sumbu, KOMPATIBEL-BALIK (SKU 330 varian lama tidak berubah), pratinjau
  # yang tidak menulis, apply idempoten, rantai pemetaan→varian→FG→katalog utuh,
  # palet warna bebas kembar, pintunya ADA di layar, dan alat ukur yang tidak
  # mengotori data yang diukurnya.
  run_gate "DATA/STOK — Identitas barang: warna·ukuran·OPSI tidak menabrak (INV-F30)" \
           "python3 scripts/verify_identitas_varian_3dimensi.py"

  # ══ SESI #29 (W4, keluhan pemilik): "Retur Fisik & Restock tidak terkoneksi
  # ke portal marketing". Diukur SEBELUM perbaikan: `marketing_returns` = 30
  # dokumen retur pembeli NYATA sementara `wh_returns` = 0 ⇒ antrean retur
  # gudang KOSONG SELAMANYA; dan tombol "Restock ke Gudang" menulis ke
  # `rahaza_fg_inventory` (koleksi MATI, 0 dokumen) memakai `sku_code` yang
  # selalu dikirim kosong ⇒ stok nyata TIDAK PERNAH bertambah, 0 baris ledger.
  # Gate ini menjaga: pintunya ada di layar (pemilik minta DIHIDUPKAN, bukan
  # dihapus), retur pembeli otomatis jadi pekerjaan gudang, stok hanya bergerak
  # lewat core/stock_service, barang RUSAK ditahan di karantina & tidak bisa
  # dijual, idempoten (klik dua kali tidak menggandakan stok), tidak menebak
  # barang pada pesanan multi-baris, dan alat ukurnya bersih.
  run_gate "ALUR/STOK — Retur pembeli Marketing → Retur Fisik gudang → stok (INV-F31)" \
           "python3 scripts/verify_jembatan_retur_marketing_gudang.py"

  # ══ SESI #29 (W1 & W2, keluhan pemilik): (a) "tabel FG tidak sinkron" +
  # "material id seharusnya tidak perlu ada di table ini"; (b) "PDF masih belum
  # lengkap … untuk produksi ada data no serial namun di pdf tidak ada
  # pilihannya". Diukur SEBELUM perbaikan: layar Viewer Stok menampilkan UUID
  # `material_id` sebagai kolom PERTAMA (dan mengekspornya ke CSV), tanpa kolom
  # kategori/warna/opsi padahal ketiganya sudah ada di master; layar menampilkan
  # 26 BARIS STOK untuk 321 barang jadi ⇒ tampak tidak sinkron dengan Master
  # Item. Untuk ekspor: kolom Serial sudah ada di katalog tetapi tidak ada pintu
  # memilihnya saat mencetak, dan memakai konfigurasi kolom pada laporan produksi
  # justru MENGGAGALKAN cetakan (500 "list index out of range") karena kolom
  # difilter DUA KALI. Gate ini menjaga semuanya, termasuk bukti dari teks PDF jadi.
  run_gate "LAYAR/DOKUMEN — Tabel stok terbaca & kolom cetak bisa dipilih (INV-F32)" \
           "python3 scripts/verify_tabel_stok_dan_ekspor_kolom.py"

  # ══ SESI #29 (W5, permintaan pemilik): "buatkan surat jalan CMT yang kirim ke
  # DA, export nya adakan saja di terima FG dari cmt". Diukur SEBELUM dikerjakan:
  # katalog PDF punya 3 surat jalan (gudang · material ke vendor · dispatch buyer)
  # tetapi TIDAK ADA untuk arah CMT → DA — padahal itu arah barang MASUK gudang
  # DA — dan layar "Terima FG dari CMT" tidak punya satu pun tombol cetak, jadi
  # pengantar barang vendor tidak punya dokumen untuk ditandatangani. Gate ini
  # menjaga: jenis dokumennya terdaftar (kolom hasil QC = PILIHAN, bukan dokumen
  # kedua), nomornya terlihat & bisa diatur pemilik + IDEMPOTEN per penerimaan,
  # nomor seri benar-benar ter-resolve dari master, kop/TTD memakai SATU
  # konfigurasi PDF yang sudah ada, input rusak 4xx bukan 500, dan alat ukurnya
  # tidak meninggalkan dokumen maupun nomor terpakai.
  run_gate "DOKUMEN — Surat jalan CMT → DA bisa dicetak dari penerimaan FG (INV-F33)" \
           "python3 scripts/verify_surat_jalan_cmt.py"

  # ══ SESI #29 (W3, keluhan pemilik): "Alert & Reorder tidak pernah berbunyi".
  # Diukur SEBELUM dikerjakan: 333 dari 333 material TIDAK punya ambang sama
  # sekali (tidak ada layar untuk mengisinya massal), DAN ada tiga definisi
  # "stok rendah" yang hidup terpisah (layar alert hanya `reorder_point`;
  # notifikasi hanya `min_stock` legacy; dashboard urutan sendiri) — dua di
  # antaranya menjumlahkan `$qty` saja sehingga baris stok skema lama
  # (`total_qty`) tidak terbaca. Gate ini menjaga: ambang bisa diisi massal
  # dengan usulan dari pemakaian NYATA (tanpa menebak), alarmnya benar-benar
  # berbunyi & berhenti sesuai ambang, ketiga pembaca sepakat, stok dibaca
  # kanonik, layar jujur soal material yang belum berambang, dan alat ukurnya
  # memulihkan data hidup.
  run_gate "STOK — Alert stok hidup & satu definisi 'rendah' (INV-F34)" \
           "python3 scripts/verify_alert_stok_hidup.py"

  # ══ SESI #30 (keluhan pemilik): (1) "purchasing itu yard namun di tracking roll
  # menjadi meter … di roll jangan dipaksakan meter"; (2) "ketika cutting harusnya
  # nama produk/style mengambil dari master data … supaya BOM & produksi jelas
  # produknya ada"; (3) "harga satuan otomatis dari pembelian purchase order,
  # jangan dari input di master data — untuk semua jenis kain maupun aksesoris".
  # Diukur SEBELUM dikerjakan: `ROLL_UOM` memaksa rol/gulung→meter & layar menulis
  # kolom "(m)" mati (padahal angkanya yard, tidak ada konversi yang terjadi);
  # dialog Issue menyediakan satuan meter/kg sehingga gulungan yard bisa terkuras
  # dengan label salah atau dijawab "sisa 0"; `POST /cutting/orders` menerima
  # `style_name` ketikan bebas tanpa `model_id`; dan mesin HPP rata-rata bergerak
  # hanya dipanggil dari penerimaan aksesoris — GR dari PO tidak pernah menyentuh
  # harga, jadi harga hanya bisa diketik di Master Item.
  run_gate "STOK/PRODUKSI — Satuan gulungan, style dari master, harga dari pembelian (INV-F35)" \
           "python3 scripts/verify_uom_roll_dan_style_master.py"

  # ── INV-F36 (2026-08-23) — HPP PER POTONG LAHIR DARI PEMBELIAN + BOM ──────
  # Lanjutan langsung INV-F35: setelah harga BAHAN lahir dari pembelian, HPP
  # PRODUK JADI masih 0 untuk 321 dokumen FG (`hpp_source: 'none'`) dan satu-
  # satunya sumber HPP model adalah kalkulator R&D atau KETIKAN `base_hpp` —
  # jadi kolom margin di Katalog Marketing mustahil hidup. Selain itu rencana
  # pemakaian kain pada Order Cutting masih DITEBAK manual walau BOM per
  # model+size sudah menyimpan kebutuhan per pcs. Gate ini menjaga: biaya bahan
  # sadar satuan, bahan tanpa harga jadi kekurangan (bukan 0 diam-diam), upah
  # CMT & cutting punya sumber yang dilaporkan, overhead tetap OPSIONAL,
  # penerapan menulis ke master+FG+katalog secara idempoten, dan BOM benar-benar
  # mengisi rencana cutting.
  run_gate "UANG/PRODUKSI — HPP per potong dari pembelian & BOM mengisi cutting (INV-F36)" \
           "python3 scripts/verify_hpp_potong_dan_bom_cutting.py"

  # ── INV-F37 (2026-08-23, sesi #32) — NILAI POTONGAN & POTONGAN YATIM ──────
  # Dua keluhan pemilik yang terbukti di data hidup:
  #  (1) master POTONGAN lahir `unit_cost: 0` dan baru diisi saat `complete`
  #      dengan cara MENIMPA memakai harga kain yang di-snapshot saat order
  #      DIBUAT ⇒ nilai persediaan bocor selama order berjalan, harga basi
  #      (POC mengukur selisih Rp41.379 pada satu order), dan HPP order kedua
  #      MENGHAPUS HPP order pertama walau stok potongan lama masih ada;
  #  (2) master potongan tertinggal YATIM. Penyebabnya dua: alur produk
  #      (`start` melahirkan master, `cancel` meninggalkannya) DAN alat ukur
  #      sendiri — gate INV-F24 dulu menghapus order+kain+dokumen tetapi
  #      mencari masternya dengan REGEX KODE yang tidak pernah cocok, sehingga
  #      satu master sampah menumpuk di Master Item pemilik setiap kali gate
  #      dijalankan. C12 gate ini memeriksa KEADAAN AKHIR (0 potongan yatim)
  #      sesudah bersih-bersih, jadi kebocoran alat ukur mana pun jadi MERAH.
  run_gate "UANG/STOK — Nilai potongan lahir saat dipotong & tak ada potongan yatim (INV-F37)" \
           "python3 scripts/verify_potongan_nilai_dan_yatim.py"

  # ── INV-F38 (2026-08-23, sesi #33) — BELANJA MINGGUAN · RIWAYAT HARGA · AMBANG ──
  # Tiga pekerjaan pemilik yang semuanya berakar pada satu pola: FITUR ADA TAPI
  # TIDAK BISA DIPAKAI.
  #  (1) Layar Ambang Stok punya tombol "Pakai semua usulan", tetapi usulannya
  #      HANYA lahir dari pemakaian 30 hari; terukur di data hidup **5 dari 335
  #      material** yang punya pemakaian ⇒ 330 material (98,5%) tidak punya jalan
  #      massal apa pun, dan ambang yang tersimpan tidak menyebut dasarnya.
  #  (2) `rahaza_material_cost_history` dipakai SEMUA jenis material (kain,
  #      aksesoris, dan nilai potongan sejak sesi #32), tetapi satu-satunya
  #      pembacanya adalah layar AKSESORIS — tanpa filter jenis ⇒ layar itu
  #      menampilkan riwayat KAIN, dan 335 barang lain tidak punya layar mana pun.
  #  (3) Alert stok hanya bilang "kurang n": tanpa satuan beli, tanpa harga, dan
  #      tanpa jembatan ke Permintaan Pengadaan ⇒ harus diketik ulang manual.
  # C15 memeriksa KEADAAN AKHIR (0 artefak uji tertinggal) — pola C12 INV-F37.
  run_gate "UANG/STOK — Belanja mingguan dari ambang, riwayat harga, ambang massal (INV-F38)" \
           "python3 scripts/verify_belanja_riwayat_ambang.py"

  # ── INV-F39 (2026-08-23, sesi #34) — BIAYA JAHIT → HPP BATCH → MARKETING ────
  # Diukur sebelum sesi ini: (1) `po_items.cmt_price_snapshot` dipakai tiga
  # pembaca (monitoring CMT, tagihan CMT, kalkulator HPP) tetapi SPK internal
  # selalu menulis 0 dan TIDAK ADA layar yang bisa mengisinya ⇒ HPP = biaya bahan
  # saja dan margin marketing terlihat lebih bagus dari kenyataan; (2) portal
  # kreator membaca koleksi katalog yang KOSONG dan kreator demo lahir tanpa
  # kredensial ⇒ pemilik tidak bisa login; (3) 22 jenis impor dipilih manual
  # tanpa petunjuk ⇒ berkas pesanan bisa masuk sebagai penjualan harian tanpa
  # ada yang tahu; (4) upah live host per-sesi mengarang gaji di luar payroll;
  # (5) periode anggaran 7 hari membuat budget/summary 500 (layar Rp 0 senyap).
  run_gate "UANG/DATA — Biaya jahit SPK, HPP batch FIFO, impor pintar, gaji host bulanan (INV-F39)" \
           "python3 scripts/verify_biaya_jahit_hpp_batch_impor_pintar.py"

  # ── INV-F40 (sesi #35) — KPI KONTEN PER KONTEN + RAPOR KREATOR MINGGUAN ─────
  # Diukur sebelum sesi ini: `POST /content-calendar/{id}/kpi` ada sejak F7.3
  # tetapi 0 layar memanggilnya ⇒ angka views/engagement/GMV konten hanya bisa
  # lahir dari penyemai demo; `/performance` tidak punya cara membaca KPI SATU
  # konten (satuan kerja yang dinilai); insentif dibaca per 3 bulan & performa
  # per bulan ⇒ kreator baru tahu tertinggal saat periodenya hampir habis.
  run_gate "DATA — KPI konten per konten/jenis/toko/KOL + rapor kreator mingguan (INV-F40)" \
           "python3 scripts/verify_kpi_konten_rapor_mingguan.py"

  # ── INV-F41 (sesi #36) — IMPOR MASTER DATA (migrasi data nyata) ─────────────
  # Migrasi adalah langkah yang tidak bisa diulang tanpa biaya: importir yang
  # menerima baris cacat tidak melahirkan error, melainkan MASTER HANTU, dan
  # seluruh HPP/stok/insentif setelahnya salah tanpa ada yang tahu. Gate ini
  # menahan: dry-run tidak menulis, baris cacat dilaporkan per baris, tidak ada
  # impor separuh, dan impor ulang tidak menduplikasi.
  run_gate "DATA — Impor master dari template Excel: dry-run, tolak cacat, idempoten (INV-F41)" \
           "python3 scripts/verify_impor_master_template.py"

  # ── INV-F42 (sesi #37) — PENCAIRAN MARKETPLACE DI PORTAL FINANCE ───────────
  # Diukur sebelum sesi ini: backend pencairan lengkap sejak F9 tetapi TIDAK ADA
  # satu pun layar yang bisa mencatatnya (layar Marketing sengaja baca-saja) ⇒
  # uang yang masuk dari Shopee/TikTok tidak punya pintu masuk ke buku besar.
  # Lebih mahal lagi: `POST`/`journal` hanya dijaga `require_auth`, dan jurnalnya
  # memakai peta COA GLOBAL padahal setiap toko sudah punya akun kas/pendapatan
  # sendiri — uang semua toko jatuh ke satu rekening tanpa satu pun galat.
  run_gate "UANG — Pencairan marketplace: form Finance, COA akun toko, selisih bernama (INV-F42)" \
           "python3 scripts/verify_pencairan_finance.py"

  # ── INV-F43 (sesi #37) — MARGIN KATALOG TIDAK PERNAH DIKARANG ─────────────
  # Diukur: 78 item katalog, 0 punya `margin_pct`, `hpp` terisi 10 item. Rumus
  # lama menghasilkan 100% saat HPP=0 dan 0% saat harga jual=0 — dua angka yang
  # terlihat sah padahal artinya "tidak diketahui". Marketing memakai kolom itu
  # untuk memutuskan diskon, jadi item yang untung-ruginya tidak diketahui justru
  # tampil sebagai yang paling aman didiskon.
  run_gate "UANG — Margin katalog: 0%/100% tidak dikarang saat HPP tak diketahui (INV-F43)" \
           "python3 scripts/verify_margin_katalog.py"

  # ── INV-F44 (sesi #38) — JURNAL COGS MEMAKAI BIAYA BATCH YANG NYATA ───────
  # Sesi #34 memasang FIFO keluar dan menyimpan `fg_cogs` di baris pengiriman,
  # tetapi jurnal COGS masih memakai snapshot HPP SPK ⇒ satu pengiriman punya
  # DUA angka biaya (gudang nyata vs buku besar perkiraan) dan laba per
  # pengiriman selalu salah tanpa satu pun galat.
  run_gate "UANG — COGS pengiriman memakai biaya batch FIFO yang benar-benar keluar (INV-F44)" \
           "python3 scripts/verify_cogs_fifo_jurnal.py"

  # ── INV-F45 (sesi #40) — IMPOR PINTAR PUNYA PINTU DI LAYAR ────────────────
  # Dua fitur yang SUDAH ada di backend ternyata tidak pernah bisa dipakai:
  #   · langkah 1 layar Impor Data menyaring jenis per KELOMPOK, tetapi tidak ada
  #     satu pun tempat yang mengisi kelompoknya ⇒ layar menjawab "0 dari 22
  #     jenis data" saat dibuka (satu-satunya jalan: mengetik kata kunci);
  #   · `POST /data-import/detect` (usulan jenis dari isi berkas, sesi #34) tidak
  #     dipanggil satu berkas frontend pun — fitur tanpa pintu = fitur yang tidak ada.
  # Ikut dijaga: pencairan yang jurnalnya sudah DI-VOID tidak boleh tetap terkunci
  # (pesannya menyuruh "void dulu", tetapi void tidak membuka apa pun ⇒ jalan buntu).
  run_gate "LAYAR/UANG — impor pintar punya pintu + pencairan void tidak mengunci (INV-F45)" \
           "python3 scripts/verify_impor_pintar_pintu_layar.py"

else
  for g in "state machine jurnal" "nomor dokumen kembar" "batas nilai AR/AP" \
           "RBAC/IDOR" "input jahat 4xx" "endpoint kritis" \
           "alur produksi/maklon/CMT" "R&D ukuran/SKU/HPP (INV-RND)" \
           "SSOT warna (INV-COLOR)" "R&D padankan ukuran + harga basi (INV-RND2)" \
           "Portal CMT Override (INV-CMTOV)" "Rekap Harian CMT (INV-REKAP)" \
           "Master Produk (INV-PRODUK)" "Katalog stok jual (INV-KATALOG)" \
           "Marketing lingkup toko + impor (INV-MKTSCOPE)" \
           "Marketing siklus + kunci periode (INV-MKTCYCLE)" \
           "Marketing impor KPI + assign toko + scorecard (INV-KPIIMPOR)" \
           "Marketing status pengiriman + pemulihan impor (INV-MKTFULFILL)" \
           "Marketing assign toko + ingat pemetaan + scorecard (INV-MKTOPS)" \
           "Marketing omzet bruto vs setelah retur (INV-RETUR)" \
           "Marketing lingkup toko per pemakai + jejak (INV-F6RBAC)" \
           "Marketing layar daftar bisa dipakai (INV-F10)" \
           "Marketing pratinjau impor per baris (INV-F11)" \
           "Marketing berkas masuk toko yang salah (INV-F12)" \
           "Dispatch buyer satu rumus sisa kirim (INV-F16)" \
           "PDF rapi tanpa tumpang tindih (INV-F17)" \
           "Kirim material CMT memotong stok (INV-F18)" \
           "Gudang: buat MI + Buat Barcode + menu mati (INV-F19)" \
           "Dashboard Marketing: pintu + angka resmi (INV-F20)" \
           "Nomor dokumen: mode auto/manual (INV-F21)" \
           "Gulungan kain lahir & wajib ditunjuk (INV-F22)" \
           "Surat jalan satu daftar + pintu lama (INV-F23)" \
           "Arus keluar Cutting berdokumen (INV-F24)" \
           "Setelan penomoran ditegakkan (INV-F25)" \
           "Template PDF tercetak & satu pintu (INV-F26)" \
           "Permak/dispatch lanjutan/aksesoris BOM (INV-F27)" \
           "Monitoring CMT potongan sesuai order (INV-F28)" \
           "Sinkronisasi Marketing ⇄ Gudang (INV-F29)" \
           "Identitas barang warna·ukuran·OPSI (INV-F30)" \
           "Retur pembeli → retur fisik → stok (INV-F31)" \
           "Tabel stok & kolom cetak dipilih (INV-F32)" \
           "Surat jalan CMT → DA (INV-F33)" \
           "Alert stok hidup (INV-F34)" \
           "Satuan gulungan & style master (INV-F35)" \
           "HPP per potong & BOM di cutting (INV-F36)" \
           "Nilai potongan & potongan yatim (INV-F37)" \
           "Belanja mingguan · riwayat harga · ambang massal (INV-F38)" \
           "Pencairan marketplace di Portal Finance (INV-F42)" \
           "Margin katalog tidak dikarang (INV-F43)" \
           "COGS pengiriman pakai biaya batch FIFO (INV-F44)" \
           "Impor pintar punya pintu di layar (INV-F45)"; do
    skip_gate "$g" "backend/auth belum siap"
  done
fi

# ══ 4. FITUR MATI DIAM-DIAM (statik, murah, terbukti menemukan bug produk) ═══
# Dua ini DIPERTAHANKAN karena rekam jejaknya nyata: `unreachable_code`
# menemukan handler export CSV payroll yang kehilangan dekorator (fitur mati),
# dan `fe_be_contract` menemukan 8 panggilan FE yang 404 senyap.
run_gate "FITUR MATI — handler tergabung / kode setelah return" \
         "python3 scripts/guardrails/verify_unreachable_code.py"
run_gate "FITUR MATI — panggilan FE ke endpoint yang tak ada" \
         "python3 scripts/preflight/verify_fe_be_contract.py --report-only"
run_gate "NAVIGASI — menu hantu / duplikat / kedalaman" \
         "python3 scripts/guardrails/check_nav_map.py"

# ── LAYAR UANG/STOK BISA DIPAKAI & DIBAWA (INV-F13) ──────────────────────────
# Sengaja DI SINI (bagian statik), BUKAN di blok `AUTH_READY`: penjaga ini
# membaca BERKAS layar, bukan HTTP. Kalau ditaruh di blok backend, ia akan
# di-`skip_gate` setiap kali backend mati — padahal justru saat itulah regresi
# layar paling mungkin lolos tanpa terlihat.
#
# Yang dijaga (pelajaran F10: dari 25 pintu Portal Marketing hanya 2 yang bisa
# diunduh; audit `_audit_ui_tables_v2.py` menemukan 78 modul KARTU-SAJA di luar
# Marketing) — untuk 4 layar paling mahal kalau salah, yaitu UANG karyawan
# (kasbon/pinjaman, klaim & perjalanan dinas) dan STOK (roll kain, surat jalan):
#   · TABEL NYATA ≥8 kolom + pengalih Tabel/Kartu yang DIINGAT + urut + halaman
#     + tombol unduh. Tanpa itu, "siapa yang masih punya sisa utang, urut dari
#     terbesar?" dijawab dengan menggulir kartu lalu MENGETIK ULANG angkanya ke
#     Excel — sumber salah-ketik paling umum, dan angkanya adalah utang karyawan;
#   · SATU PEMBUAT CSV (`ExportCsvButton`/`lib/csv.js`). Kalau tiap layar menulis
#     escaping-nya sendiri, salah satu akan lupa tanda kutip dan Excel membaca
#     "Rp 1.000" sebagai TANGGAL;
#   · YANG DIUNDUH = YANG TERLIHAT — baris CSV wajib dari daftar yang sudah
#     DISARING & DIURUTKAN layar. Berkas yang tidak sama dengan layar lebih
#     berbahaya daripada tidak ada berkas sama sekali;
#   · UKURAN KEMAJUAN JUJUR — audit dijalankan ULANG; jumlah layar KARTU-SAJA
#     tidak boleh BERTAMBAH (layar baru wajib langsung punya tabel & unduhan).
run_gate "LAYAR — UANG/STOK di luar Marketing bisa dipakai & dibawa (INV-F13)" \
         "python3 test_core_f13_layar_uang_bisa_dibawa.py"

# ── FORM WAJIB MEMAKAI MASTER, BUKAN KETIKAN (INV-F14) ───────────────────────
# Temuan PEMILIK (2026-08-14): layar Launching Produk meminta staf MENGETIK nama
# produk / bahan / model, padahal yang diluncurkan adalah produk DA sendiri yang
# sudah ada di `rahaza_models`. Yang membuatnya mahal (semuanya DIUKUR):
#   · `_auto_create_fg_from_launch()` melahirkan BARANG JADI dari teks itu ⇒
#     satu produk lahir dua kali di master stok (kode karangan, hpp = 0,
#     kategori literal "launch") ⇒ "stok produk ini berapa?" punya DUA jawaban,
#     dan semuanya terjadi tanpa satu pun galat;
#   · harga rencana tidak bisa dibandingkan dengan harga RESMI master maupun
#     harga katalog toko;
#   · ejaan = identitas ⇒ laporan per produk/bahan salah DIAM-DIAM;
#   · 8 dari 8 rencana yang ada tidak punya `model_id` sama sekali.
#
# Ditaruh di bagian STATIK (bukan blok `AUTH_READY`) karena inti penjaganya —
# audit SELURUH layar — tidak butuh HTTP. Bagian runtime-nya (server = satu
# penulis, FG kembar tidak bisa lahir) melewati dirinya sendiri dengan sopan
# kalau backend mati, jadi gate ini tidak pernah "hilang" saat backend down.
run_gate "DATA/UANG — Form wajib memakai Master, bukan ketikan (INV-F14)" \
         "python3 test_core_f14_form_pakai_master.py"

# ── KARTU PUNYA LATAR & TULISANNYA TERBACA (INV-F15) ─────────────────────────
# Laporan PEMILIK (2026-08-14): "beberapa page di portal marketing cardsnya
# masih belum terdesign dengan baik seperti lupa di kasih background cardsnya,
# lalu ada beberapa yang masih abu abu".
#
# Sesudah diukur, ketiga cacatnya punya satu sifat yang sama: TIDAK PERNAH
# menjadi galat, jadi build & lint tetap HIJAU sementara layarnya rusak.
#   · 23 kelas Tailwind RUSAK (`bg-foreground/[0.06]0` — angka nyasar sesudah
#     `]`) ⇒ Tailwind tidak menghasilkan CSS apa pun ⇒ elemen benar-benar tanpa
#     latar. Sisa find/replace massal (`bg-white/60` → …/[0.06]0);
#   · 56 teks `text-muted-foreground/50|60|70` di atas `bg-muted` ⇒ rasio
#     kontras 1.9–2.6 (lantai 3.0) di tema terang MAUPUN gelap — badge status
#     jadi bayangan abu-abu;
#   · 30 cadangan token `localStorage.getItem('auth_token')` padahal
#     `auth_token` TIDAK PERNAH ditulis ⇒ `Bearer null` diam-diam. Cadangan yang
#     mustahil bekerja lebih buruk daripada tidak ada cadangan: ia membuat orang
#     berhenti mencurigai token sebagai penyebab.
# Ditambah `PickingListModal` yang memakai variabel milik komponen INDUK
# (`accountFilter`) ⇒ ReferenceError = layar putih begitu modal dibuka.
run_gate "LAYAR — Kartu punya latar, tulisan terbaca, token tidak berbohong (INV-F15)" \
         "python3 test_core_f15_kartu_terbaca.py"

# ══ 5. SESI BISA DISERAHKAN (gate lint platform harus hidup) ═════════════════
run_gate "SERAH-TERIMA — mesin lint platform hidup (import validation + oxlint)" \
         "python3 scripts/guardrails/verify_platform_lint_engine.py --quiet"

# ══ 6. ALUR PRODUK HR (hanya dengan --full; butuh backend) ═══════════════════
if [ $FULL -eq 1 ]; then
  if [ $AUTH_READY -eq 1 ]; then
    run_gate "PRODUK — absen (selfie+geofence wajib)" "python3 scripts/verify_fase16_absen.py"
    sleep 10
    run_gate "PRODUK — cuti" "python3 scripts/verify_fase17_cuti.py"
    sleep 10
    run_gate "PRODUK — payslip karyawan" "python3 scripts/verify_fase18_payslip.py"
    sleep 10
    run_gate "PRODUK — alur lembur live (HRIS)" "python3 scripts/bughunt_hris_flow.py"
  else
    skip_gate "alur produk HR" "backend/auth belum siap"
  fi
fi

# ══ RECEIPT ══════════════════════════════════════════════════════════════════
ELAPSED=$(( $(date +%s) - START ))
{
  echo "# 🧾 GATE RECEIPT — CV. Dewi Aditya ERP"
  echo
  echo "> Dihasilkan \`scripts/gate.sh\`. JANGAN edit manual."
  echo "> \"Selesai\" hanya sah bila receipt HIJAU untuk cakupan yang TIDAK di-skip."
  echo
  echo "- **Waktu:** $TS  ·  **Durasi:** ${ELAPSED}s  ·  **Mode:** $([ $FULL -eq 1 ] && echo 'full' || echo 'cepat')"
  echo "- **Backend:** $([ $BACKEND_UP -eq 1 ] && echo RUNNING || echo DOWN) · **Auth:** $([ $AUTH_READY -eq 1 ] && echo READY || echo 'NOT READY')"
  echo
  echo "| Gate | Hasil |"
  echo "|------|-------|"
  for i in "${!NAMES[@]}"; do echo "| ${NAMES[$i]} | ${RESULTS[$i]} |"; done
  echo
  if [ $OVERALL -eq 0 ]; then
    echo "## ✅ VERDICT: HIJAU — boleh lanjut / klaim selesai (untuk cakupan non-skip)."
  else
    echo "## ❌ VERDICT: MERAH — ada gate gagal. JANGAN klaim selesai."
  fi
  echo
  echo "_SKIP bukan PASS. Jalankan ulang saat backend + auth hidup._"
} > "$RECEIPT"

echo -e "\n${CYAN}${BOLD}==============================================================${RST}"
for i in "${!NAMES[@]}"; do
  case "${RESULTS[$i]}" in
    PASS) echo -e "  ${GREEN}PASS${RST}  ${NAMES[$i]}" ;;
    FAIL) echo -e "  ${RED}FAIL${RST}  ${NAMES[$i]}" ;;
    *)    echo -e "  ${YEL}SKIP${RST}  ${NAMES[$i]}" ;;
  esac
done
echo -e "  ${BOLD}durasi ${ELAPSED}s · receipt: $RECEIPT${RST}"
[ $OVERALL -eq 0 ] && echo -e "  ${GREEN}${BOLD}VERDICT: HIJAU${RST}" || echo -e "  ${RED}${BOLD}VERDICT: MERAH${RST}"
exit $OVERALL
