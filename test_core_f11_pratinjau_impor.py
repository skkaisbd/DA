#!/usr/bin/env python3
"""test_core_f11_pratinjau_impor.py — CORE TEST **FASE 4**: pratinjau impor
**PER BARIS** ("apa yang akan berubah") + laporan hasil yang bisa diunduh.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN — DAN KENAPA JUSTRU ITU
═══════════════════════════════════════════════════════════════════════════════
Sebelum Fase 4, pratinjau impor bisa menjawab tiga hal: berapa baris terbaca,
berapa valid/peringatan/galat, dan berapa banyak yang SUDAH ADA (angka agregat +
5 contoh). Yang TIDAK bisa dijawab justru pertanyaan yang menentukan pilihan staf
di layar itu:

  · "kalau saya pilih **Perbarui yang lama**, nilai APA yang berubah — dari
     berapa menjadi berapa?"
  · "baris mana yang akan **dilewati**, mana yang **ditolak**, dan kenapa?"

Ini bukan soal kenyamanan. Mode "Perbarui yang lama" bisa mengubah **status
pesanan** (`paid → cancelled`); perubahan itu MELEPAS reservasi stok dan
menurunkan omzet bulan yang mungkin sudah dirapatkan. Satu-satunya cara melihat
akibatnya dulu adalah "commit dulu, kalau salah tekan Batalkan impor" — memakai
data sungguhan sebagai kelinci percobaan.

PENJAGA DI BERKAS INI
---------------------
* `A-*` **STATIK — pratinjau tidak boleh menulis.** Tidak ada `insert_*`,
  `update_*`, `delete_*`, maupun `apply_status(` di seluruh jalur pratinjau. Dan
  penghalang seluruh-commit (periode terkunci / periode iklan bertindih / omzet
  rincian live melebihi) harus hidup di SATU fungsi yang dipakai commit **dan**
  pratinjau — bukan disalin.
* `B-*` **RUNTIME — pratinjau = kenyataan.** Untuk setiap commit yang dijalankan
  uji ini, KEEMPAT angka pratinjau dibandingkan dengan hasil commit
  (`baru`↔`inserted`, `diperbarui`+`sebagian`↔`updated`, `dilewati`↔`skipped`,
  `ditolak`↔`rejected`). Ini penjaga terpenting: pratinjau yang boleh berbeda
  dari kenyataan lebih berbahaya daripada tidak punya pratinjau.
* `C-*` **NILAI LAMA → BARU benar-benar ada** untuk baris yang akan diperbarui
  (termasuk perubahan STATUS pesanan dari berkas Ekspor B), dan **alasan penolakan
  disebut** untuk baris yang nomornya belum pernah diimpor / statusnya mundur.
* `D-*` **PENGHALANG tampil di pratinjau**, dengan pesan yang sama seperti yang
  akan dipakai commit untuk menolak (423 periode terkunci).
* `E-*` **BISA DIUNDUH**: rencana impor (sebelum commit) dan hasil impor
  (sesudah commit, termasuk baris DITOLAK + alasannya) — keduanya CSV ber-BOM.

CATATAN KEBERSIHAN: uji ini hanya membuat sesi impor DEMO dan **membatalkannya
sendiri** lewat endpoint rollback resmi di akhir. Ia tidak pernah menghapus
dokumen yang bukan miliknya.

Pakai:  python3 /app/test_core_f11_pratinjau_impor.py
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
SRC = Path("/app/backend/routes/marketing_data_import.py")
SAMPLES = Path("/app/samples")
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []
SESSIONS_MADE: list = []


def ok(code: str, msg: str):
    RES.append((code, True, msg))
    print(f"  {G}✓{X} [{code}] {msg}")


def bad(code: str, msg: str):
    RES.append((code, False, msg))
    print(f"  {R}✗{X} [{code}] {msg}")


def check(code: str, cond: bool, msg: str):
    (ok if cond else bad)(code, msg)
    return cond


# ═══════════════════════════════════════════════════════════════════════════════
# [A] STATIK — pratinjau tidak menulis · penghalang tidak disalin
# ═══════════════════════════════════════════════════════════════════════════════
def _block(src: str, name: str) -> str:
    """Ambil satu blok def/async def dari kode (sampai def berikutnya di kolom 0)."""
    m = re.search(rf"^(async def|def) {re.escape(name)}\(", src, re.M)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r"^(@router|async def |def |class )", src[start + 10:], re.M)
    return src[start:start + 10 + nxt.start()] if nxt else src[start:]


def section_static():
    print(f"\n{B}[A] STATIK — pratinjau MEMBACA saja, penghalang satu sumber{X}")
    src = SRC.read_text()

    WRITE_PAT = re.compile(
        r"\.(insert_one|insert_many|update_one|update_many|delete_one|delete_many|"
        r"replace_one|bulk_write|find_one_and_update)\(|apply_status\(")
    plan_blocks = ["_plan_rows", "_plan_fulfillment_row", "_plan_context",
                   "plan", "plan_csv", "result_csv", "_commit_blockers",
                   "_diff_changes", "_new_row_changes", "_status_reject_reason",
                   # F12 (sesi #11) — pemeriksa "berkas milik toko lain" ikut
                   # dijaga di sini: ia membaca riwayat impor toko LAIN, dan versi
                   # pertamanya sempat MENULIS sidik isi berkas ke sesi orang lain
                   # (cache turunan). Membuka layar pratinjau tidak boleh pernah
                   # mengubah apa pun — kalau bisa, tidak ada yang berani membukanya.
                   "_shop_evidence"]
    dirty = []
    for name in plan_blocks:
        blk = _block(src, name)
        if not blk:
            bad("A-0", f"fungsi pratinjau `{name}` tidak ditemukan di {SRC.name}")
            return
        hits = WRITE_PAT.findall(blk)
        if hits:
            dirty.append(f"{name}: {sorted(set(h for h in hits if h))}")
    check("A-1", not dirty,
          "tidak ada penulisan DB / apply_status di seluruh jalur pratinjau"
          + (f" — TEMUAN: {'; '.join(dirty)}" if dirty else
             f" ({len(plan_blocks)} fungsi diperiksa)"))

    # Penghalang seluruh-commit HANYA boleh ditulis sekali (di `_commit_blockers`).
    for needle, label in (
            ("sudah punya laporan iklan untuk periode", "periode iklan bertindih"),
            ("menyentuh periode yang sudah DITUTUP", "periode terkunci"),
            ("Sesi live tujuan sudah tidak ada", "sesi live hilang")):
        n = src.count(needle)
        check("A-2", n == 1,
              f"pesan penghalang «{label}» ditulis {n}× (harus 1× — kalau disalin, "
              "pratinjau & commit bisa bercerita beda)")

    commit_blk = _block(src, "commit")
    check("A-3", "_commit_blockers(" in commit_blk,
          "commit() MEMAKAI `_commit_blockers()` (bukan salinan pemeriksaannya)")

    # Kosakata aksi pratinjau = kosakata `row_notes` commit ⇒ angkanya bisa
    # dibandingkan tanpa penerjemah (dan penjaga B-* di bawah bisa ada).
    plan_actions = {"baru", "diperbarui", "sebagian", "dilewati", "ditolak"}
    commit_actions = set(re.findall(r'"action": "([a-z ]+)"', commit_blk))
    unmapped = commit_actions - (plan_actions | {"disimpan", "sebagian disimpan"})
    check("A-4", not unmapped,
          f"setiap aksi commit punya padanan di pratinjau (aksi commit: "
          f"{sorted(commit_actions)})"
          + (f" — TAK BERPADANAN: {sorted(unmapped)}" if unmapped else ""))

    # Layar impor = wizard + panel rencananya (satu layar, dua berkas).
    fe_dir = Path("/app/frontend/src/components/erp/marketing")
    fe = ((fe_dir / "DataImportWizard.jsx").read_text()
          + (fe_dir / "ImportPlanPanel.jsx").read_text())
    check("A-5", "import-plan" in fe and "plan.csv" in fe,
          "layar impor memanggil pratinjau per baris + unduhan rencana")
    check("A-6", "import-plan-blockers" in fe,
          "layar impor menampilkan penghalang seluruh-commit SEBELUM tombol Simpan")
    wiz = (fe_dir / "DataImportWizard.jsx").read_text()
    check("A-7", "planInfo?.blockers" in wiz and "window.open(`" not in wiz,
          "tombol Simpan MATI saat ada penghalang, dan tidak ada unduhan "
          "`window.open` (tab baru tidak membawa token ⇒ 401, bukan berkas)")
    check("A-8", "import-result-csv" in wiz,
          "laporan HASIL impor (termasuk baris ditolak) bisa diunduh dari layar")

    # A-9 — JANJI LAYAR YANG MUDAH HILANG SAAT PANEL DIRAPIKAN.
    # Panel rencana tidak berguna kalau isinya cuma angka agregat: staf harus bisa
    # (a) melihat BARIS-nya di tabel, (b) menyempitkan ke satu golongan akibat
    # (terutama `ditolak`), (c) mencari satu nomor pesanan, dan (d) melewati
    # halaman. Empat-empatnya pernah hilang di modul lain saat "dirapikan"
    # (temuan F10), jadi di sini dijaga statik.
    panel = (fe_dir / "ImportPlanPanel.jsx").read_text()
    # Testid chip dibuat dinamis (`import-plan-filter-${a.key}`), jadi yang
    # diperiksa: templatenya ADA **dan** kelima golongan akibat ada di daftar
    # `ACTIONS` — termasuk `ditolak`, chip yang paling sering dibutuhkan staf.
    acts_declared = set(re.findall(r"key:\s*'([a-z]+)'", panel))
    missing_ui = [t for t in ("import-plan-table", "import-plan-filter-${a.key}",
                              "import-plan-filter-all", "import-plan-search",
                              "import-plan-next", "import-plan-csv")
                  if t not in panel]
    missing_act = {"baru", "diperbarui", "sebagian", "dilewati",
                   "ditolak"} - acts_declared
    check("A-9", not missing_ui and not missing_act,
          "panel rencana punya tabel baris + saring 5 akibat + cari + halaman + unduh"
          + (f" — HILANG: {missing_ui} {sorted(missing_act)}"
             if (missing_ui or missing_act) else ""))
    # Paginasi WAJIB memakai `total` dari server. Menghitung dari panjang SATU
    # halaman memberi "Halaman 1 dari 1" untuk berkas 5.000 baris (staf menyimpan
    # tanpa pernah melihat 4.975 baris sisanya).
    check("A-10", "pagination?.total" in panel
          and re.search(r"Math\.ceil\(\s*total\s*/", panel) is not None
          and re.search(r"Math\.ceil\(\s*rows\.length", panel) is None,
          "jumlah halaman dihitung dari `pagination.total` server, bukan panjang "
          "satu halaman")


# ═══════════════════════════════════════════════════════════════════════════════
# helper runtime
# ═══════════════════════════════════════════════════════════════════════════════
class Api:
    def __init__(self):
        r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
        r.raise_for_status()
        self.h = {"Authorization": f"Bearer {r.json()['token']}"}

    def get(self, path, **kw):
        return requests.get(f"{BASE}{path}", headers=self.h, timeout=90, **kw)

    def post(self, path, **kw):
        return requests.post(f"{BASE}{path}", headers=self.h, timeout=120, **kw)

    def upload(self, source_type: str, account_id: str, content: bytes, fname: str):
        r = requests.post(
            f"{BASE}/api/marketing/data-import/upload", headers=self.h, timeout=120,
            files={"file": (fname, content, "text/csv")},
            data={"source_type": source_type, "account_id": account_id})
        return r

    def plan(self, sid: str, mode="skip", **params):
        p = {"on_duplicate": mode}
        p.update(params)
        return self.get(f"/api/marketing/data-import/sessions/{sid}/plan", params=p)

    def commit(self, sid: str, mode="skip"):
        return self.post(f"/api/marketing/data-import/sessions/{sid}/commit",
                         json={"on_duplicate": mode})


def counts_of(plan: dict) -> dict:
    return plan.get("counts") or {}


def compare_plan_vs_commit(code: str, plan: dict, res: dict, what: str):
    c = counts_of(plan)
    pairs = [
        ("baru → inserted", c.get("baru", 0), res.get("inserted", 0)),
        ("diperbarui+sebagian → updated",
         c.get("diperbarui", 0) + c.get("sebagian", 0), res.get("updated", 0)),
        ("dilewati → skipped_duplicates", c.get("dilewati", 0),
         res.get("skipped_duplicates", 0)),
        ("ditolak → rejected", c.get("ditolak", 0), res.get("rejected", 0)),
    ]
    wrong = [f"{lbl}: pratinjau {a} ≠ hasil {b}" for lbl, a, b in pairs if a != b]
    check(code, not wrong,
          f"pratinjau = kenyataan untuk {what} "
          f"({', '.join(f'{lbl.split(chr(8594))[0].strip()}={a}' for lbl, a, _ in pairs)})"
          + (f" — SELISIH: {'; '.join(wrong)}" if wrong else ""))


def find_demo_account(api: Api) -> dict:
    r = api.get("/api/marketing/accounts", params={"limit": 200})
    rows = r.json() if isinstance(r.json(), list) else (r.json().get("accounts")
                                                       or r.json().get("data") or [])
    for a in rows:
        if a.get("account_code") == "SHOPEE-OFFICIAL":
            return a
    return rows[0] if rows else {}


# ═══════════════════════════════════════════════════════════════════════════════
# [B]/[C]/[D]/[E] RUNTIME
# ═══════════════════════════════════════════════════════════════════════════════
def section_runtime():
    print(f"\n{B}[B] RUNTIME — pratinjau per baris = kenyataan{X}")
    api = Api()
    acc = find_demo_account(api)
    if not acc:
        bad("B-0", "tidak ada toko marketing di sistem — jalankan bootstrap dulu")
        return api
    aid = acc["id"]
    print(f"  toko uji: {acc.get('account_name')} ({acc.get('account_code')})")

    # ── bersihkan jejak uji sebelumnya lewat ROLLBACK RESMI ──────────────────
    # Kenapa perlu: kalau uji ini pernah terputus di tengah (mis. pipa ditutup
    # `| head`), pesanan DEMO-nya tertinggal dan jalannya uji berikutnya berubah
    # ("4 baru" menjadi "4 dilewati") ⇒ MERAH yang bukan salah produk.
    hist = api.get("/api/marketing/data-import/history",
                   params={"page_size": 100}).json()
    stale = [s for s in (hist.get("history") or [])
             if (s.get("filename") or "").startswith("uji-plan-")]
    for s in stale:
        if s.get("status") == "committed":
            api.post(f"/api/marketing/data-import/sessions/{s['id']}/rollback")
        requests.delete(f"{BASE}/api/marketing/data-import/sessions/{s['id']}",
                        headers=api.h, timeout=30)
    if stale:
        print(f"  (bersih-bersih awal: {len(stale)} sesi uji lama dibatalkan)")

    A = (SAMPLES / "ekspor_A_pesanan_contoh.csv").read_bytes()
    Bfile = (SAMPLES / "ekspor_B_status_dikirim_contoh.csv").read_bytes()
    Cfile = (SAMPLES / "ekspor_C_batal_retur_contoh.csv").read_bytes()

    # ── B-1 unggah Ekspor A + pratinjau ─────────────────────────────────────
    up = api.upload("marketplace_orders", aid, A, "uji-plan-A.csv")
    if up.status_code != 200:
        bad("B-1", f"unggah Ekspor A gagal HTTP {up.status_code}: {up.text[:200]}")
        return api
    sid_a = up.json()["session"]["id"]
    SESSIONS_MADE.append(sid_a)
    ok("B-1", f"sesi impor Ekspor A dibuat ({sid_a[:8]})")

    from pymongo import MongoClient
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = mc[os.environ.get("DB_NAME", "test_database")]
    before = db.marketing_orders.count_documents({})

    p = api.plan(sid_a, "skip")
    if p.status_code != 200:
        bad("B-2", f"GET plan gagal HTTP {p.status_code}: {p.text[:300]}")
        return api
    plan_a = p.json()
    c = counts_of(plan_a)
    check("B-2", c.get("baru", 0) >= 4 and c.get("dilewati", 0) == 0,
          f"pratinjau Ekspor A: {c.get('baru')} baris BARU, {c.get('dilewati')} dilewati, "
          f"{c.get('ditolak')} ditolak")
    rows = plan_a.get("rows") or []
    with_changes = [r for r in rows if r.get("changes")]
    check("B-3", len(with_changes) >= 1 and any(
        ch["after"] not in ("", "—") for ch in with_changes[0]["changes"]),
        "baris BARU memperlihatkan nilai yang AKAN ditulis (kolom lama kosong)")
    after = db.marketing_orders.count_documents({})
    check("B-4", before == after,
          f"pratinjau TIDAK menulis apa pun ke marketing_orders ({before} → {after})")
    check("B-5", plan_a.get("blockers") == [],
          "tidak ada penghalang seluruh-commit untuk berkas ini")

    r = api.commit(sid_a, "skip")
    if r.status_code != 200:
        bad("B-6", f"commit Ekspor A gagal HTTP {r.status_code}: {r.text[:300]}")
        return api
    res_a = r.json()
    compare_plan_vs_commit("B-6", plan_a, res_a, "Ekspor A (semua baris baru)")

    # ── B-7 berkas yang SAMA diunggah lagi: dilewati vs diperbarui ───────────
    up2 = api.upload("marketplace_orders", aid, A, "uji-plan-A2.csv")
    sid_a2 = up2.json()["session"]["id"]
    SESSIONS_MADE.append(sid_a2)
    p_skip = api.plan(sid_a2, "skip").json()
    check("B-7", counts_of(p_skip).get("dilewati", 0) >= 4
          and counts_of(p_skip).get("baru", 0) == 0,
          f"berkas sama + mode Lewati ⇒ {counts_of(p_skip).get('dilewati')} baris "
          "DILEWATI (bukan baris kembar)")
    why_skip = " ".join(sum([r.get("why") or [] for r in p_skip.get("rows") or []], []))
    check("B-8", "sudah ada" in why_skip.lower(),
          "alasan dilewati disebut apa adanya («sudah ada (duplikat)»)")

    # berkas dengan angka DIUBAH ⇒ pratinjau harus menunjukkan lama → baru
    changed = A.decode().replace(
        "DEMO-A-1001,Perlu dikirim,SKU9001,DEMO-KAOS-M,Kaos Polos Premium M,2,180000,190000",
        "DEMO-A-1001,Perlu dikirim,SKU9001,DEMO-KAOS-M,Kaos Polos Premium M,2,180000,777000")
    up3 = api.upload("marketplace_orders", aid, changed.encode(), "uji-plan-A3.csv")
    sid_a3 = up3.json()["session"]["id"]
    SESSIONS_MADE.append(sid_a3)
    p_upd = api.plan(sid_a3, "update").json()
    upd_rows = [r for r in (p_upd.get("rows") or []) if r["action"] == "diperbarui"]
    money_change = None
    for r in upd_rows:
        for ch in r.get("changes") or []:
            if "777000" in str(ch.get("after")) or "777.000" in str(ch.get("after")):
                money_change = (r["ref"], ch)
    check("B-9", counts_of(p_upd).get("diperbarui", 0) >= 4,
          f"mode Perbarui ⇒ {counts_of(p_upd).get('diperbarui')} baris DIPERBARUI")
    check("B-10", money_change is not None,
          "nilai LAMA → BARU terlihat untuk angka yang berubah"
          + (f" (baris {money_change[0]}: {money_change[1]['label']} "
             f"{money_change[1]['before']} → {money_change[1]['after']})"
             if money_change else " — TIDAK ADA satu pun perubahan angka terlihat"))

    # B-12 — PERUBAHAN PALSU. Ditemukan lewat UJI LAYAR sesi #11: mode "Perbarui
    # yang lama" memajang `Waktu Pesanan Dibuat: 2026-08-05 10:15 → 2026-08-05
    # 10:15` untuk SETIAP baris. Sebabnya Mongo mengembalikan datetime NAIVE
    # sementara berkas menghasilkan datetime BER-ZONA (`aware == naive` selalu
    # False). Ini bukan cacat kosmetik: baris palsu memakan kuota `_DIFF_MAX`
    # (perubahan NYATA terdorong ke "+N field lain") dan membuat staf berhenti
    # mempercayai satu-satunya kolom yang jadi alasan panel ini ada.
    fake = [(r["ref"], ch) for r in (p_upd.get("rows") or [])
            for ch in (r.get("changes") or [])
            if str(ch.get("before")) == str(ch.get("after"))]
    check("B-12", not fake,
          "tidak ada perubahan PALSU (nilai lama = nilai baru) di daftar perubahan"
          + (f" — {len(fake)} TEMUAN, mis. {fake[0][0]}: {fake[0][1]['label']} "
             f"«{fake[0][1]['before']}» → «{fake[0][1]['after']}»" if fake else
             f" ({sum(len(r.get('changes') or []) for r in (p_upd.get('rows') or []))} "
             "perubahan diperiksa)"))

    # B-13 — baris yang MEMANG tidak berubah wajib mengatakannya. Angka
    # "diperbarui" yang tinggi tanpa satu pun perubahan mudah dibaca sebagai
    # "datanya berubah banyak"; commit memang tetap menulis penanda waktu, jadi
    # yang jujur adalah menyebutkannya.
    kosong = [r for r in (p_upd.get("rows") or [])
              if r["action"] == "diperbarui" and not r.get("changes")]
    beralasan = [r for r in kosong
                 if any("tidak ada nilai yang berubah" in w for w in (r.get("why") or []))]
    check("B-13", len(kosong) == len(beralasan),
          f"baris 'diperbarui' tanpa perubahan menjelaskan diri "
          f"({len(beralasan)}/{len(kosong)} baris)"
          + ("" if len(kosong) == len(beralasan)
             else f" — TANPA ALASAN: {[r['ref'] for r in kosong if r not in beralasan][:3]}"))
    res_upd = api.commit(sid_a3, "update")
    if res_upd.status_code == 200:
        compare_plan_vs_commit("B-11", p_upd, res_upd.json(),
                               "Ekspor A ulang (mode Perbarui yang lama)")
    else:
        bad("B-11", f"commit mode update gagal HTTP {res_upd.status_code}: "
                    f"{res_upd.text[:200]}")

    # ── [C] Ekspor B — status pesanan berubah & baris asing ditolak ──────────
    print(f"\n{B}[C] Ekspor B/C — perubahan STATUS & alasan penolakan{X}")
    upb = api.upload("marketplace_fulfillment", aid, Bfile, "uji-plan-B.csv")
    if upb.status_code != 200:
        bad("C-1", f"unggah Ekspor B gagal HTTP {upb.status_code}: {upb.text[:200]}")
    else:
        sid_b = upb.json()["session"]["id"]
        SESSIONS_MADE.append(sid_b)
        p_b = api.plan(sid_b, "skip").json()
        rows_b = p_b.get("rows") or []
        status_change = [(r["ref"], ch) for r in rows_b
                         for ch in (r.get("changes") or [])
                         if ch["field"] == "status"]
        check("C-1", len(status_change) >= 2,
              "pratinjau menyebut perubahan STATUS pesanan lama → baru"
              + (f" (contoh {status_change[0][0]}: {status_change[0][1]['before']} → "
                 f"{status_change[0][1]['after']})" if status_change else ""))
        rejected = [r for r in rows_b if r["action"] == "ditolak"]
        check("C-2", any("belum pernah diimpor" in " ".join(r["why"])
                         for r in rejected),
              "baris yang nomor pesanannya asing DITOLAK dengan jalan keluarnya"
              + (f" ({rejected[0]['ref']})" if rejected else " — tidak ada"))
        res_b = api.commit(sid_b, "skip")
        if res_b.status_code == 200:
            compare_plan_vs_commit("C-3", p_b, res_b.json(),
                                   "Ekspor B (memperbarui pesanan yang ada)")
        else:
            bad("C-3", f"commit Ekspor B gagal HTTP {res_b.status_code}: "
                       f"{res_b.text[:200]}")

    # Ekspor C (batal/retur) lalu Ekspor B untuk pesanan yang sudah batal ⇒
    # pratinjau HARUS meramalkan penolakan (status tidak boleh dihidupkan lagi).
    upc = api.upload("marketplace_fulfillment", aid, Cfile, "uji-plan-C.csv")
    if upc.status_code == 200:
        sid_c = upc.json()["session"]["id"]
        SESSIONS_MADE.append(sid_c)
        p_c = api.plan(sid_c, "skip").json()
        res_c = api.commit(sid_c, "skip")
        if res_c.status_code == 200:
            compare_plan_vs_commit("C-4", p_c, res_c.json(), "Ekspor C (batal/retur)")
        revive = ("Order SN,Order Status,Tracking ID,Shipping Provider Name,"
                  "Shipped Time,Delivered Time\n"
                  "DEMO-A-1003,Dikirim,JX5555555555,J&T Express,"
                  "10/08/2026 08:00:00,\n")
        upr = api.upload("marketplace_fulfillment", aid, revive.encode(),
                         "uji-plan-B-revive.csv")
        if upr.status_code == 200:
            sid_r = upr.json()["session"]["id"]
            SESSIONS_MADE.append(sid_r)
            p_r = api.plan(sid_r, "skip").json()
            why_r = " ".join(sum([r.get("why") or []
                                  for r in p_r.get("rows") or []], [])).lower()
            check("C-5", counts_of(p_r).get("ditolak", 0) == 1
                  and ("tidak bisa dihidupkan" in why_r or "memundurkan" in why_r),
                  "pesanan yang sudah BATAL diramalkan DITOLAK sebelum commit "
                  f"(alasan: {why_r[:90]}…)")
            res_r = api.commit(sid_r, "skip")
            if res_r.status_code == 200:
                compare_plan_vs_commit("C-6", p_r, res_r.json(),
                                       "Ekspor B yang mencoba menghidupkan pesanan batal")

    # ── [D] PENGHALANG seluruh commit tampil di pratinjau ───────────────────
    print(f"\n{B}[D] Penghalang seluruh-commit tampil SEBELUM tombol Simpan{X}")
    lock = api.post("/api/marketing/periods/lock",
                    json={"account_id": aid, "period": "2026-08", "action": "close",
                          "reason": "uji pratinjau impor (otomatis dibuka lagi)"})
    if lock.status_code != 200:
        bad("D-0", f"tidak bisa menutup periode untuk uji: HTTP {lock.status_code} "
                   f"{lock.text[:160]}")
    else:
        try:
            upl = api.upload("marketplace_orders", aid, A, "uji-plan-A-locked.csv")
            sid_l = upl.json()["session"]["id"]
            SESSIONS_MADE.append(sid_l)
            p_l = api.plan(sid_l, "skip").json()
            blk = p_l.get("blockers") or []
            check("D-1", any(x.get("code") == "periode_terkunci" for x in blk),
                  "pratinjau menyebut periode TERKUNCI sebelum Simpan ditekan"
                  + (f" — «{blk[0]['message'][:80]}…»" if blk else " — TIDAK ada"))
            res_l = api.commit(sid_l, "skip")
            check("D-2", res_l.status_code == 423,
                  f"commit memang ditolak 423 (dapat {res_l.status_code}) — jadi "
                  "pratinjau tidak memberi harapan palsu")
            if blk and res_l.status_code == 423:
                same = blk[0]["message"].strip() == \
                    str(res_l.json().get("detail") or "").strip()
                check("D-3", same,
                      "pesan penghalang di pratinjau SAMA PERSIS dengan pesan penolakan commit")
        finally:
            # Kosakata resmi endpoint ini: `close` / **`reopen`** (bukan "open").
            # Salah kata = periode TETAP TERKUNCI setelah uji ⇒ semua impor toko
            # itu ditolak 423 dan gate berikutnya merah tanpa sebab yang jelas.
            re_open = api.post(
                "/api/marketing/periods/lock",
                json={"account_id": aid, "period": "2026-08", "action": "reopen",
                      "reason": "selesai uji pratinjau impor"})
            check("D-4", re_open.status_code == 200
                  and not (re_open.json().get("lock") or {}).get("locked", True),
                  "periode uji DIBUKA kembali (uji tidak meninggalkan periode terkunci)")

    # ── [E] BISA DIUNDUH ────────────────────────────────────────────────────
    print(f"\n{B}[E] Rencana & hasil impor bisa DIUNDUH (CSV){X}")
    upe = api.upload("marketplace_orders", aid, A, "uji-plan-A-csv.csv")
    sid_e = upe.json()["session"]["id"]
    SESSIONS_MADE.append(sid_e)
    rp = api.get(f"/api/marketing/data-import/sessions/{sid_e}/plan.csv",
                 params={"on_duplicate": "update"})
    body = rp.text
    check("E-1", rp.status_code == 200 and body.startswith("\ufeff")
          and "Nilai lama" in body and "Nilai baru" in body,
          f"rencana impor bisa diunduh CSV ber-BOM dengan kolom lama/baru "
          f"(HTTP {rp.status_code}, {len(body)} char)")
    rows_csv = list(csv.reader(io.StringIO(body.lstrip("\ufeff"))))
    check("E-2", len(rows_csv) >= 5,
          f"CSV rencana memuat baris per perubahan ({len(rows_csv) - 1} baris data)")
    # E-2b — CSV yang hanya berisi JUDUL kolom "Nilai lama / Nilai baru" lolos E-1
    # tanpa membawa satu pun nilai. Yang dibawa staf ke rapat harus benar-benar
    # memuat perubahannya, bukan tabel kosong berjudul benar.
    try:
        hdr = rows_csv[0]
        i_old, i_new = hdr.index("Nilai lama"), hdr.index("Nilai baru")
        pairs = [(r[i_old], r[i_new]) for r in rows_csv[1:]
                 if len(r) > max(i_old, i_new)]
        real = [(a, b) for a, b in pairs
                if str(b).strip() not in ("", "—") and str(a).strip() != str(b).strip()]
    except (ValueError, IndexError):
        real = []
    check("E-2b", bool(real),
          "CSV rencana benar-benar memuat NILAI lama→baru, bukan hanya judul kolom"
          + (f" (contoh: «{real[0][0]}» → «{real[0][1]}»)" if real
             else " — TIDAK ADA satu pun pasangan nilai"))
    early = api.get(f"/api/marketing/data-import/sessions/{sid_e}/result.csv")
    check("E-3", early.status_code == 400,
          f"laporan HASIL menolak diunduh sebelum commit (HTTP {early.status_code}) "
          "— tidak ada laporan yang mengarang hasil")
    api.commit(sid_e, "skip")
    fin = api.get(f"/api/marketing/data-import/sessions/{sid_e}/result.csv")
    check("E-4", fin.status_code == 200 and "Alasan / catatan" in fin.text,
          f"laporan HASIL bisa diunduh sesudah commit (HTTP {fin.status_code})")
    rej = api.get(f"/api/marketing/data-import/sessions/{sid_e}/result.csv",
                  params={"only_rejected": "true"})
    check("E-5", rej.status_code == 200,
          "laporan HASIL bisa disaring hanya baris DITOLAK (untuk diperbaiki di berkas asli)")

    # ── [F] PENYARING & HALAMAN yang JUJUR ──────────────────────────────────
    # Berkas impor nyata bisa 5.000 baris. Panel rencana menjanjikan tiga hal
    # yang, kalau bohong, justru MEMBUAT staf salah memutuskan:
    #   · chip "N ditolak" bisa diklik ⇒ yang keluar HARUS hanya baris ditolak,
    #     dan jumlahnya sama dengan angka di chip (kalau `total` ikut tersaring
    #     tetapi chip tidak, staf mengira 3 dari 3 padahal 3 dari 300);
    #   · pencarian menyempitkan ke nomor pesanan yang dicari;
    #   · `total` adalah jumlah SELURUH baris yang cocok — bukan panjang satu
    #     halaman (cacat "Halaman 1 dari 1" yang ditemukan di modul lain, F10).
    print(f"\n{B}[F] Penyaring & halaman rencana JUJUR (berkas besar){X}")
    upf = api.upload("marketplace_orders", aid, A, "uji-plan-F-filter.csv")
    if upf.status_code != 200:
        bad("F-0", f"unggah berkas uji penyaring gagal HTTP {upf.status_code}")
    else:
        sid_f = upf.json()["session"]["id"]
        SESSIONS_MADE.append(sid_f)
        base = api.plan(sid_f, "skip").json()
        cbase = counts_of(base)
        n_skip = cbase.get("dilewati", 0)
        check("F-1", n_skip >= 4 and cbase.get("total", 0) == n_skip,
              f"berkas yang seluruh barisnya sudah ada ⇒ {n_skip} dilewati "
              f"(total {cbase.get('total')})")
        only = api.plan(sid_f, "skip", only="dilewati").json()
        acts = {r["action"] for r in (only.get("rows") or [])}
        check("F-2", acts == {"dilewati"}
              and (only.get("pagination") or {}).get("total") == n_skip,
              f"saring «dilewati» ⇒ hanya baris dilewati ({sorted(acts)}), "
              f"total {(only.get('pagination') or {}).get('total')} = chip {n_skip}")
        kosong = api.plan(sid_f, "skip", only="baru").json()
        check("F-3", (kosong.get("rows") or []) == []
              and (kosong.get("pagination") or {}).get("total") == 0
              and counts_of(kosong).get("dilewati", 0) == n_skip,
              "saring golongan yang KOSONG ⇒ 0 baris, tetapi angka chip TIDAK "
              "ikut mengecil (kalau ikut, staf kehilangan gambaran seluruh berkas)")
        ref0 = (base.get("rows") or [{}])[0].get("ref") or ""
        cari = api.plan(sid_f, "skip", q=ref0).json()
        check("F-4", ref0 and (cari.get("pagination") or {}).get("total") == 1
              and (cari.get("rows") or [{}])[0].get("ref") == ref0,
              f"pencarian «{ref0}» menyempitkan tepat ke barisnya "
              f"({(cari.get('pagination') or {}).get('total')} baris)")
        satu = api.plan(sid_f, "skip", page_size=1).json()
        check("F-5", len(satu.get("rows") or []) == 1
              and (satu.get("pagination") or {}).get("total") == n_skip,
              f"halaman 1 memuat 1 baris tetapi `total` tetap {n_skip} "
              "(bukan panjang satu halaman)")
        hal2 = api.plan(sid_f, "skip", page_size=1, page=2).json()
        r1 = (satu.get("rows") or [{}])[0].get("row")
        r2 = (hal2.get("rows") or [{}])[0].get("row")
        check("F-6", r1 is not None and r2 is not None and r1 != r2,
              f"halaman 2 memuat baris LAIN (baris {r1} → {r2})")
    return api


def cleanup(api: Api):
    print(f"\n{B}Bersih-bersih — membatalkan sesi impor uji lewat rollback resmi{X}")
    done = 0
    for sid in reversed(SESSIONS_MADE):
        try:
            r = api.post(f"/api/marketing/data-import/sessions/{sid}/rollback")
            if r.status_code == 200:
                done += 1
            requests.delete(f"{BASE}/api/marketing/data-import/sessions/{sid}",
                            headers=api.h, timeout=30)
        except Exception as e:  # noqa: BLE001
            print(f"  {Y}!{X} sesi {sid[:8]}: {e}")
    print(f"  {done}/{len(SESSIONS_MADE)} sesi uji dibatalkan & dibuang")


def main():
    print(f"{B}══ CORE TEST FASE 4 — PRATINJAU IMPOR PER BARIS ══{X}")
    section_static()
    api = None
    try:
        api = section_runtime()
    except Exception as e:  # noqa: BLE001
        bad("RUNTIME", f"gagal tak terduga: {type(e).__name__}: {e}")
    finally:
        if api:
            try:
                cleanup(api)
            except Exception as e:  # noqa: BLE001
                print(f"  {Y}! cleanup: {e}{X}")

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
