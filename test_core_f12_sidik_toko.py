#!/usr/bin/env python3
"""test_core_f12_sidik_toko.py — CORE TEST **FASE 2 (sesi #11)**: berkas ekspor
yang diunggah ke TOKO YANG SALAH harus tertangkap SEBELUM tersimpan.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN — DAN KENAPA JUSTRU ITU
═══════════════════════════════════════════════════════════════════════════════
Sebelum Fase 2 hanya ada dua penjaga toko, dan **keduanya cuma pada satu jenis
data** (`marketplace_orders`):

  · `platform_guard` — "berkas Shopee masuk toko TikTok" ⇒ ditolak;
  · `shop_guard`     — "gudang platform di berkas bukan gudang toko tujuan".

Yang MASIH terbuka justru kesalahan yang paling mudah terjadi setiap hari: memilih
toko yang salah dari daftar 12 toko yang namanya mirip (*Shopee Daluna* vs
*TikTok Daluna* vs *Shopee Moen* vs *TikTok Style by Moen*).

  · **Ekspor B/C** (`marketplace_fulfillment`) tidak punya kolom platform maupun
    gudang. Berkas toko A yang diunggah ke toko B menjawab *"3 baris ditolak:
    belum pernah diimpor"*. Kalimatnya BENAR tetapi menyembunyikan sebabnya, jadi
    staf mengira berkasnya rusak — atau (jauh lebih mahal) memilih jenis "Pesanan
    Marketplace" supaya "mau masuk" ⇒ pesanan HANTU tanpa item & tanpa omzet.
  · Untuk jenis yang tidak punya sidik gudang, berkas toko A **bisa MASUK** ke
    toko B: omzet/komplain/konten toko A tercatat di toko B, dan tidak ada satu
    pun layar yang membantah.

Fase 2 memakai **BUKTI, bukan dugaan** — dua-duanya fakta yang sudah tercatat:

  1. **Tanda pengenal GLOBAL** (`SourceType.identity`): nomor pesanan platform,
     nomor komplain, URL konten. Kalau nomornya sudah tercatat pada toko LAIN,
     berkas itu memang milik toko itu. Mayoritas baris (≥ setengah) ⇒ PENGHALANG;
     sebagian ⇒ PERINGATAN (berkas gabungan tidak boleh langsung dilarang).
  2. **Berkas dengan ISI yang sama persis pernah DISIMPAN ke toko lain**
     (`content_sha256`) — satu berkas ekspor tidak mungkin milik dua toko. Ini
     satu-satunya bukti yang tersedia untuk ekspor KPI/iklan yang isinya tidak
     membawa penanda toko apa pun.

PENJAGA DI BERKAS INI
---------------------
* `A-*` **STATIK** — setiap jenis data punya `identity` **atau** terdaftar di
  `NO_IDENTITY_REASON` beserta alasannya (pengecualian tanpa alasan = aturan yang
  hilang, dan penjaga yang memaksa SEMUA jenis punya identity akan MENUDUH SALAH
  untuk ekspor yang isinya memang tanpa penanda toko). Ditambah: jenis apa pun
  yang menulis ke `marketing_orders` WAJIB ber-identity `order_id`; pesan
  penghalang/peringatan ditulis SEKALI (satu sumber untuk pratinjau & commit);
  pratinjau F12 tidak menulis apa pun; layar menampilkan peringatan MENETAP dan
  peringatan TIDAK ikut mematikan tombol Simpan.
* `B-*` **RUNTIME — bukti nomor pesanan.** Berkas yang sudah tersimpan di toko A
  lalu diunggah ke toko B ⇒ penghalang yang MENYEBUT nama toko A + jumlahnya,
  commit ditolak **409 dengan pesan sama persis**, dan toko yang BENAR tidak ikut
  dituduh. Berkas CAMPURAN (minoritas milik toko lain) ⇒ peringatan, bukan
  larangan.
* `C-*` **Ekspor B/C** — penolakan tidak lagi berhenti di "belum pernah diimpor":
  penghalangnya menyebut toko pemilik nomor-nomor itu.
* `D-*` **PRATINJAU TIDAK MENULIS** (dibuktikan dengan menghitung dokumen).

CATATAN KEBERSIHAN: uji ini hanya membuat sesi impor DEMO pada dua toko **DEMO**
(`SHOPEE-OFFICIAL`, `SHOPEE-RESELLER`) dan membatalkannya sendiri lewat endpoint
rollback resmi di akhir. Ia tidak pernah menghapus dokumen yang bukan miliknya.

Pakai:  python3 /app/test_core_f12_sidik_toko.py
"""
from __future__ import annotations

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
SCHEMA = Path("/app/backend/core/marketing_import_schema.py")
FE_DIR = Path("/app/frontend/src/components/erp/marketing")
SAMPLES = Path("/app/samples")
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []
SESSIONS_MADE: list = []
MARK = "uji-f12-"


