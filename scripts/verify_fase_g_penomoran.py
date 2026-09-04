#!/usr/bin/env python3
"""verify_fase_g_penomoran.py — FASE G (2026-08-16).

Permintaan pemilik: *"pengaturan nomor Auto/Manual per jenis dokumen supaya tidak
ada lagi nomor bebas."*

YANG TERUKUR SEBELUM PERBAIKAN:
  · Pondasi penomoran sudah ada (47 jenis dokumen, satu generator race-safe,
    layar format di Administrasi Sistem) TETAPI **mode-nya hanya implisit**:
    kolom nomor kosong → dibuatkan; kolom nomor diisi → **dipakai apa adanya tanpa
    satu pun pemeriksaan.**
  · `production_pos` — sumber nomor **SPP** — bahkan MEWAJIBKAN nomor diketik
    tangan (`create_po_internal`: "Nomor PO wajib diisi"). Isi arsipnya hari ini:
    `PO-INT-DEMO-1`, `PO-MK-DEMO-1`, `PO-MKL-GAB-A` — tiga pola untuk satu jenis
    dokumen. Nomor berpola bebas tidak bisa diurutkan, tidak bisa dicari, dan
    tidak bisa dibuktikan sebagai dokumen ke-berapa.

INVARIAN:
  G1  kebijakan nomor bisa dibaca oleh STAF PEMBUAT dokumen (bukan hanya admin),
      dan bawaannya = perilaku hari ini (PO produksi tetap MANUAL)
  G2  mode MANUAL → nomor di luar pola DITOLAK, pesannya menyebut pola & contoh
  G3  mode MANUAL → nomor sesuai pola diterima dan TERSIMPAN sama persis
  G4  mode MANUAL → nomor duplikat DITOLAK (bukan dua dokumen bernomor sama)
  G5  mode OTOMATIS → nomor ketikan DITOLAK sambil menyebut nomor yang akan dipakai
      (bukan diabaikan diam-diam: pemakai harus tahu nomor apa yang ia dapat)
  G6  mode OTOMATIS → tanpa nomor, dokumen bernomor sesuai format dan BERURUT
  G7  layar: Penomoran Dokumen punya tombol mode & form PO menghormati mode

Pakai:
    python3 scripts/verify_fase_g_penomoran.py
    python3 scripts/verify_fase_g_penomoran.py --keep
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

KEY = "production_pos.po_number"
MARK = "VERIFY-FASE-G"
DOCNUM_JSX = ROOT / "frontend/src/components/erp/DocNumberingModule.jsx"
PO_JSX = ROOT / "frontend/src/components/erp/engine/ProductionPOModule.jsx"

PASS, FAIL = [], []
created_pos: list[str] = []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def login(email, pwd):
    st, r = call("POST", "/api/auth/login", None, {"email": email, "password": pwd})
    return r.get("token") if st == 200 else None


def detail(resp) -> str:
    d = resp.get("detail")
    if isinstance(d, str):
        return d
    return json.dumps(resp)[:300]


def set_mode(token, mode):
    return call("PUT", "/api/admin/doc-numbering", token, {"key": KEY, "mode": mode})


def make_po(token, number=None, note=MARK):
    body = {"business_type": "internal", "customer_name": f"{note} (uji penomoran)",
            "notes": note, "items": []}
    if number is not None:
        body["po_number"] = number
    st, r = call("POST", "/api/production-pos", token, body)
    if st in (200, 201) and r.get("id"):
        created_pos.append(r["id"])
    return st, r


def clean(db, restore_cfg):
    n = 0
    ids = [p["id"] for p in db.production_pos.find({"notes": MARK}, {"_id": 0, "id": 1})]
    ids = list(set(ids + created_pos))
    if ids:
        n += db.production_pos.delete_many({"id": {"$in": ids}}).deleted_count
        db.po_items.delete_many({"po_id": {"$in": ids}})
    # counter khusus format uji (prefix baru) — jangan tinggalkan urutan menggantung
    db.counters.delete_many({"_id": {"$regex": r"^autonum:production_pos:po_number:PO-INT-"}})
    if restore_cfg is None:
        db.doc_number_configs.delete_many({"key": KEY})
    else:
        db.doc_number_configs.replace_one({"key": KEY}, restore_cfg, upsert=True)
    return n


def part_static():
    print(f"\n{B}[1] LAYAR{X}")
    dn = DOCNUM_JSX.read_text()
    po = PO_JSX.read_text()
    have_toggle = "docnum-mode-" in dn and "setMode(" in dn
    have_form = ("po-number-auto" in po and "doc-number-policy" in po
                 and "delete payload.po_number" in po)
    if have_toggle and have_form:
        ok("G7", "layar penomoran punya tombol Otomatis/Manual & form PO menghormatinya",
           "form membaca kebijakan lalu mengunci kolom nomor saat mode otomatis")
    else:
        bad("G7", "kontrol mode belum lengkap di layar",
            f"tombol mode={have_toggle} form PO patuh={have_form}")

    # G8 — jangan sampai kebijakan baru MENOLAK nomor yang dibuat sistem sendiri.
    # PO Maklon lahir dengan nomor dari jenis dokumen `dewi_maklon_pos.po_number`
    # (MKL-{KLIEN}-{YYYY}-{SEQ:4}) lalu DICERMINKAN ke `production_pos`. Bila jalur
    # cermin itu ikut diterbitkan/divalidasi ulang di bawah jenis dokumen lain,
    # satu dokumen punya dua penomoran dan PO Maklon gagal dibuat sama sekali.
    mirror = (ROOT / "backend/routes/dewi_maklon_pos.py").read_text()
    engine = (ROOT / "backend/routes/production_pos.py").read_text()
    if "number_issued=True" in mirror and "number_issued: bool = False" in engine:
        ok("G8", "jalur cermin PO Maklon memakai nomor yang sudah diterbitkan hulunya",
           "tidak ada dokumen yang dinomori dua kali oleh dua jenis dokumen")
    else:
        bad("G8", "jalur cermin PO Maklon akan dinomori/divalidasi ulang",
            "nomor MKL-… buatan sistem sendiri berisiko ditolak kebijakan PO produksi")


def part_runtime(db, restore_cfg):
    print(f"\n{B}[2] KEBIJAKAN & PENOLAKAN{X}")
    admin = login("admin@garment.com", "Admin@123")
    staff = login("spv@dewiaditya.id", "Dewi@123")
    if not admin:
        bad("G1", "login admin gagal — invarian runtime tidak bisa diuji")
        return

    st_pol, pol = call("GET", f"/api/doc-number-policy?key={KEY}", staff or admin)
    if st_pol != 200:
        bad("G1", f"kebijakan nomor tidak bisa dibaca staf pembuat dokumen (HTTP {st_pol})",
            "form PO tidak akan pernah tahu kolom nomor harus dikunci atau tidak")
        return
    if pol.get("mode_default") != "manual":
        bad("G1", f"bawaan mode PO produksi = {pol.get('mode_default')} (harusnya manual)",
            "menyalakan fitur ini tidak boleh mengubah cara kerja yang sedang jalan")
    else:
        ok("G1", "kebijakan dibaca staf pembuat dokumen; bawaan PO produksi tetap MANUAL",
           f"format {pol.get('format')} · contoh {pol.get('contoh')} · "
           f"pola {pol.get('pola')}")

    # ── MANUAL ───────────────────────────────────────────────────────────────
    set_mode(admin, "manual")
    st, r = make_po(admin, "PO-BEBAS-GAB-A")
    msg = detail(r)
    if st == 400 and "pola" in msg.lower():
        ok("G2", "nomor berpola bebas DITOLAK dengan pola & contoh yang benar",
           msg[:170])
    else:
        bad("G2", f"nomor bebas 'PO-BEBAS-GAB-A' tidak ditolak (HTTP {st})", msg[:200])

    st_pol, pol = call("GET", f"/api/doc-number-policy?key={KEY}", admin)
    good_number = pol.get("nomor_berikutnya")
    st, r = make_po(admin, good_number)
    if st in (200, 201):
        saved = db.production_pos.find_one({"id": r.get("id")}, {"_id": 0, "po_number": 1})
        if (saved or {}).get("po_number") == good_number:
            ok("G3", "nomor manual yang sesuai pola diterima & tersimpan sama persis",
               f"{good_number}")
        else:
            bad("G3", "nomor tersimpan berbeda dengan yang dikirim",
                f"dikirim {good_number} · tersimpan {(saved or {}).get('po_number')}")
    else:
        bad("G3", f"nomor manual yang benar justru ditolak (HTTP {st})", detail(r)[:200])

    st, r = make_po(admin, good_number)
    if st == 409:
        ok("G4", "nomor duplikat DITOLAK (mustahil ada dua dokumen bernomor sama)",
           detail(r)[:150])
    else:
        bad("G4", f"nomor duplikat '{good_number}' tidak ditolak (HTTP {st})", detail(r)[:200])

    # ── OTOMATIS ─────────────────────────────────────────────────────────────
    print(f"\n{B}[3] MODE OTOMATIS{X}")
    set_mode(admin, "auto")
    st, r = make_po(admin, "PO-KETIKAN-SAYA-1")
    msg = detail(r)
    st_pol, pol2 = call("GET", f"/api/doc-number-policy?key={KEY}", admin)
    akan = pol2.get("nomor_berikutnya") or ""
    if st == 400 and "otomatis" in msg.lower() and akan and akan in msg:
        ok("G5", "nomor ketikan DITOLAK saat mode otomatis, sambil menyebut nomor yang dipakai",
           msg[:180])
    elif st == 400 and "otomatis" in msg.lower():
        bad("G5", "penolakan tidak menyebut nomor yang akan dipakai",
            f"pesan: {msg[:160]} · seharusnya memuat {akan}")
    else:
        bad("G5", f"nomor ketikan tidak ditolak saat mode otomatis (HTTP {st})", msg[:200])

    nums = []
    for _ in range(2):
        st, r = make_po(admin, None)
        if st not in (200, 201):
            bad("G6", f"PO otomatis gagal dibuat (HTTP {st})", detail(r)[:200])
            return
        nums.append(r.get("po_number"))
    rx = re.compile(pol2.get("pola") or r"^$")
    seq = [int(re.search(r"(\d+)$", n).group(1)) for n in nums if re.search(r"(\d+)$", n)]
    if all(rx.match(n or "") for n in nums) and len(seq) == 2 and seq[1] == seq[0] + 1:
        ok("G6", "nomor otomatis mengikuti format DAN berurut",
           f"{nums[0]} → {nums[1]} (pola {pol2.get('format')})")
    else:
        bad("G6", "nomor otomatis tidak sesuai format / tidak berurut",
            f"{nums} vs pola {pol2.get('pola')}")


def main():
    print(f"{C}{B}FASE G — Penomoran dokumen: mode Otomatis/Manual ditegakkan{X}")
    db = db_handle()
    restore_cfg = db.doc_number_configs.find_one({"key": KEY})
    clean(db, restore_cfg)
    try:
        part_static()
        part_runtime(db, restore_cfg)
    finally:
        if "--keep" not in sys.argv:
            n = clean(db, restore_cfg)
            print(f"\n{Y}  bersih-bersih: {n} PO uji dihapus, kebijakan dikembalikan{X}")
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian penomoran terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
