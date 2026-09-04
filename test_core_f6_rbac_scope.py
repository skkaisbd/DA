#!/usr/bin/env python3
"""test_core_f6_rbac_scope.py — CORE TEST **F6**: lingkup toko per PEMAKAI + layar
"siapa mengubah apa".

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN (dan kenapa justru itu yang diuji)
═══════════════════════════════════════════════════════════════════════════════
`core/marketing_account_scope.py` sudah menuliskan aturan "siapa boleh melihat
toko yang mana" sejak F6 — tetapi pada awal sesi #9 hanya **7 dari 54** berkas
`routes/marketing_*.py` yang memanggilnya. Diukur dengan dua token (staf yang
memegang SATU toko vs admin), **14 endpoint** memberi jawaban yang PERSIS SAMA:
staf melihat omzet 9 toko, biaya iklan 9 toko, komplain, ulasan, sesi live,
peringkat kreator, bahkan **riwayat impor** (dari sana ada tombol "Batalkan &
pulihkan" — jalan pintas mengubah data toko orang lain).

* `A-*` **Jaring pengaman (middleware).** Kelas masalahnya IDOR: menukar
  `account_id` di URL/body. Ditutup di SATU tempat supaya berkas route ke-55
  tidak perlu ingat aturannya. Dijaga: path, query, DAN body; admin tidak
  terpengaruh; toko yang tidak ada TIDAK dijadikan 403 (biar route balas 404).
* `B-*` **Endpoint DAFTAR/RINGKAS** (yang tidak menyebut toko) wajib menyaring
  sendiri — middleware tidak tahu isi jawabannya. Diuji dengan membandingkan
  jawaban staf vs admin: kalau identik pada data yang tidak kosong, itu bocor.
* `C-*` **Layar "siapa mengubah apa".** Jejak yang tidak bisa dicari sama dengan
  tidak ada. Diuji: paginasi & `total` yang JUJUR (bukan `len(rows)`), filter
  toko/aksi/pelaku/tanggal/teks, nilai LAMA→BARU per field, id user diterjemahkan
  jadi NAMA, dan lingkup F6 tetap berlaku pada jejak itu sendiri.
* `D-*` **Statik.** Berkas yang WAJIB memanggil helper lingkup didaftar di sini;
  begitu ada yang melepasnya, gate merah. Juga: jejak tidak boleh punya endpoint
  tulis (jejak yang bisa disunting bukan jejak).

DATA UJI: memakai akun `staffmkt@dewiaditya.id` (peran `staff_marketing` dari
`seed_role_accounts`), meng-assign SATU toko kepadanya lewat API resmi, lalu
MEMULIHKAN daftar staf toko itu ke keadaan semula. Jejak yang lahir dari gate ini
bertanda `QAF6` dan hanya baris bertanda itu yang dihapus (aturan A-2e sesi #8b:
gate tidak boleh memusnahkan bukti).

Pakai:  python3 /app/test_core_f6_rbac_scope.py [--keep]
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
STAFF = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []
MARK = "QAF6"

# Berkas yang WAJIB memanggil helper lingkup (F6). Daftar ini adalah kontraknya:
# menambah layar daftar marketing baru berarti menambah barisnya di sini.
MUST_SCOPE = [
    "routes/marketing_reports.py",
    "routes/marketing_reports_weekly.py",
    "routes/marketing_dashboard.py",
    "routes/marketing_sales_performance_routes.py",
    "routes/marketing_ads_routes.py",
    "routes/marketing_returns_routes.py",
    "routes/marketing_reviews_routes.py",
    "routes/marketing_complaints_routes.py",
    "routes/marketing_live_sessions_routes.py",
    "routes/marketing_live_analytics.py",
    "routes/marketing_kol_leaderboard.py",
    "routes/marketing_data_import.py",
    "routes/marketing_change_log.py",
    "routes/marketing_targets.py",
    "routes/marketing_budget.py",
    "routes/marketing_orders_routes.py",
    "routes/marketing_content_calendar_routes.py",
    "routes/marketing_platform_kpi_routes.py",
]

# Endpoint DAFTAR/RINGKAS yang tidak menyebut toko → jawaban staf HARUS berbeda
# dari admin (atau kosong). `path` · `jalan ke angka/daftar`.
LIST_ENDPOINTS = [
    ("/api/marketing/reports/daily", "accounts"),
    ("/api/marketing/reports/monthly?year=2026&month=7", "accounts"),
    ("/api/marketing/reports/weekly?week_start=2026-07-15", "per_toko"),
    ("/api/marketing/ads/summary", "data.total_spend"),
    ("/api/marketing/ads/campaigns", "data.campaigns"),
    ("/api/marketing/returns/summary", "data.total"),
    ("/api/marketing/reviews/summary", "data.total"),
    ("/api/marketing/complaints", "complaints"),
    ("/api/marketing/live/sessions", "data.sessions"),
    ("/api/marketing/live/summary", "data.total_revenue"),
    ("/api/marketing/live/analytics/overview", "kpi.total_sessions"),
    ("/api/marketing/kol-leaderboard/", "data"),
    ("/api/marketing/data-import/sessions", "sessions"),
    ("/api/marketing/cycle/overview?period=2026-07", "rows"),
    ("/api/marketing/performance/overview", "data.total_revenue"),
    # sesi #10 — ditemukan lewat UJI LAYAR: kartu "Marketing Overview" memanggil
    # enam ringkasan yang tidak pernah masuk daftar ini, dan lima di antaranya
    # memberi staf tanpa toko angka SEMBILAN toko (omzet Rp 57,5 jt, 9 akun,
    # 10 diskon, 8 peluncuran, 15 konten).
    ("/api/marketing/orders/summary", "total_revenue"),
    ("/api/marketing/health/summary", "data.total_accounts"),
    ("/api/marketing/discounts/summary", "data.total"),
    ("/api/marketing/product-launches/summary", "data.total"),
    ("/api/marketing/content-calendar/summary", "data.total"),
    ("/api/marketing/complaints/summary", "total"),
    ("/api/marketing/samples/summary", "data.total"),
    ("/api/marketing/targets", ""),
    ("/api/marketing/catalogs", "catalogs"),
    ("/api/marketing/orders/fulfillment-monitor", "totals.belum_dikirim"),
    ("/api/marketing/data-import/history", "history"),
    ("/api/marketing/ai-insights/overview", "data.orders.total"),
]

# ── SWEEP (sesi #10): setiap GET marketing dipukul rata dengan dua token ─────
# Daftar LIST_ENDPOINTS di atas adalah kurasi manusia — dan manusia lupa. Sweep
# ini MENEMUKAN sendiri seluruh `@router.get` marketing tanpa parameter path lalu
# membandingkan jawaban staf-tanpa-toko vs admin. Endpoint yang SAH sama untuk
# semua pemakai harus terdaftar di bawah ini **beserta alasannya** — pengecualian
# yang tidak bisa dibaca sama dengan tidak ada aturan.
SCOPE_EXEMPT = {
    # nilai acuan / enum (bukan angka toko)
    "/api/marketing/live/statuses": "enum status sesi live",
    # F9 (sesi #12) — peta akun COA yang dipakai jurnal pencairan. Isinya
    # KONFIGURASI akuntansi (kode + nama akun), bukan angka toko mana pun, jadi
    # ia memang sama untuk semua pemakai. Justru DISENGAJA bisa dibaca staf:
    # kalau peta akun hanya ada di kode, orang yang membaca laporan tidak bisa
    # memeriksa apakah potongan platform masuk ke akun yang benar.
    "/api/marketing/settlements/coa-map": "peta akun COA (konfigurasi akuntansi, bukan angka toko)",
    "/api/marketing/discounts/types": "enum jenis diskon",
    "/api/marketing/content-calendar/types": "enum jenis konten",
    "/api/marketing/content-calendar/platforms": "enum platform",
    "/api/marketing/reviews/platforms": "enum platform ulasan",
    "/api/marketing/reviews/categories": "enum kategori ulasan",
    "/api/marketing/returns/reasons": "enum alasan retur",
    "/api/marketing/ads/platforms": "enum platform iklan",
    "/api/marketing/data-import/source-types": "katalog jenis impor (skema, bukan data)",
    # SESI #38 — pintu pertama wizard impor (6 KELOMPOK). Isinya SKEMA yang sama
    # persis untuk semua pemakai: nama kelompok + jumlah jenis di dalamnya. Tidak
    # ada satu angka toko di dalamnya, dan staf toko justru WAJIB bisa
    # membacanya — tanpa daftar kelompok, layar impor tidak punya pilihan apa pun.
    "/api/marketing/data-import/source-groups": "katalog KELOMPOK jenis impor "
                                                "(skema, bukan data toko)",
    # SESI #34 — panjang periode anggaran (7 hari vs 1 bulan). Isinya SETELAN
    # perusahaan (mode + jumlah hari + tanggal periode berjalan), bukan angka
    # toko mana pun; staf toko justru harus bisa membacanya agar layar anggaran
    # tahu periode mana yang sedang berjalan.
    "/api/marketing/budget/period-settings": "setelan panjang periode anggaran (konfigurasi, bukan angka toko)",
    # master milik PERUSAHAAN (bukan milik satu toko) — justru dibutuhkan staf
    # toko untuk menambah item ke katalog tokonya
    "/api/marketing/catalogs/fg-products": "master barang jadi perusahaan",
    "/api/marketing/catalogs/master-products": "master produk internal perusahaan",
    # konfigurasi/sistem — tidak memuat angka toko
    "/api/marketing/accounts/coa-options": "daftar akun COA (master keuangan)",
    "/api/marketing/integration-settings/meta": "metadata integrasi (konfigurasi)",
    "/api/marketing/advanced-ai/pricing/settings": "ambang & konfigurasi AI harga",
    "/api/marketing/alerts/settings": "ambang peringatan (konfigurasi, bukan angka toko)",
    "/api/marketing/alerts/history": "riwayat JALANNYA penjadwal (berapa kali jalan)",
    "/api/marketing/webhooks/security-status": "status keamanan webhook (konfigurasi)",
    "/api/marketing/data-import/formats": "ingatan susunan kolom (per bentuk berkas, "
                                          "bukan per toko)",
    "/api/marketing/account-assign/staff-options": "daftar ORANG yang bisa di-assign "
                                                   "(bukan angka toko)",
    # SESI #38 — sudut pandang per ORANG ("Rina pegang toko apa saja"). Daftar
    # BARISnya adalah staf marketing (master pemakai), sedangkan daftar toko di
    # tiap baris SUDAH disaring `scope.scope_filter` — staf tanpa toko menerima
    # `accounts: []`. Bobotnya bisa sama dengan admin hanya ketika seluruh staf
    # memang memegang 0 toko; itu bukan kebocoran, itu kenyataan yang sama.
    "/api/marketing/account-assign/by-staff": "roster staf marketing (daftar toko "
                                             "di tiap baris sudah disaring lingkup)",
}


def check(name: str, cond: bool, detail: str = "") -> bool:
    RES.append((name, bool(cond), detail))
    print(f"  {G}PASS{X}  {name}" if cond else f"  {R}FAIL{X}  {name}",
          f"— {detail}" if detail else "")
    return bool(cond)


def login(creds: dict) -> str:
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=60)
    r.raise_for_status()
    return r.json()["token"]


def dig(payload, path: str):
    # Jawaban yang berbentuk DAFTAR langsung (mis. GET /targets) tidak punya jalur
    # field; jumlah barisnya-lah angkanya.
    if not path:
        return len(payload) if isinstance(payload, list) else payload
    cur = payload
    for k in path.split("."):
        cur = (cur or {}).get(k) if isinstance(cur, dict) else None
    return len(cur) if isinstance(cur, list) else cur


def get(path: str, token: str):
    r = requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"},
                     timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:                                            # noqa: BLE001
        return r.status_code, {}


def num(v) -> float:
    """Angka yang bisa dibandingkan. `None`/teks/dict ⇒ 0 (dianggap kosong)."""
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return 0.0


def set_staff(AT: str, account_id: str, staff_ids: list, reason: str):
    """Ubah daftar staf pemegang toko lewat API resmi (bukan tulis langsung ke DB)."""
    return requests.post(f"{BASE}/api/marketing/account-assign/{account_id}",
                         headers={"Authorization": f"Bearer {AT}"}, timeout=60,
                         json={"staff_ids": staff_ids, "reason": reason})


# ═══════════════════════════════════════════════════════════════════════════════
# [A] JARING PENGAMAN — toko yang DISEBUT permintaan
# ═══════════════════════════════════════════════════════════════════════════════
def section_guard(AT: str, ST: str, mine: dict, other: dict) -> None:
    print(f"\n{Y}[A] JARING PENGAMAN — menukar account_id di URL/body ⇒ 403{X}")
    aid_other, aid_mine = other["id"], mine["id"]

    code, body = get(f"/api/marketing/cycle/summary?account_id={aid_other}&period=2026-07", ST)
    check("A-1 QUERY account_id toko lain ⇒ 403", code == 403,
          f"HTTP {code} · {str(body.get('detail'))[:80]}")
    check("A-2 pesan 403 menyebut NAMA toko + jalan keluarnya (minta SPV assign)",
          code == 403 and other["account_name"] in str(body.get("detail"))
          and "SPV" in str(body.get("detail")), str(body.get("detail"))[:110])

    code, _ = get(f"/api/marketing/accounts/{aid_other}/sales", ST)
    check("A-3 PATH /accounts/{id}/... toko lain ⇒ 403", code == 403, f"HTTP {code}")

    r = requests.post(f"{BASE}/api/marketing/sales/recompute",
                      headers={"Authorization": f"Bearer {ST}"}, timeout=60,
                      params={"account_id": aid_other, "date_from": "2026-07-05"})
    check("A-4 TULIS (hitung ulang rekap) toko lain ⇒ 403", r.status_code == 403,
          f"HTTP {r.status_code}")

    r = requests.post(f"{BASE}/api/marketing/sales-data",
                      headers={"Authorization": f"Bearer {ST}"}, timeout=60,
                      json={"account_id": aid_other, "date": "2027-05-05",
                            "revenue_type": "total", "revenue": 1})
    check("A-5 BODY JSON account_id toko lain ⇒ 403 (body ikut diperiksa)",
          r.status_code == 403, f"HTTP {r.status_code}")

    code, _ = get(f"/api/marketing/cycle/summary?account_id={aid_mine}&period=2026-07", ST)
    check("A-6 toko SENDIRI tetap bisa dibuka staf ⇒ 200", code == 200, f"HTTP {code}")

    code, _ = get(f"/api/marketing/cycle/summary?account_id={aid_other}&period=2026-07", AT)
    check("A-7 admin TIDAK terpengaruh jaring pengaman ⇒ 200", code == 200, f"HTTP {code}")

    code, _ = get("/api/marketing/cycle/summary?account_id=toko-yang-tidak-ada&period=2026-07", ST)
    check("A-8 account_id yang TIDAK ADA di DB tidak dibelokkan jadi 403 "
          "(biar route menjawab 404/400 dengan pesannya sendiri)",
          code != 403, f"HTTP {code}")


# ═══════════════════════════════════════════════════════════════════════════════
# [B] ENDPOINT DAFTAR/RINGKAS — wajib menyaring sendiri
# ═══════════════════════════════════════════════════════════════════════════════
def section_lists_zero(AT: str, ST: str) -> dict:
    """Pas pertama: staf yang **tidak memegang toko apa pun**.

    Inilah bukti lingkup yang tidak bisa ditafsir dua arti: kalau seorang staf
    tanpa toko masih melihat angka, endpoint itu memang tidak menyaring. (Pas
    kedua — staf dengan SATU toko — memakai hasil ini: dua angka yang KEBETULAN
    sama tidak lagi dilaporkan bocor kalau di pas ini terbukti kosong. Sebab yang
    nyata: seluruh data uji sebuah endpoint bisa memang milik satu toko itu,
    mis. sesi kreator demo hanya ada di satu toko.)
    """
    print(f"\n{Y}[B0] staf TANPA toko — semua daftar/ringkas wajib KOSONG{X}")
    proved: dict = {}
    for path, expr in LIST_ENDPOINTS:
        cs, bs = get(path, ST)
        ca, ba = get(path, AT)
        vs, va = dig(bs, expr), dig(ba, expr)
        ok = cs == 200 and ca == 200 and num(vs) == 0
        proved[path] = ok
        check(f"B0-{path.split('/api/marketing/')[1][:43]}", ok,
              f"staf(0 toko)={vs} · admin={va} (HTTP {cs}/{ca})")
    bad = [p for p, v in proved.items() if not v]
    check("B0-RINGKAS staf tanpa toko tidak melihat angka toko siapa pun",
          not bad, f"{len(bad)} bocor: {bad[:3]}")
    return proved


# ═══════════════════════════════════════════════════════════════════════════════
# [B2] SWEEP — SELURUH GET marketing dipukul rata (menemukan yang belum terdaftar)
# ═══════════════════════════════════════════════════════════════════════════════
def _marketing_get_endpoints() -> list:
    """Kumpulkan `@router.get` di `routes/marketing_*.py` tanpa parameter path."""
    out = []
    for f in sorted(Path("/app/backend/routes").glob("marketing_*.py")):
        src = f.read_text(encoding="utf-8")
        prefixes = re.findall(r"APIRouter\(\s*prefix=['\"]([^'\"]+)['\"]", src)
        for m in re.finditer(r"@\w+\.get\(\s*['\"]([^'\"]*)['\"]", src):
            path = m.group(1)
            if "{" in path:
                continue
            for pre in prefixes:
                url = (pre + path).replace("//", "/")
                if url.startswith("/api/marketing"):
                    out.append((f.name, url))
    return sorted(set(out))


def _weight(v, depth: int = 0) -> float:
    """"Seberapa banyak angka/baris" dalam sebuah jawaban (kasar tapi cukup).

    Kunci teknis (batas halaman, waktu pembuatan, penjelasan) DIBUANG supaya
    jawaban KOSONG tidak tampak sama-berisi hanya karena `limit: 50`.
    """
    # SESI #40 — `sla_default`, `labels`, dan `named` ikut dibuang. Ketiganya
    # KONSTANTA/penjelasan, bukan angka milik toko: `sla_default {normal:2,
    # preorder:7}` menyumbang bobot 9 dan baris penjelas `gap.named` menyumbang 1,
    # sehingga saat data memang KOSONG jawaban admin & staf sama-sama berbobot >0
    # dan sweep menuduh kebocoran atas jawaban yang sebenarnya tidak memuat satu
    # angka toko pun (terbukti: kedua jawaban seluruhnya 0/[] ).
    SKIP = {"ok", "success", "page", "page_size", "limit", "total_pages", "days",
            "has_next", "has_prev", "data_notes", "notes", "message", "detail",
            "generated_at", "status_filter", "period", "scope", "sort_by",
            "period_days", "year", "month", "sla_default", "labels", "named"}
    if depth > 4 or isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return abs(float(v))
    if isinstance(v, list):
        return len(v) + sum(_weight(x, depth + 1) for x in v)
    if isinstance(v, dict):
        return sum(_weight(x, depth + 1) for k, x in v.items() if k not in SKIP)
    return 0.0


def section_sweep(AT: str, ST: str) -> None:
    """Semua GET marketing: staf TANPA toko tidak boleh menerima angka apa pun.

    KENAPA SWEEP, BUKAN DAFTAR: sesi #9 mendaftar 15 endpoint dan menutup 18
    berkas — lalu uji LAYAR sesi #10 menemukan enam ringkasan lain ("Marketing
    Overview") yang tidak pernah masuk daftar dan membocorkan omzet 9 toko.
    Berkas route ke-55 akan mengulang kesalahan yang sama; sweep ini yang
    menemukannya, bukan ingatan agen berikutnya.
    """
    print(f"\n{Y}[B2] SWEEP seluruh GET marketing — staf tanpa toko vs admin{X}")
    leaks, checked, exempt_hit = [], 0, set()
    for fname, url in _marketing_get_endpoints():
        ca, ba = get(url, AT)
        if ca != 200:
            continue                      # butuh query wajib / bukan daftar
        cs, bs = get(url, ST)
        checked += 1
        wa, ws = _weight(ba), _weight(bs)
        if cs == 200 and wa > 0 and abs(wa - ws) < 1e-9:
            if url in SCOPE_EXEMPT:
                exempt_hit.add(url)
            else:
                leaks.append(f"{url} (admin={wa:.0f} staf={ws:.0f}) [{fname}]")
    check(f"B2-SWEEP {checked} GET marketing diperiksa — tidak ada yang membocorkan "
          "angka ke staf tanpa toko", not leaks,
          f"{len(leaks)} bocor: {leaks[:4]}" if leaks
          else f"{len(exempt_hit)} endpoint acuan/konfigurasi dikecualikan dengan alasan")
    check("B2-DAFTAR pengecualian lingkup selalu punya ALASAN tertulis",
          all(bool(str(v).strip()) for v in SCOPE_EXEMPT.values()),
          f"{len(SCOPE_EXEMPT)} pengecualian")


def section_lists(AT: str, ST: str, proved: dict | None = None) -> None:
    print(f"\n{Y}[B] DAFTAR/RINGKAS tanpa account_id — staf 1 toko ≤ admin 9 toko{X}")
    proved = proved or {}
    leaks = []
    for path, expr in LIST_ENDPOINTS:
        cs, bs = get(path, ST)
        ca, ba = get(path, AT)
        vs, va = dig(bs, expr), dig(ba, expr)
        smaller = num(vs) < num(va)
        # Sama-besar hanya SAH bila endpoint ini sudah terbukti menyaring pada
        # pas B0 (staf tanpa toko ⇒ kosong) — artinya seluruh data uji-nya memang
        # milik toko staf. Tanpa bukti itu, sama-besar = bocor.
        legit_equal = num(vs) == num(va) and (not num(va) or proved.get(path))
        ok = (cs == 200 and ca == 200) and num(vs) <= num(va) and (smaller or legit_equal)
        if not ok:
            leaks.append(f"{path} [{expr}] staf={vs} admin={va} (HTTP {cs}/{ca})")
        check(f"B-{path.split('/api/marketing/')[1][:44]}", ok,
              f"staf={vs} · admin={va}"
              + (" (sama besar — SAH: pas B0 membuktikan endpoint ini menyaring, "
                 "seluruh data ujinya milik toko staf)"
                 if ok and legit_equal and num(va) else ""))
    check("B-RINGKAS tidak ada endpoint daftar yang menyamakan staf dengan admin "
          "tanpa bukti menyaring", not leaks, f"{len(leaks)} bocor: {leaks[:3]}")


# ═══════════════════════════════════════════════════════════════════════════════
# [C] LAYAR "SIAPA MENGUBAH APA"
# ═══════════════════════════════════════════════════════════════════════════════
def section_changelog(AT: str, ST: str, mine: dict, reason: str) -> None:
    print(f"\n{Y}[C] JEJAK PERUBAHAN — bisa dicari, dihalaman, & jujur{X}")
    code, d = get("/api/marketing/change-log?page_size=5", AT)
    rows = d.get("rows") or []
    check("C-1 endpoint jejak hidup & berhalaman", code == 200 and "total_pages" in d,
          f"HTTP {code} · total={d.get('total')} halaman={d.get('total_pages')}")
    check("C-2 `total` = jumlah SESUNGGUHNYA (bukan len(rows) halaman ini)",
          isinstance(d.get("total"), int) and d["total"] >= len(rows)
          and (d["total"] > len(rows) or d.get("total_pages") == 1),
          f"total={d.get('total')} rows={len(rows)}")
    # Baris yang dicari adalah PERSIS perubahan assign toko `mine` (bukan sekadar
    # baris pertama bertanda gate — pembersihan toko pembanding juga bertanda sama).
    mine_row = next((r for r in rows if str(r.get("reason") or "") == reason), None)
    check("C-3 perubahan assign yang baru dibuat gate MUNCUL di jejak",
          bool(mine_row), f"alasan={str((mine_row or {}).get('reason'))[:60]}")
    check("C-4 baris membawa nama TOKO, label aksi, pelaku + PERAN, dan alasan",
          bool(mine_row) and mine_row.get("account_name") == mine["account_name"]
          and mine_row.get("action_label") and mine_row.get("actor_role")
          and mine_row.get("reason") == reason,
          f"{(mine_row or {}).get('account_name')} · {(mine_row or {}).get('action_label')} "
          f"· {(mine_row or {}).get('actor_name')} ({(mine_row or {}).get('actor_role')})")
    ch = (mine_row or {}).get("changes") or []
    staff_change = next((c for c in ch if c.get("field") in ("assigned_staff", "added")), None)
    check("C-5 nilai LAMA → BARU dipecah per field (bukan dua blob JSON)",
          bool(staff_change) and "before" in staff_change and "after" in staff_change,
          f"{[c.get('field') for c in ch]}")
    after = (staff_change or {}).get("after")
    check("C-6 id user DITERJEMAHKAN jadi NAMA (uuid tidak menjawab 'siapa')",
          isinstance(after, list) and bool(after)
          and not any(len(str(x)) == 36 and str(x).count("-") == 4 for x in after),
          f"after={after}")
    check("C-7 perubahan kewenangan ditandai beda dari perubahan angka",
          (mine_row or {}).get("kind") == "kewenangan",
          f"kind={(mine_row or {}).get('kind')}")

    code, d2 = get("/api/marketing/change-log?only_permissions=true&page_size=50", AT)
    check("C-8 filter 'hanya kewenangan' benar-benar menyaring",
          code == 200 and all(r.get("kind") == "kewenangan" for r in (d2.get("rows") or []))
          and (d2.get("total") or 0) >= 1,
          f"{d2.get('total')} baris kewenangan")
    code, d3 = get(f"/api/marketing/change-log?q={MARK}", AT)
    check("C-9 pencarian teks (alasan/pelaku) bekerja",
          code == 200 and (d3.get("total") or 0) >= 1, f"total={d3.get('total')}")
    code, d4 = get(f"/api/marketing/change-log?account_id={mine['id']}", AT)
    check("C-10 filter per TOKO bekerja & semua barisnya milik toko itu",
          code == 200 and all(r.get("account_id") == mine["id"]
                              for r in (d4.get("rows") or [])),
          f"total={d4.get('total')}")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    code, d5 = get(f"/api/marketing/change-log?date_from={today}&date_to={today}", AT)
    check("C-11 filter tanggal bekerja (perubahan hari ini terbaca)",
          code == 200 and (d5.get("total") or 0) >= 1, f"total={d5.get('total')}")
    code, d6 = get("/api/marketing/change-log?page_size=1&page=2", AT)
    check("C-12 halaman ke-2 mengembalikan baris BERBEDA (paginasi nyata)",
          code == 200 and len(d6.get("rows") or []) <= 1
          and (not rows or not d6.get("rows")
               or d6["rows"][0]["id"] != rows[0]["id"]), "")
    fl = d.get("filters") or {}
    check("C-13 pilihan filter (jenis/aksi/pelaku) dihitung dari data nyata",
          bool(fl.get("entities")) and bool(fl.get("actions")) and bool(fl.get("actors")),
          f"{len(fl.get('entities') or [])} jenis · {len(fl.get('actions') or [])} aksi "
          f"· {len(fl.get('actors') or [])} pelaku")
    check("C-14 catatan kejujuran data ikut dikirim",
          any("READ-ONLY" in n for n in (d.get("data_notes") or [])),
          str((d.get("data_notes") or [""])[0])[:70])

    # lingkup F6 pada jejak itu sendiri
    code, ds = get("/api/marketing/change-log?page_size=100", ST)
    check("C-15 staf hanya melihat jejak TOKO-nya sendiri",
          code == 200 and all(r.get("account_id") == mine["id"]
                              for r in (ds.get("rows") or [])),
          f"total staf={ds.get('total')} vs admin={d.get('total')}")
    check("C-16 staf DIBERI TAHU bahwa jejak lintas-toko disembunyikan "
          "(bukan tampak 'tidak ada')",
          any("di-assign kepada Anda" in n for n in (ds.get("data_notes") or [])),
          next((n[:80] for n in (ds.get("data_notes") or [])
                if "di-assign" in n), "—"))
    code, st = get("/api/marketing/change-log/stats?days=30", AT)
    check("C-17 kartu ringkas jejak (angka vs kewenangan vs pelaku) hidup",
          code == 200 and st.get("total", 0) >= 1
          and st.get("number_changes", -1) + st.get("permission_changes", -1) == st["total"],
          f"total={st.get('total')} angka={st.get('number_changes')} "
          f"kewenangan={st.get('permission_changes')} pelaku={st.get('actors')}")

    # ── C-18/C-19: ALASAN pada perubahan ANGKA ──────────────────────────────
    # Sampai sesi #9 hanya jalur kewenangan & kunci periode yang membawa alasan;
    # target & anggaran tercatat TANPA alasan, jadi jejaknya bisa menjawab
    # "berapa" tetapi tidak pernah "kenapa". Dibuktikan di sini lewat API resmi.
    reason_num = f"uji {MARK} target diubah karena stok warna utama habis"
    rt = requests.post(f"{BASE}/api/marketing/targets", timeout=60,
                       headers={"Authorization": f"Bearer {AT}"},
                       json={"account_id": mine["id"], "year": 2029, "month": 1,
                             "revenue_target": 12_345_000, "orders_target": 7,
                             "notes": f"{MARK} sementara", "reason": reason_num})
    code, dr = get(f"/api/marketing/change-log?q={MARK}%20target&page_size=20", AT)
    row_num = next((r for r in (dr.get("rows") or [])
                    if r.get("reason") == reason_num), None)
    check("C-18 ALASAN perubahan ANGKA (target) tersimpan & terbaca di jejak",
          rt.status_code == 200 and bool(row_num),
          f"HTTP {rt.status_code} · alasan={str((row_num or {}).get('reason'))[:60]}")
    check("C-19 baris angka itu membawa nilai LAMA → BARU per field + periodenya",
          bool(row_num) and any(c.get("field") == "revenue_target"
                                for c in (row_num or {}).get("changes") or [])
          and (row_num or {}).get("period") == "2029-01"
          and (row_num or {}).get("kind") == "angka",
          f"{[c.get('field') for c in (row_num or {}).get('changes') or []]} · "
          f"periode={(row_num or {}).get('period')}")
    # C-20 — baris yang "berubah" dari kosong ke kosong adalah KEBISINGAN: pembaca
    # audit mencari pencabutan staf yang sebenarnya tidak pernah terjadi
    # ("Staf dicabut: belum ada → kosong"). Tidak boleh ada satu pun.
    code, dall = get("/api/marketing/change-log?page_size=200", AT)
    noise = [(r.get("action"), c.get("field"))
             for r in (dall.get("rows") or []) for c in (r.get("changes") or [])
             if c.get("before") in (None, "", [], {}) and c.get("after") in (None, "", [], {})]
    check("C-20 tidak ada baris 'kosong → kosong' yang menyesatkan pembaca audit",
          not noise, f"{len(noise)} kebisingan: {noise[:3]}")
    db_tmp = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
    db_tmp.marketing_account_targets.delete_many(
        {"account_id": mine["id"], "year": 2029, "month": 1})


# ═══════════════════════════════════════════════════════════════════════════════
# [D] STATIK — kontrak yang tidak boleh dilepas
# ═══════════════════════════════════════════════════════════════════════════════
def section_static() -> None:
    print(f"\n{Y}[D] PENJAGA STATIK — helper lingkup & jejak read-only{X}")
    missing = []
    for rel in MUST_SCOPE:
        src = open(f"/app/backend/{rel}", encoding="utf-8").read()
        if not any(k in src for k in ("assert_account_visible", "scope_filter",
                                      "visible_account_ids", "visible_accounts")):
            missing.append(rel)
    check(f"D-1 {len(MUST_SCOPE)} berkas route marketing memakai helper lingkup",
          not missing, f"tanpa lingkup: {missing}")

    mw = open("/app/backend/middleware/marketing_scope_guard.py", encoding="utf-8").read()
    check("D-2 jaring pengaman memeriksa path, query, DAN body",
          "_ids_from_path" in mw and "query_params" in mw and "request._body" in mw, "")
    check("D-3 jaring pengaman GAGAL-TERBUKA tetapi MENCATAT (tidak senyap)",
          "fail-open" in mw and "logger.warning" in mw, "")
    srv = open("/app/backend/server.py", encoding="utf-8").read()
    # BUKAN sekadar "namanya ada di berkas": pemanggilannya harus HIDUP (tidak
    # dikomentari). Cacat yang paling mungkin terjadi adalah seseorang mematikan
    # middleware sementara lalu lupa menghidupkannya kembali.
    check("D-4 jaring pengaman terpasang HIDUP di server (tidak dikomentari)",
          any(ln.strip().startswith("app.add_middleware(MarketingScopeGuardMiddleware)")
              for ln in srv.splitlines()), "")

    cl = open("/app/backend/routes/marketing_change_log.py", encoding="utf-8").read()
    check("D-5 jejak TIDAK punya endpoint tulis (jejak yang bisa disunting bukan jejak)",
          "@router.post" not in cl and "@router.put" not in cl
          and "@router.delete" not in cl and "@router.patch" not in cl, "")
    check("D-6 jejak memakai `count_documents` untuk total (bukan len(rows))",
          "count_documents" in cl, "")

    fe = open("/app/frontend/src/components/erp/marketing/MarketingChangeLogModule.jsx",
              encoding="utf-8").read()
    for tid in ("changelog-table", "changelog-filters", "changelog-export-csv",
                "changelog-only-permissions", "changelog-notes", "changelog-stats"):
        if tid not in fe:
            check(f"D-7 layar jejak memuat `{tid}`", False, "")
            break
    else:
        check("D-7 layar jejak memuat tabel, filter, CSV, tanda kewenangan, & catatan",
              True, "")
    reg = open("/app/frontend/src/components/erp/moduleRegistry.js", encoding="utf-8").read()
    nav = open("/app/frontend/src/components/erp/portal-shell/portalNav.js",
               encoding="utf-8").read()
    check("D-8 layar terdaftar di registry & muncul di navigasi DUA portal",
          "'marketing-change-log'" in reg and "'mgmt-marketing-change-log'" in reg
          and "marketing-change-log" in nav and "mgmt-marketing-change-log" in nav, "")

    # D-9 — ALASAN pada perubahan ANGKA: backend meneruskannya ke jejak DAN
    # layarnya menyediakan kolomnya. Salah satu saja tidak cukup: field yang tidak
    # pernah bisa diisi dari layar sama dengan tidak ada.
    tgt = open("/app/backend/routes/marketing_targets.py", encoding="utf-8").read()
    bud = open("/app/backend/routes/marketing_budget.py", encoding="utf-8").read()
    cyc = open("/app/frontend/src/components/erp/marketing/CycleView.jsx",
               encoding="utf-8").read()
    check("D-9 alasan perubahan ANGKA: diteruskan backend & bisa diisi dari layar",
          "reason=(data.reason" in tgt and "reason=(data.reason" in bud
          and "cycle-target-reason" in cyc and "cycle-budget-reason" in cyc, "")

    # D-10 — environment SEGAR tidak boleh melahirkan layar audit yang kosong:
    # seeder jejak demo wajib ikut `bootstrap.sh` (pelajaran sesi #9: seeder yang
    # hanya hidup sebagai perintah manual di HANDOFF = layar kosong bagi siapa pun
    # yang cuma menjalankan bootstrap).
    boot = open("/app/scripts/bootstrap.sh", encoding="utf-8").read()
    check("D-10 seeder jejak demo terdaftar di bootstrap.sh (layar tidak kosong "
          "di environment segar)",
          "seed_marketing_change_log_demo.py" in boot
          and os.path.exists("/app/scripts/seed_marketing_change_log_demo.py"), "")

    # D-11 (sesi #10) — NOL YANG MENJELASKAN DIRINYA. Sesudah kebocoran ditutup,
    # staf yang belum dipegangi toko melihat angka 0 di seluruh layar marketing.
    # Nol tanpa sebab melahirkan kesimpulan yang salah ("aplikasinya rusak" /
    # "tokonya tidak jualan"), jadi panel MENETAP + pesan pemilih toko yang benar
    # adalah bagian dari fiturnya, bukan hiasan.
    notice = "/app/frontend/src/components/erp/marketing/NoStoreScopeNotice.jsx"
    ov = open("/app/frontend/src/components/erp/marketing/MarketingOverviewDashboard.jsx",
              encoding="utf-8").read()
    pick = open("/app/frontend/src/components/erp/marketing/pickers/MarketingPickers.jsx",
                encoding="utf-8").read()
    nsrc = open(notice, encoding="utf-8").read() if os.path.exists(notice) else ""
    check("D-11 staf tanpa toko diberi tahu SEBAB & jalan keluarnya (panel menetap "
          "+ pesan pemilih toko), bukan angka 0 tanpa penjelasan",
          "marketing-no-scope-notice" in nsrc and "SPV Marketing" in nsrc
          and "NoStoreScopeNotice" in ov and "NoStoreScopeNotice" in fe
          and "di-assign kepada Anda" in pick, "")
    check("D-12 kartu KPI tidak pernah menampilkan 'NaN' untuk nilai yang belum "
          "diketahui (dipakai '—')",
          "Number.isFinite(v)" in ov, "")


def main() -> int:
    keep = "--keep" in sys.argv
    print(f"{B}{'=' * 88}{X}")
    print(f"{B}F6 — LINGKUP TOKO PER PEMAKAI + LAYAR 'SIAPA MENGUBAH APA' (INV-F6RBAC){X}")
    print(f"{B}{'=' * 88}{X}")

    section_static()

    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]
    try:
        AT = login(ADMIN)
    except Exception as e:                                       # noqa: BLE001
        print(f"{R}  backend/login admin tidak siap: {e}{X}")
        return 1
    try:
        ST = login(STAFF)
    except Exception as e:                                       # noqa: BLE001
        check("A-0 akun staf berlingkup toko tersedia "
              "(staffmkt@dewiaditya.id — seed_role_accounts)", False, str(e)[:90])
        ST = None

    staff = db.users.find_one({"email": STAFF["email"]}, {"_id": 0, "id": 1, "name": 1})
    accs = list(db.marketing_platform_accounts.find(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "assigned_staff": 1}
    ).sort("account_name", 1).limit(2))
    if not (ST and staff and len(accs) >= 2):
        check("A-0 lingkungan uji siap (staf + 2 toko aktif)", False,
              f"staf={bool(staff)} toko={len(accs)}")
    else:
        mine, other = accs[0], accs[1]
        before = list(mine.get("assigned_staff") or [])
        before_other = list(other.get("assigned_staff") or [])
        reason = f"uji {MARK} lingkup toko sesi 9"

        # ── PAS B0: staf dilepas dari SEMUA toko dulu ────────────────────────
        # Keadaan "nol toko" adalah bukti lingkup yang paling tidak bisa dibantah,
        # DAN keadaan nyata staf baru sebelum SPV meng-assign (layar kosong yang
        # wajib menjelaskan dirinya). Daftar toko yang dilepas dicatat supaya
        # dipulihkan persis seperti semula sesudah gate.
        held = list(db.marketing_platform_accounts.find(
            {"assigned_staff": staff["id"]}, {"_id": 0, "id": 1, "assigned_staff": 1}))
        restore = {a["id"]: list(a.get("assigned_staff") or []) for a in held}
        codes = [set_staff(AT, a["id"],
                           [s for s in (a.get("assigned_staff") or []) if s != staff["id"]],
                           f"uji {MARK} lepas semua toko dulu (pas B0)").status_code
                 for a in held]
        check("A-0z staf uji dilepas dari SEMUA toko dulu (pas 'nol toko')",
              all(c == 200 for c in codes),
              f"{len(held)} toko dilepas · HTTP {codes or '—'}")
        proved = section_lists_zero(AT, ST)
        section_sweep(AT, ST)

        r = requests.post(f"{BASE}/api/marketing/account-assign/{mine['id']}",
                          headers={"Authorization": f"Bearer {AT}"}, timeout=60,
                          json={"staff_ids": [staff["id"]], "reason": reason})
        check("A-0 assign SATU toko ke staf uji (lewat API resmi) ⇒ 200",
              r.status_code == 200, f"HTTP {r.status_code}")
        # Toko PEMBANDING harus benar-benar BUKAN milik staf itu — kalau tidak,
        # "403 toko lain" tidak menguji apa pun (jebakan nyata: sesi sebelumnya
        # sempat meng-assign toko ini ke staf yang sama).
        if staff["id"] in before_other:
            r2 = requests.post(f"{BASE}/api/marketing/account-assign/{other['id']}",
                               headers={"Authorization": f"Bearer {AT}"}, timeout=60,
                               json={"staff_ids": [s for s in before_other
                                                   if s != staff["id"]],
                                     "reason": f"uji {MARK} lepas toko pembanding"})
                                                                        # noqa: E128
            check("A-0b toko pembanding dilepas dari staf uji ⇒ 200",
                  r2.status_code == 200, f"HTTP {r2.status_code}")
        # token staf harus diambil ULANG? tidak perlu: lingkup dibaca dari DB tiap request
        try:
            section_guard(AT, ST, mine, other)
            section_lists(AT, ST, proved)
            section_changelog(AT, ST, mine, reason)
        finally:
            if not keep:
                # pulihkan daftar staf SEMUA toko yang disentuh gate + buang HANYA
                # jejak bertanda gate (aturan A-2e sesi #8b: gate tidak boleh
                # memusnahkan bukti "siapa memegang toko ini").
                restore[mine["id"]] = before
                restore.setdefault(other["id"], before_other)
                for acc_id, staff_list in restore.items():
                    set_staff(AT, acc_id, staff_list, f"pulihkan {MARK} sesudah gate")
                n = db.marketing_change_log.delete_many(
                    {"reason": {"$regex": MARK}}).deleted_count
                print(f"    dibersihkan: daftar staf {len(restore)} toko dipulihkan · "
                      f"{n} jejak bertanda {MARK} dihapus (jejak LAIN tidak disentuh)")

    ok = sum(1 for _, c, _ in RES if c)
    bad = [n for n, c, _ in RES if not c]
    print(f"\n{B}{'-' * 88}{X}")
    print(f"  INV-F6RBAC: {len(RES)} diperiksa — {len(bad)} temuan")
    if bad:
        print(f"  {R}{B}✗ INV-F6RBAC MERAH{X}")
        for n in bad:
            print(f"    {R}{n}{X}")
    else:
        print(f"  {G}{B}✓ INV-F6RBAC HIJAU{X} — {ok}/{len(RES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
