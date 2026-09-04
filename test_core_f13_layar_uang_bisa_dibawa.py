#!/usr/bin/env python3
"""test_core_f13_layar_uang_bisa_dibawa.py — CORE TEST **FASE 3 (sesi #11)**:
layar UANG & STOK di luar Marketing harus bisa DIPAKAI — tabel nyata, urutan,
penyempitan, halaman, dan **unduhan**.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN — DAN KENAPA JUSTRU ITU
═══════════════════════════════════════════════════════════════════════════════
F10 (sesi #10) mengukur 25 pintu Portal Marketing dan menemukan hanya **2** yang
bisa diunduh. Sesi ini mengukur hal yang sama di LUAR Marketing lewat
`scripts/_audit_ui_tables_v2.py`: **78 modul KARTU-SAJA** dan **133 tabel tanpa
pengalih**. Menutup semuanya sekaligus bukan pekerjaan satu sesi, jadi yang
dikerjakan lebih dulu adalah layar yang kalau salah **paling mahal**: UANG
karyawan (kasbon/pinjaman, klaim & perjalanan dinas) dan STOK (roll kain, surat
jalan).

Kenapa "tidak bisa diunduh" itu cacat, bukan selera:
  · Kasbon: pertanyaan pertama Keuangan adalah *"siapa yang masih punya sisa,
    urut dari terbesar?"*. Tanpa tabel & urutan, jawabannya diperoleh dengan
    menggulir kartu lalu **MENGETIK ULANG** angkanya ke Excel — sumber salah-ketik
    paling umum, dan angkanya adalah **utang karyawan**.
  · Inbox klaim: dulu tidak punya kotak pencarian **sama sekali**; "cari klaim Pak
    Budi" berarti mencari dengan mata, dan "total yang menunggu dibayar" harus
    dijumlah kartu per kartu.
  · Roll kain: SEMUA roll dirender sekaligus sebagai kartu 3 kolom. Untuk gudang
    ratusan roll, "roll mana yang hampir habis" tidak terjawab.
  · Surat jalan: PDF hanya bisa per SATU surat jalan, jadi rekap kiriman mingguan
    tidak bisa dibawa ke mana pun.

PENJAGA DI BERKAS INI (semuanya STATIK — layar tidak butuh backend untuk dijaga)
-------------------------------------------------------------------------------
* `A-*` setiap layar dalam cakupan punya: **tabel nyata** (≥8 kolom — tabel 3
  kolom untuk dokumen ber-15 field adalah "informasi tidak lengkap" yang sama
  saja dengan kartu), **pengalih Tabel/Kartu** yang diingat antar kunjungan,
  **pengurutan per kolom**, **paginasi**, dan **tombol unduh**.
* `B-*` **SATU pembuat CSV.** Layar dalam cakupan TIDAK boleh membuat CSV/Blob
  sendiri — wajib lewat `ExportCsvButton`/`lib/csv.js` (escaping + BOM Excel di
  satu tempat). Kalau tiap layar menulis escaping-nya sendiri, salah satu akan
  lupa tanda kutip dan Excel akan membaca "Rp 1.000" sebagai tanggal.
* `C-*` **Yang diunduh = yang TERLIHAT.** Baris CSV wajib dibangun dari daftar
  yang sudah DISARING & DIURUTKAN layar, bukan dari daftar mentah hasil fetch.
  Berkas yang tidak sama dengan layar lebih berbahaya daripada tidak ada berkas.
* `D-*` **Ukuran kemajuan yang jujur.** Audit `_audit_ui_tables_v2.py` dijalankan
  ulang: keempat layar dalam cakupan TIDAK boleh lagi muncul sebagai KARTU-SAJA,
  dan jumlah KARTU-SAJA keseluruhan tidak boleh BERTAMBAH (anti-kemunduran).

Pakai:  python3 /app/test_core_f13_layar_uang_bisa_dibawa.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ERP = Path("/app/frontend/src/components/erp")
AUDIT_JSON = Path("/app/memory/AUDIT_UI_TABLES_V2.json")
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []

# Cakupan Fase 3. `prefix` = awalan data-testid yang dipakai layar itu.
# `csv_from` = nama variabel daftar YANG TERLIHAT (sesudah saring+urut) yang
# WAJIB menjadi sumber baris CSV.
SCOPE = {
    "FinanceKasbonModule.jsx": {
        "why": "UANG — kasbon & pinjaman karyawan (sisa utang per orang)",
        "prefix": "kasbon", "csv_from": "rows",
    },
    "EmployeeExpenseApprovalModule.jsx": {
        "why": "UANG — inbox persetujuan klaim biaya & perjalanan dinas",
        "prefix": "expense", "csv_from": "rows",
    },
    "WMSFabricRollsModule.jsx": {
        "why": "STOK — roll kain (sisa panjang/berat per roll)",
        "prefix": "rolls", "csv_from": "sortedRolls",
    },
    "WMSDeliveryNotesModule.jsx": {
        "why": "STOK — surat jalan (barang keluar gudang)",
        "prefix": "sj", "csv_from": "filteredNotes",
    },
    # ── FASE B (sesi #12) — 5 layar UANG/STOK berikutnya ─────────────────────
    # Dipilih dengan satu pertanyaan: kalau layar ini salah, berapa mahalnya?
    "HRKasbonModule.jsx": {
        "why": "UANG — antrian persetujuan kasbon (yang disetujui = potongan gaji)",
        "prefix": "hrkasbon", "csv_from": "rows",
    },
    "KasbonStaffModule.jsx": {
        "why": "UANG — riwayat kasbon milik karyawan sendiri (bukti yang sering diminta)",
        "prefix": "kasbonstaff", "csv_from": "rows",
    },
    "ReceivingModule.jsx": {
        "why": "STOK — penerimaan barang: PINTU MASUK seluruh stok + qty ditolak (dasar klaim ke supplier)",
        "prefix": "receiving", "csv_from": "rows",
    },
    "ProcurementRequestModule.jsx": {
        "why": "UANG — permintaan pengadaan = komitmen belanja; urutan nilai dikerjakan SERVER",
        "prefix": "pr", "csv_from": "prRows",
    },
    "AccessoriesDashboard.jsx": {
        "why": "STOK+UANG — nilai stok aksesoris & item yang BELUM dinilai (masuk laporan keuangan)",
        "prefix": "acc", "csv_from": "rows",
    },
}


def ok(code: str, msg: str):
    RES.append((code, True, msg))
    print(f"  {G}✓{X} [{code}] {msg}")


def bad(code: str, msg: str):
    RES.append((code, False, msg))
    print(f"  {R}✗{X} [{code}] {msg}")


def check(code: str, cond: bool, msg: str):
    (ok if cond else bad)(code, msg)
    return cond


def _count_columns(src: str, anchor: str = "") -> int:
    """Jumlah kolom NYATA sebuah tabel — bukan jumlah token `<th` di kode.

    Penjaga versi pertama menghitung `<th` dan langsung MENUDUH SALAH: kolom di
    layar-layar ini dihasilkan dari daftar `[['key','Label'], …].map(…)`, jadi
    tabel 11 kolom hanya menuliskan DUA `<th` di kode. Pelajaran yang sama seperti
    sesi #10: penjaga yang menuduh salah membuat agen berikutnya "memperbaiki" hal
    yang sudah benar. Jadi yang dihitung: pasangan `['key', 'Label']` di dalam
    `<thead>` + `<th` yang ditulis apa adanya di luar `.map()`.

    ⚠️ PRESISI KEDUA (2026-08-17, sesi #17 — penjaga MENUDUH SALAH lagi):
    dulu fungsi ini mengambil `<thead>` PERTAMA di berkas. Itu benar sampai Fase
    H-5/H-7 MENAMBAH tabel baru DI ATAS tabel utama pada dua layar:
    `WMSFabricRollsModule` (tab "Penerimaan tanpa roll") dan
    `WMSDeliveryNotesModule` (tab "Semua Sumber"). Sejak itu penjaga mengukur
    tabel yang SALAH dan melaporkan "1 kolom" untuk tabel yang sesungguhnya
    ber-11 kolom ⇒ INV-F13 merah tanpa satu pun cacat produk. Sekarang
    pencarian DIANCAR ke tabel yang memang dimaksud (`data-testid="<prefix>-table"`),
    sehingga menambah tabel lain di layar yang sama tidak lagi membuat penjaga
    ini berbohong.
    """
    start = 0
    if anchor:
        i = src.find(anchor)
        if i == -1:
            return 0
        start = i
    m = re.search(r"<thead\b.*?</thead>", src[start:], re.S)
    if not m:
        return 0
    head = m.group(0)
    dari_daftar = len(re.findall(r"\['[A-Za-z_]+',\s*'", head))
    literal = len(re.findall(r"<th\b", head))
    # `<th` pembungkus di dalam `.map()` sudah terwakili oleh pasangan di daftar;
    # kurangi satu supaya tidak dihitung dua kali.
    return dari_daftar + max(0, literal - (1 if dari_daftar else 0))


def section_layar():
    print(f"\n{B}[A] Setiap layar UANG/STOK dalam cakupan bisa DIPAKAI{X}")
    for fname, meta in SCOPE.items():
        p = ERP / fname
        if not p.exists():
            bad("A-0", f"{fname} tidak ada")
            continue
        src = p.read_text()
        pre = meta["prefix"]
        print(f"  {B}{fname}{X} — {meta['why']}")

        th = _count_columns(src, anchor=f'data-testid="{pre}-table"')
        check(f"A-1·{pre}", f'data-testid="{pre}-table"' in src and th >= 8,
              f"tabel nyata dengan {th} kolom (≥8: dokumen ber-belasan field tidak "
              "boleh diringkas jadi 3 kolom)")
        check(f"A-2·{pre}",
              f'data-testid="{pre}-view-table"' in src
              and f'data-testid="{pre}-view-grid"' in src,
              "pengalih Tabel/Kartu ada (kartu tetap berguna untuk sekali-lihat)")
        check(f"A-3·{pre}", "localStorage.setItem(" in src and "_VIEW_KEY" in src,
              "pilihan tampilan DIINGAT antar kunjungan (staf tidak perlu "
              "mengklik ulang tiap membuka layar)")
        check(f"A-4·{pre}", f'data-testid={{`{pre}-sort-' in src
              or f'data-testid="{pre}-sort-' in src,
              "kolom bisa diurutkan (pertanyaan 'yang terbesar/paling lama' "
              "tidak boleh butuh mata)")
        check(f"A-5·{pre}", "PaginationLite" in src,
              "paginasi ada (daftar panjang tidak dirender sekaligus)")
        check(f"A-6·{pre}", f'testId="{pre}-export-csv"' in src,
              "tombol unduh ada (angka yang tidak bisa dibawa keluar = diketik ulang)")


def section_satu_pembuat_csv():
    print(f"\n{B}[B] SATU pembuat CSV — layar tidak boleh membuat CSV sendiri{X}")
    for fname in SCOPE:
        src = (ERP / fname).read_text()
        pre = SCOPE[fname]["prefix"]
        check(f"B-1·{pre}",
              "ExportCsvButton" in src and "new Blob(" not in src,
              "memakai `ExportCsvButton` (escaping + BOM Excel di `lib/csv.js`), "
              "tidak membuat Blob CSV sendiri")
    # lib/csv.js tetap SATU-SATUNYA tempat escaping CSV frontend hidup.
    csv_lib = Path("/app/frontend/src/lib/csv.js").read_text()
    check("B-2", "\\uFEFF" in csv_lib and 'replace(/"/g, \'""\')' in csv_lib,
          "`lib/csv.js` tetap memasang BOM Excel + escaping tanda kutip")


def section_yang_diunduh_yang_terlihat():
    print(f"\n{B}[C] Yang diunduh = yang TERLIHAT (bukan daftar mentah){X}")
    for fname, meta in SCOPE.items():
        src = (ERP / fname).read_text()
        pre, want = meta["prefix"], meta["csv_from"]
        m = re.search(r"const csvRows = (\w+)", src)
        check(f"C-1·{pre}", bool(m) and m.group(1) == want,
              f"baris CSV dibangun dari `{want}` (daftar yang sudah disaring & "
              f"diurutkan layar)"
              + (f" — TERNYATA dari `{m.group(1)}`" if m and m.group(1) != want
                 else "" if m else " — `csvRows` tidak ditemukan"))
        check(f"C-2·{pre}", "rows={csvRows}" in src,
              "tombol unduh menerima baris itu apa adanya (tanpa kueri ulang)")


def section_ukuran_jujur():
    print(f"\n{B}[D] Ukuran kemajuan yang jujur (audit dijalankan ulang){X}")
    # Ambang = jumlah KARTU-SAJA sesudah Fase 3 + Fase B (sesi #12).
    # 78 (sebelum Fase 3) → 74 (4 layar F13) → 69 (5 layar Fase B).
    # Angka ini SENGAJA diketatkan setiap kali layar ditutup: kalau dibiarkan
    # longgar, layar baru yang lahir tanpa tabel & unduhan akan lolos diam-diam
    # dan "kemajuan" hanya berarti tidak memburuk.
    BASELINE_CARD_ONLY = 69
    try:
        subprocess.run([sys.executable, "/app/scripts/_audit_ui_tables_v2.py"],
                       capture_output=True, timeout=300, check=False)
        data = json.loads(AUDIT_JSON.read_text())
    except Exception as e:  # noqa: BLE001
        bad("D-0", f"tidak bisa menjalankan/ membaca audit UI: {e}")
        return
    card_only = data.get("card_only") or []
    names = {c.get("file") or c.get("name") or c for c in card_only} \
        if card_only and isinstance(card_only[0], dict) else set(card_only)
    masih = sorted(n for n in names if Path(str(n)).name in SCOPE)
    check("D-1", not masih,
          f"keempat layar dalam cakupan TIDAK lagi terhitung KARTU-SAJA "
          f"(total KARTU-SAJA sekarang: {len(names)})"
          + (f" — MASIH: {masih}" if masih else ""))
    check("D-2", len(names) <= BASELINE_CARD_ONLY,
          f"jumlah layar KARTU-SAJA tidak bertambah ({len(names)} ≤ "
          f"{BASELINE_CARD_ONLY}) — layar baru wajib langsung punya tabel & unduhan")


def main():
    print(f"{B}══ CORE TEST FASE 3 — LAYAR UANG/STOK BISA DIPAKAI & DIBAWA ══{X}")
    section_layar()
    section_satu_pembuat_csv()
    section_yang_diunduh_yang_terlihat()
    section_ukuran_jujur()

    passed = sum(1 for _, p, _ in RES if p)
    total = len(RES)
    print(f"\n{B}{'═' * 70}{X}")
    for code, p, msg in RES:
        if not p:
            print(f"  {R}GAGAL{X} [{code}] {msg}")
    print(f"{B}HASIL: {passed}/{total} penjaga LULUS{X}")
    print(f"{'  ' + G + 'HIJAU' + X if passed == total else '  ' + R + 'MERAH' + X}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