def ok(code: str, msg: str):
    RES.append((code, True, msg))
    print(f"  {G}✓{X} [{code}] {msg}")


def bad(code: str, msg: str):
    RES.append((code, False, msg))
    print(f"  {R}✗{X} [{code}] {msg}")


def check(code: str, cond: bool, msg: str):
    (ok if cond else bad)(code, msg)
    return cond


def _block(src: str, name: str) -> str:
    m = re.search(rf"^(async def|def) {re.escape(name)}\(", src, re.M)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r"^(@router|async def |def |class )", src[start + 10:], re.M)
    return src[start:start + 10 + nxt.start()] if nxt else src[start:]


# ═══════════════════════════════════════════════════════════════════════════════
# [A] STATIK
# ═══════════════════════════════════════════════════════════════════════════════
def section_static():
    print(f"\n{B}[A] STATIK — daftar beralasan · satu sumber pesan · pratinjau membaca saja{X}")
    from core.marketing_import_schema import SOURCE_TYPES, NO_IDENTITY_REASON

    # A-1 — setiap jenis: punya identity ATAU terdaftar beralasan.
    tanpa = [k for k, st in SOURCE_TYPES.items()
             if not st.identity and k not in NO_IDENTITY_REASON]
    check("A-1", not tanpa,
          f"setiap jenis data punya `identity` atau alasan tertulis "
          f"({sum(1 for st in SOURCE_TYPES.values() if st.identity)} ber-identity, "
          f"{len(NO_IDENTITY_REASON)} beralasan)"
          + (f" — TANPA KEDUANYA: {tanpa}" if tanpa else ""))

    # A-1b — alasan harus benar-benar menjelaskan (bukan "n/a").
    pendek = {k: v for k, v in NO_IDENTITY_REASON.items() if len(v.strip()) < 60}
    hantu = [k for k in NO_IDENTITY_REASON if k not in SOURCE_TYPES]
    check("A-1b", not pendek and not hantu,
          "setiap alasan panjangnya masuk akal & jenisnya benar-benar ada"
          + (f" — TERLALU PENDEK: {list(pendek)}" if pendek else "")
          + (f" — JENIS TAK ADA: {hantu}" if hantu else ""))

    # A-2 — jenis apa pun yang MENULIS pesanan wajib ber-identity `order_id`.
    # Kalau tidak, jenis baru bisa memasukkan pesanan toko lain tanpa satu pun bukti.
    salah = [k for k, st in SOURCE_TYPES.items()
             if st.collection == "marketing_orders" and st.identity != "order_id"]
    check("A-2", not salah,
          "semua jenis yang menulis ke `marketing_orders` ber-identity `order_id`"
          + (f" — TIDAK: {salah}" if salah else ""))

    # A-2b — pemeriksaan kepemilikan nomor pesanan HARUS di SSOT `marketing_orders`
    # (bukan di koleksi turunan retur/ulasan yang isinya tidak lengkap).
    keliru = [k for k, st in SOURCE_TYPES.items()
              if st.identity == "order_id"
              and (st.identity_collection or st.collection) != "marketing_orders"]
    check("A-2b", not keliru,
          "kepemilikan nomor pesanan diperiksa di SSOT `marketing_orders`"
          + (f" — TIDAK: {keliru}" if keliru else ""))

    src = SRC.read_text()

    # A-3 — pesan penghalang & peringatan ditulis SEKALI (dipakai pratinjau+commit).
    for code_name in ("berkas_milik_toko_lain", "sebagian_milik_toko_lain",
                      "berkas_sudah_masuk_toko_lain"):
        n = src.count(f'"{code_name}"')
        check("A-3", n == 1,
              f"kode «{code_name}» ditulis {n}× (harus 1× — kalau disalin, "
              "pratinjau & commit bisa bercerita beda)")

    # A-4 — pratinjau F12 tidak menulis apa pun.
    blk = _block(src, "_shop_evidence")
    if not blk:
        bad("A-4", "`_shop_evidence()` tidak ditemukan")
    else:
        hits = re.findall(
            r"\.(insert_one|insert_many|update_one|update_many|delete_one|"
            r"delete_many|replace_one|bulk_write|find_one_and_update)\(", blk)
        check("A-4", not hits,
              "`_shop_evidence()` HANYA membaca (membuka layar pratinjau tidak "
              "boleh mengubah apa pun)"
              + (f" — TEMUAN: {sorted(set(hits))}" if hits else ""))

    # A-5 — penghalang dipakai commit lewat SATU fungsi.
    check("A-5", "_shop_evidence(" in _block(src, "_commit_blockers"),
          "`_commit_blockers()` memakai `_shop_evidence()` ⇒ commit menolak dengan "
          "pesan yang sama seperti yang dibaca staf di pratinjau")

    # A-6 — sidik ISI berkas dihitung saat unggah.
    up = _block(src, "upload")
    check("A-6", "content_sha256" in up and "hashlib.sha256(raw)" in up,
          "sidik isi berkas (`content_sha256`) dihitung saat unggah")

    # A-7 — LAYAR: peringatan MENETAP dan TIDAK mematikan tombol Simpan.
    panel = (FE_DIR / "ImportPlanPanel.jsx").read_text()
    wiz = (FE_DIR / "DataImportWizard.jsx").read_text()
    check("A-7", "import-plan-warnings" in panel and "data?.warnings" in panel,
          "layar menampilkan panel peringatan MENETAP (bukan toast yang hilang)")
    check("A-8", "planInfo?.blockers" in wiz and "planInfo?.warnings" not in wiz,
          "tombol Simpan hanya dimatikan oleh PENGHALANG — peringatan tidak boleh "
          "ikut mematikan (staf yang justru sedang memperbaiki keadaan akan "
          "terkunci di luar)")


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
        return requests.post(
            f"{BASE}/api/marketing/data-import/upload", headers=self.h, timeout=120,
            files={"file": (fname, content, "text/csv")},
            data={"source_type": source_type, "account_id": account_id})

    def plan(self, sid: str, mode="skip", **params):
        p = {"on_duplicate": mode}
        p.update(params)
        return self.get(f"/api/marketing/data-import/sessions/{sid}/plan", params=p)

    def commit(self, sid: str, mode="skip"):
        return self.post(f"/api/marketing/data-import/sessions/{sid}/commit",
                         json={"on_duplicate": mode})


def find_accounts(api: Api) -> tuple:
    r = api.get("/api/marketing/accounts", params={"limit": 200})
    j = r.json()
    rows = j if isinstance(j, list) else (j.get("accounts") or j.get("data") or [])
    by = {a.get("account_code"): a for a in rows}
    return by.get("SHOPEE-OFFICIAL"), by.get("SHOPEE-RESELLER")


def blocker_codes(plan: dict) -> list:
    return [b.get("code") for b in (plan.get("blockers") or [])]


def warning_codes(plan: dict) -> list:
    return [w.get("code") for w in (plan.get("warnings") or [])]


def cleanup_stale(api: Api):
    hist = api.get("/api/marketing/data-import/history",
                   params={"page_size": 200}).json()
    stale = [s for s in (hist.get("history") or [])
             if (s.get("filename") or "").startswith(MARK)]
    for s in stale:
        if s.get("status") == "committed":
            api.post(f"/api/marketing/data-import/sessions/{s['id']}/rollback")
        requests.delete(f"{BASE}/api/marketing/data-import/sessions/{s['id']}",
                        headers=api.h, timeout=30)
    if stale:
        print(f"  (bersih-bersih awal: {len(stale)} sesi uji lama dibatalkan)")


# ═══════════════════════════════════════════════════════════════════════════════
# [B]/[C]/[D] RUNTIME
# ═══════════════════════════════════════════════════════════════════════════════
def section_runtime() -> Api:
    api = Api()
    acc_a, acc_b = find_accounts(api)
    if not acc_a or not acc_b:
        bad("B-0", "dua toko DEMO (SHOPEE-OFFICIAL & SHOPEE-RESELLER) tidak "
                   "ditemukan — jalankan scripts/bootstrap.sh dulu")
        return api
    print(f"\n{B}[B] RUNTIME — bukti nomor pesanan milik toko lain{X}")
    print(f"  toko A (pemilik berkas): {acc_a['account_name']} · "
          f"toko B (salah pilih): {acc_b['account_name']}")
    cleanup_stale(api)

    A = (SAMPLES / "ekspor_A_pesanan_contoh.csv").read_bytes()
    Bfile = (SAMPLES / "ekspor_B_status_dikirim_contoh.csv").read_bytes()

    from pymongo import MongoClient
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = mc[os.environ.get("DB_NAME", "test_database")]

    # ── B-1 berkas masuk ke toko A (keadaan awal yang wajar) ─────────────────
    up = api.upload("marketplace_orders", acc_a["id"], A, f"{MARK}A-tokoA.csv")
    if up.status_code != 200:
        bad("B-1", f"unggah ke toko A gagal HTTP {up.status_code}: {up.text[:200]}")
        return api
    sid_a = up.json()["session"]["id"]
    SESSIONS_MADE.append(sid_a)
    p_a = api.plan(sid_a, "skip").json()
    check("B-1", blocker_codes(p_a) == [] and warning_codes(p_a) == [],
          "berkas di toko yang BENAR: tidak ada penghalang & tidak ada tuduhan "
          f"(penghalang={blocker_codes(p_a)}, peringatan={warning_codes(p_a)})")
    r = api.commit(sid_a, "skip")
    if r.status_code != 200 or (r.json().get("inserted") or 0) < 4:
        bad("B-2", f"commit ke toko A gagal/kurang: HTTP {r.status_code} "
                   f"{str(r.text)[:200]}")
        return api
    ok("B-2", f"4 pesanan tersimpan di toko A ({r.json().get('inserted')} baris)")

    # ── B-3 berkas yang SAMA diunggah ke toko B ⇒ PENGHALANG beralasan ───────
    upb = api.upload("marketplace_orders", acc_b["id"], A, f"{MARK}A-tokoB.csv")
    if upb.status_code != 200:
        bad("B-3", f"unggah ke toko B gagal HTTP {upb.status_code}: {upb.text[:220]}")
        return api
    sid_b = upb.json()["session"]["id"]
    SESSIONS_MADE.append(sid_b)
    p_b = api.plan(sid_b, "skip").json()
    blk = [b for b in (p_b.get("blockers") or [])
           if b.get("code") == "berkas_milik_toko_lain"]
    check("B-3", bool(blk),
          "berkas toko A yang diunggah ke toko B DIHENTIKAN sebelum tersimpan"
          + (f" — «{blk[0]['message'][:110]}…»" if blk
             else f" — penghalang yang ada: {blocker_codes(p_b)}"))
    if blk:
        m = blk[0]["message"]
        check("B-4", acc_a["account_name"] in m and "4 dari 4" in m,
              "pesannya MENYEBUT nama toko pemilik & berapa dari berapa baris "
              f"(«…{acc_a['account_name']}…»)"
              + ("" if acc_a["account_name"] in m else f" — pesan: {m[:160]}"))
        check("B-5", ("Ganti toko" in m or "ganti toko" in m) and "Seller Center" in m,
              "pesannya menyebut JALAN KELUAR (ganti toko tujuan / ekspor ulang)")

    # ── B-6 peringatan "berkas identik pernah masuk toko lain" ───────────────
    warn = [w for w in (p_b.get("warnings") or [])
            if w.get("code") == "berkas_sudah_masuk_toko_lain"]
    check("B-6", bool(warn) and acc_a["account_name"] in (warn[0]["message"] if warn else ""),
          "peringatan kedua: berkas ber-ISI sama pernah disimpan ke toko lain, "
          "dengan nama toko + waktu + pelakunya"
          + (f" — «{warn[0]['message'][:110]}…»" if warn
             else f" — peringatan yang ada: {warning_codes(p_b)}"))

    # ── B-7 commit ke toko B ditolak 409 dengan PESAN SAMA PERSIS ────────────
    res = api.commit(sid_b, "skip")
    check("B-7", res.status_code == 409,
          f"commit ke toko B ditolak 409 (dapat {res.status_code}) — pratinjau "
          "tidak memberi harapan palsu")
    if blk and res.status_code == 409:
        same = blk[0]["message"].strip() == str(res.json().get("detail") or "").strip()
        check("B-8", same,
              "pesan penghalang di pratinjau SAMA PERSIS dengan penolakan commit")

    # ── B-9 toko yang BENAR tidak ikut dituduh ───────────────────────────────
    up_again = api.upload("marketplace_orders", acc_a["id"], A,
                          f"{MARK}A-tokoA-ulang.csv")
    if up_again.status_code == 200:
        sid_a2 = up_again.json()["session"]["id"]
        SESSIONS_MADE.append(sid_a2)
        p_a2 = api.plan(sid_a2, "skip").json()
        check("B-9", blocker_codes(p_a2) == []
              and "berkas_sudah_masuk_toko_lain" not in warning_codes(p_a2),
              "berkas yang sama diunggah lagi ke toko yang BENAR tidak dituduh "
              f"(penghalang={blocker_codes(p_a2)}, peringatan={warning_codes(p_a2)})")

    # ── B-10 berkas CAMPURAN (minoritas milik toko lain) ⇒ PERINGATAN saja ───
    # 2 nomor lama toko A + 3 nomor baru = 2/5 ⇒ di bawah setengah ⇒ tidak dilarang.
    head = A.decode().splitlines()[0]
    rows = A.decode().splitlines()[1:5]
    mixed = [head] + rows[:2]
    for i in range(3):
        cols = rows[0].split(",")
        cols[0] = f"UJI-F12-BARU-{i}"
        mixed.append(",".join(cols))
    upm = api.upload("marketplace_orders", acc_b["id"], "\n".join(mixed).encode(),
                     f"{MARK}A-campur.csv")
    if upm.status_code != 200:
        bad("B-10", f"unggah berkas campuran gagal HTTP {upm.status_code}: "
                    f"{upm.text[:200]}")
    else:
        sid_m = upm.json()["session"]["id"]
        SESSIONS_MADE.append(sid_m)
        p_m = api.plan(sid_m, "skip").json()
        check("B-10", "berkas_milik_toko_lain" not in blocker_codes(p_m)
              and "sebagian_milik_toko_lain" in warning_codes(p_m),
              "berkas CAMPURAN (minoritas milik toko lain) ⇒ PERINGATAN, bukan "
              f"larangan (penghalang={blocker_codes(p_m)}, "
              f"peringatan={warning_codes(p_m)})")
        wm = [w for w in (p_m.get("warnings") or [])
              if w.get("code") == "sebagian_milik_toko_lain"]
        check("B-11", bool(wm) and "2 dari 5" in wm[0]["message"],
              "peringatannya menyebut berapa dari berapa baris"
              + (f" — «{wm[0]['message'][:100]}…»" if wm else ""))
        rm = api.commit(sid_m, "skip")
        check("B-12", rm.status_code == 200,
              f"berkas campuran TETAP boleh disimpan (HTTP {rm.status_code}) — "
              "peringatan bukan larangan")

    # ── [C] Ekspor B/C: penolakan menyebut toko pemiliknya ──────────────────
    print(f"\n{B}[C] Ekspor B/C — penolakan tidak berhenti di «belum pernah diimpor»{X}")
    upf = api.upload("marketplace_fulfillment", acc_b["id"], Bfile,
                     f"{MARK}B-tokoB.csv")
    if upf.status_code != 200:
        bad("C-1", f"unggah Ekspor B ke toko B gagal HTTP {upf.status_code}: "
                   f"{upf.text[:200]}")
    else:
        sid_f = upf.json()["session"]["id"]
        SESSIONS_MADE.append(sid_f)
        p_f = api.plan(sid_f, "skip").json()
        bf = [b for b in (p_f.get("blockers") or [])
              if b.get("code") == "berkas_milik_toko_lain"]
        check("C-1", bool(bf) and acc_a["account_name"] in (bf[0]["message"] if bf else ""),
              "berkas status pengiriman toko A yang diunggah ke toko B menyebut "
              "toko pemilik nomor-nomornya"
              + (f" — «{bf[0]['message'][:110]}…»" if bf
                 else f" — penghalang: {blocker_codes(p_f)}"))
        rf = api.commit(sid_f, "skip")
        check("C-2", rf.status_code == 409,
              f"commit-nya ditolak 409 (dapat {rf.status_code}) — bukan «0 baris "
              "masuk» yang membingungkan")

    # ── [D] PRATINJAU TIDAK MENULIS ─────────────────────────────────────────
    print(f"\n{B}[D] Pratinjau F12 tidak menulis apa pun{X}")
    before_orders = db.marketing_orders.count_documents({})
    before_sess = db.marketing_data_import_sessions.count_documents({})
    before_hash = db.marketing_data_import_sessions.count_documents(
        {"content_sha256": {"$exists": True, "$nin": [None, ""]}})
    for _ in range(2):
        api.plan(sid_b, "skip")
        api.plan(sid_b, "update")
    check("D-1", db.marketing_orders.count_documents({}) == before_orders,
          f"membuka pratinjau 4× tidak menulis pesanan ({before_orders} tetap)")
    check("D-2", db.marketing_data_import_sessions.count_documents({}) == before_sess
          and db.marketing_data_import_sessions.count_documents(
              {"content_sha256": {"$exists": True, "$nin": [None, ""]}}) == before_hash,
          "pratinjau tidak menyentuh sesi impor milik toko lain (tidak ada cache "
          "sidik yang ditulis diam-diam)")
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
    print(f"{B}══ CORE TEST FASE 2 — SIDIK TOKO: BERKAS MILIK TOKO LAIN ══{X}")
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
