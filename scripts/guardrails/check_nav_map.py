#!/usr/bin/env python3
"""INV-NAV-01 — Navigation map integrity (portalNav.js ⇄ moduleRegistry.js ⇄ komponen).

Kelas masalah dicegah (pelajaran IA v2 round-2 + audit IA Produksi 2026-07-26):
  NAV-EMPTY   section tanpa item sama sekali  -> HIGH (render "Belum ada item").
  NAV-SINGLE  section beranggota 1 item       -> HIGH (langgar MECE/cohesion — "kategori
              tak bisa dibagi jadi 1 bagian"). Ini lint utama yang diminta owner.
  NAV-GHOST   menu id yang TIDAK ada di MODULE_REGISTRY (kecuali isHeader) -> HIGH
              (klik menu -> layar kosong).
  NAV-DUP     moduleId duplikat DALAM satu portal -> HIGH (highlight/section ambigu).
              (Duplikat LINTAS-portal DIBOLEHKAN — shortcut yang disengaja.)
  NAV-DEPTH   kedalaman IA > 4 (Portal→Section→Group→Item) -> MED.
  NAV-FIELD   item tanpa id/label -> HIGH.

  ── FASE IA-D (2026-07-26) — 5 guard anti-kambuh, lahir dari cacat NYATA ──────
  NAV-FLAT    section memakai `groups` (Portal→Section→Group→Item = 3 tingkat
              di sidebar) -> HIGH. Owner memutuskan navigasi WAJIB datar 2 tingkat
              (Section → Pintu) supaya "cari pintu" tidak perlu membuka 2 lapis.
  NAV-MAX     section > MAX_ITEMS(8) pintu -> HIGH. Sebelum restrukturisasi,
              Portal Produksi menumpuk 12 pintu dalam SATU section — daftar sepanjang
              itu tidak bisa dipindai mata (Miller's Law) dan menyembunyikan pintu mati.
  NAV-LABEL   label memakai tanda kurung / lebih dari 3 kata / HURUF BESAR SEMUA ->
              HIGH. Aturan penamaan yang disetujui owner (IA v2.1): akronim boleh,
              tanda kurung tidak ("Tutup PO (Closure)" → "Tutup PO").
  NAV-DUPTAB  pintu yang isinya PERSIS komponen sebuah TAB di pintu lain pada portal
              yang sama -> HIGH. Cacat nyata: "Estimasi AI" (prod-ai-insights) =
              tab "AI Insight" di Dashboard Produksi ⇒ dua pintu, satu isi.
  NAV-DEADCALL komponen di balik sebuah pintu memanggil endpoint yang TIDAK ADA di
              backend -> HIGH. Cacat nyata (2026-07-26): pintu "Monitoring Produksi"
              memanggil `apiGet('/production-monitoring-v2')` — 0 route di backend,
              HTTP 404, error ditelan `catch → setData([])` ⇒ layar "Tidak ada data"
              padahal DB berisi 3 production_jobs. Gate kontrak
              (`verify_fe_be_contract.py`) BUTA pada kasus ini karena hanya memindai
              literal yang memuat `/api/`, sementara wrapper `apiGet()` menambahkan
              `/api` sendiri (frontend/src/lib/api.js:44) — 38 path FE lolos radar.

READ-ONLY. Parser memakai Node (mengevaluasi PORTAL_NAV yang sebenarnya, bukan regex rapuh):
icon di-null-kan, import lucide dibuang, `export` distrip, lalu JSON.stringify(PORTAL_NAV).

Usage:
    cd /app && python scripts/guardrails/check_nav_map.py [--strict]
    cd /app && python scripts/guardrails/check_nav_map.py --selftest   # bukti tiap guard MERAH
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from gr_common import Report, FE_SRC, all_routes, norm_path, api_base  # noqa: E402
import fe_static  # noqa: E402

NAV_JS = FE_SRC / "components/erp/portal-shell/portalNav.js"
REGISTRY_JS = FE_SRC / "components/erp/moduleRegistry.js"
MAX_DEPTH = 4
MAX_ITEMS = 8          # NAV-MAX — batas pintu per section
MAX_LABEL_WORDS = 3    # NAV-LABEL — "Terima FG dari CMT" (4 kata) tetap lolos: lihat _label_words


def extract_portal_nav() -> dict:
    """Bundle portalNav.js via esbuild (juga = compile check), lalu require untuk membaca
    PORTAL_NAV yang SEBENARNYA (bukan regex rapuh). Fungsi ikon di-drop oleh JSON.stringify."""
    frontend = FE_SRC.parent  # /app/frontend
    rel = str(NAV_JS.relative_to(frontend))
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as f:
        bundle = f.name
    try:
        build = subprocess.run(
            ["esbuild", rel, "--bundle", "--format=cjs", f"--outfile={bundle}", "--log-level=warning"],
            cwd=str(frontend), capture_output=True, text=True, timeout=90)
        if build.returncode != 0:
            raise RuntimeError(f"esbuild gagal (portalNav.js tak kompilasi): {build.stderr[:500]}")
        out = subprocess.run(
            ["node", "-e", f"const m=require('{bundle}');process.stdout.write(JSON.stringify(m.PORTAL_NAV))"],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise RuntimeError(f"gagal membaca PORTAL_NAV: {out.stderr[:400]}")
        return json.loads(out.stdout.strip())
    finally:
        Path(bundle).unlink(missing_ok=True)


def extract_registry_ids() -> set:
    """Ambil semua key moduleId dari object MODULE_REGISTRY."""
    txt = REGISTRY_JS.read_text(encoding="utf-8")
    m = re.search(r"export const MODULE_REGISTRY\s*=\s*\{", txt)
    body = txt[m.end():] if m else txt
    # key berupa 'foo-bar': atau "foo-bar":  di awal (whitespace) baris
    return set(re.findall(r"""(?m)^\s*['"]([A-Za-z0-9_\-]+)['"]\s*:""", body))


# ═════════════════════════════════════════════════════════════════════════════
# Peta moduleId → BERKAS komponen (untuk NAV-DUPTAB & NAV-DEADCALL)
# ═════════════════════════════════════════════════════════════════════════════
_ENTRY_RE = re.compile(r"""(?m)^\s*['"]([A-Za-z0-9_\-]+)['"]\s*:\s*([^,\n]+)""")
_REDIRECT_RE = re.compile(r"""makeRedirect\(\s*['"]([A-Za-z0-9_\-]+)['"]""")
_WRAPPED_RE = re.compile(r"""(?:withProps|makeModuleWithTab|withScope)\(\s*([A-Za-z_$][\w$]*)""")
_PLAIN_RE = re.compile(r"""^([A-Za-z_$][\w$]*)\s*$""")


def registry_component_map() -> dict:
    """moduleId → {'file': "berkas::export"|None, 'redirect': targetId|None}.

    `makeRedirect('x')` disamakan dengan pintu x (deep-link lama tetap hidup, tapi
    isinya = modul x) sehingga NAV-DUPTAB tak tertipu oleh alias.
    """
    txt = fe_static.read(REGISTRY_JS)
    imports = fe_static.resolve_imports(REGISTRY_JS)
    m = re.search(r"export const MODULE_REGISTRY\s*=\s*\{", txt)
    body = txt[m.end():] if m else txt
    out = {}
    for mid, raw in _ENTRY_RE.findall(body):
        raw = raw.strip().rstrip(",").strip()
        red = _REDIRECT_RE.search(raw)
        if red:
            out[mid] = {"file": None, "redirect": red.group(1)}
            continue
        wm = _WRAPPED_RE.search(raw) or _PLAIN_RE.match(raw)
        name = wm.group(1) if wm else None
        out[mid] = {"file": imports.get(name), "redirect": None}
    return out


def module_file(mid: str, cmap: dict, _depth: int = 0):
    """Identitas komponen efektif sebuah moduleId (mengikuti rantai makeRedirect)."""
    info = cmap.get(mid)
    if not info or _depth > 5:
        return None
    if info["redirect"]:
        return module_file(info["redirect"], cmap, _depth + 1)
    return info["file"]


# ═════════════════════════════════════════════════════════════════════════════
# NAV-DEADCALL — pencocokan path FE ↔ route backend
# ═════════════════════════════════════════════════════════════════════════════
def _loc(f) -> str:
    """Lokasi berkas untuk laporan (relatif ke frontend/src bila memungkinkan)."""
    try:
        return f"src/{Path(f).relative_to(FE_SRC)}"
    except ValueError:
        return str(f)


def backend_shapes():
    """(shapes, authoritative) — daftar shape route backend.

    OpenAPI runtime adalah SATU-SATUNYA daftar yang lengkap: ekstraksi AST melewatkan
    router yang prefix-nya dipasang saat `include_router()` atau yang variabel routernya
    bukan `router` (terbukti: 1655 path OpenAPI vs 2109 AST, tapi `/api/assets/loans`
    HANYA ada di OpenAPI). Keduanya digabung supaya route yang belum ter-mount
    (mis. di-guard flag) tetap dianggap ada.

    Bila backend mati → `authoritative=False` dan temuan NAV-DEADCALL diturunkan jadi
    WARN: menuduh endpoint "tidak ada" berdasar parser yang kita tahu tidak lengkap
    adalah cara tercepat membuat guard ini diabaikan orang.
    """
    shapes = {norm_path(r["path"]) for r in all_routes()}
    authoritative = False
    try:
        import urllib.request
        with urllib.request.urlopen(api_base() + "/api/openapi.json", timeout=30) as r:
            spec = json.loads(r.read().decode("utf-8", "replace"))
        shapes |= {norm_path(p) for p in spec.get("paths", {})}
        authoritative = True
    except Exception:  # noqa: BLE001 — backend mati saat gate statik dijalankan
        pass
    return shapes, authoritative


def _segs(shape: str):
    return [s for s in shape.strip("/").split("/") if s]


def _seg_match(route_seg: str, fe_seg: str) -> bool:
    """Cocokkan SATU segmen path FE dengan segmen route backend.

    Segmen campuran literal+dinamis (mis. `production-tracking{}` dari
    `` `/production-tracking${qs}` ``) HARUS tetap mencocokkan bagian literalnya.
    Versi pertama guard ini menganggap segmen apa pun yang memuat `{}` sebagai
    wildcard penuh — akibatnya `/api/production-monitoring-v2{}` (endpoint yang
    TIDAK ADA, cacat A) dianggap cocok dengan sembarang route 2-segmen dan guard
    tetap hijau. Persis kelas kesalahan `_seg_match` simetris yang dulu
    menyembunyikan 48 temuan (lihat catatan FASE 21 di scripts/gate.sh).
    """
    if route_seg == fe_seg or route_seg == "{}" or fe_seg == "{}":
        return True
    if "{}" in fe_seg:
        pos = 0
        for part in [p for p in fe_seg.split("{}") if p]:
            idx = route_seg.find(part, pos)
            if idx == -1:
                return False
            pos = idx + len(part)
        return True
    return False


def path_exists(shape: str, shapes: set, allow_prefix: bool = False) -> bool:
    """Cocokkan shape FE dengan daftar route backend (sadar path-param & segmen dinamis).

    Longgar SECARA SENGAJA pada segmen yang memuat `{}` (hasil `${var}`): tujuannya
    menangkap path yang JELAS-JELAS tidak ada (typo / endpoint dihapus), bukan
    berdebat soal komposisi path dinamis — itu urusan triase manusia di gate kontrak.
    """
    if shape in shapes:
        return True
    if allow_prefix and any(s.startswith(shape.rstrip("/") + "/") for s in shapes):
        return True   # konstanta basis (`const BASE = `${API}/api/x`` lalu `${BASE}/y`)
    fs = _segs(shape)
    # segmen terakhir campuran literal+dinamis (mis. `/prod/cmt-receipts{}` dari
    # `` `/prod/cmt-receipts${params}` `` yang sebenarnya query string) → coba tanpa sufiks
    if fs and fs[-1].endswith("{}") and fs[-1] != "{}":
        if path_exists("/" + "/".join(fs[:-1] + [fs[-1][:-2]]), shapes, allow_prefix):
            return True
    for cand in shapes:
        cs = _segs(cand)
        if len(cs) != len(fs):
            continue
        if all(_seg_match(c, f) for c, f in zip(cs, fs)):
            return True
    return False


# ═════════════════════════════════════════════════════════════════════════════
# Aturan label
# ═════════════════════════════════════════════════════════════════════════════
_STOPWORDS = {"dari", "ke", "dan", "&", "/", "per", "di"}


def _label_words(label: str) -> int:
    """Hitung kata BERMAKNA (kata sambung tidak dihitung: 'Terima FG dari CMT' = 3)."""
    return len([w for w in re.split(r"\s+", label.strip()) if w and w.lower() not in _STOPWORDS])


def label_problems(label: str) -> list:
    probs = []
    if "(" in label or ")" in label:
        probs.append("memakai tanda kurung")
    if _label_words(label) > MAX_LABEL_WORDS:
        probs.append(f"> {MAX_LABEL_WORDS} kata bermakna")
    letters = [c for c in label if c.isalpha()]
    if len(letters) >= 6 and all(c.isupper() for c in letters):
        probs.append("HURUF BESAR SEMUA")
    return probs


def section_items(section):
    """(real_items, header_items) — real=navigable (punya id, bukan isHeader)."""
    items = []
    if section.get("items"):
        items = section["items"]
    elif section.get("groups"):
        for g in section["groups"]:
            items += g.get("items", [])
    real = [it for it in items if not it.get("isHeader")]
    headers = [it for it in items if it.get("isHeader")]
    return real, headers


# ═════════════════════════════════════════════════════════════════════════════
# Pemeriksaan
# ═════════════════════════════════════════════════════════════════════════════
def check_portal_alias(rep: Report):
    """NAV-ALIAS — NAMA portal yang tertulis di layar harus sah dipakai di URL.

    Cacat NYATA (2026-08-13): portal yang di layar bernama **"Marketing"** ber-id
    `toko` (warisan "Toko Online"). Tautan yang ditulis manusia —
    `?portal=marketing&module=marketing-targets` — id-nya tidak dikenal, lalu
    aplikasi diam-diam menampilkan portal terakhir yang tersimpan **tanpa satu pun
    pesan**. Dari sudut pandang pemakai: "menu Target & Budget hilang". Satu sesi
    uji penuh habis karena ini.

    Aturannya sederhana dan bisa dipertanggungjawabkan: untuk setiap portal, NAMA
    yang dibaca pemakai (`PORTAL_LABEL`, huruf kecil, spasi→'-') harus sama dengan
    id-nya ATAU terdaftar di `PORTAL_ID_ALIASES` (App.js).
    """
    nav_js = NAV_JS.read_text(errors="ignore")
    app_js = (FE_SRC / "App.js").read_text(errors="ignore")
    labels = dict(re.findall(r"^\s*([a-z_]+):\s*'([^']+)',", nav_js, re.M))
    # PORTAL_LABEL berada di blok pertama; batasi ke blok tersebut
    m = re.search(r"export const PORTAL_LABEL\s*=\s*\{(.*?)\};", nav_js, re.S)
    if m:
        labels = dict(re.findall(r"([a-z_]+):\s*'([^']+)'", m.group(1)))
    am = re.search(r"const PORTAL_ID_ALIASES\s*=\s*\{(.*?)\};", app_js, re.S)
    aliases = {}
    if am:
        for k, v in re.findall(r"'?([A-Za-z_-]+)'?:\s*'([a-z]+)'", am.group(1)):
            aliases[k.lower()] = v
    if not labels:
        rep.add("MED", "NAV-ALIAS", "PORTAL_LABEL tidak bisa dibaca — alias portal tidak diperiksa")
        return
    for pid, label in labels.items():
        rep.bump()
        key = label.strip().lower().replace(" ", "-").replace("/", "-")
        # bentuk yang wajar ditulis manusia: nama penuh, tanpa awalan "portal-",
        # dan kata pertamanya (mis. "RnD & Desain" → "rnd").
        cands = {key, key.replace("portal-", "", 1), key.split("-")[0]}
        if pid in cands or any(aliases.get(c) == pid for c in cands):
            continue
        rep.add("HIGH", "NAV-ALIAS",
                f"portal '{label}' ber-id '{pid}': nama yang dibaca pemakai tidak bisa "
                f"dipakai di URL (?portal={key}). Tambahkan alias di PORTAL_ID_ALIASES "
                f"(App.js) supaya tautan yang ditulis manusia tidak mendarat di portal lain "
                f"tanpa pesan.", loc="frontend/src/App.js")



def check_nav(rep: Report, nav: dict, registry: set):
    """NAV-EMPTY/SINGLE/GHOST/DUP/DEPTH/FIELD/FLAT/MAX/LABEL + NAV-SOLO."""
    for portal, pdata in nav.items():
        sections = pdata.get("sections", [])
        seen = {}  # moduleId -> section label (deteksi duplikat dalam portal)
        # ── NAV-SOLO (IA v4) — pola "portal satu pintu" ──────────────────────
        # Portal ber-flag `singleDoor: true` SENGAJA hanya punya 1 pintu; PortalShell
        # menyembunyikan sidebar + pill karena navigasi ditangani tab di dalam modul
        # (kasus nyata: Portal Manajemen Aset — 4 pintu lama = 1 komponen beda tab).
        # Flag ini MEMBEBASKAN portal dari NAV-SINGLE, tapi sebagai gantinya
        # DIWAJIBKAN benar-benar 1 section × 1 pintu; kalau tidak, flag-nya bohong
        # dan user kehilangan menu (pintu ke-2 dst. jadi tak terjangkau).
        single_door = bool(pdata.get("singleDoor"))
        if single_door:
            rep.bump()
            total = sum(len(section_items(s)[0]) for s in sections)
            if len(sections) != 1 or total != 1:
                rep.add("HIGH", "NAV-SOLO",
                        f"[{portal}] `singleDoor: true` tapi punya {len(sections)} section / "
                        f"{total} pintu — sidebar disembunyikan ⇒ pintu selain yang pertama "
                        f"TIDAK BISA diklik. Hapus flag atau sisakan 1 pintu.")
        for sec in sections:
            rep.bump()
            label = sec.get("label", "?")
            real, _headers = section_items(sec)
            if len(real) == 0:
                rep.add("HIGH", "NAV-EMPTY", f"[{portal}] section '{label}' KOSONG (0 item navigable)")
            elif len(real) == 1 and not single_door:
                rep.add("HIGH", "NAV-SINGLE",
                        f"[{portal}] section '{label}' hanya 1 item ('{real[0].get('id')}') "
                        f"— langgar MECE/cohesion; gabung ke section lain")
            # NAV-MAX
            if len(real) > MAX_ITEMS:
                rep.add("HIGH", "NAV-MAX",
                        f"[{portal}] section '{label}' berisi {len(real)} pintu (> {MAX_ITEMS}) "
                        f"— pecah jadi 2 section supaya bisa dipindai mata")
            # NAV-FLAT / depth
            depth = 2  # portal(L1 implisit) -> section(L1) -> item(L2); grup -> +1
            if sec.get("groups"):
                depth = 3
                rep.add("HIGH", "NAV-FLAT",
                        f"[{portal}] section '{label}' memakai `groups` (3 tingkat) "
                        f"— navigasi wajib DATAR: Section → Pintu. Naikkan tiap group jadi section.")
                for g in sec["groups"]:
                    for p in label_problems(g.get("label", "")):
                        rep.add("HIGH", "NAV-LABEL",
                                f"[{portal}] group '{g.get('label')}' {p}")
            if depth > MAX_DEPTH:
                rep.add("MED", "NAV-DEPTH", f"[{portal}] section '{label}' kedalaman {depth} > {MAX_DEPTH}")
            # label section: hanya larangan tanda kurung (section boleh HURUF BESAR & >3 kata)
            if "(" in label or ")" in label:
                rep.add("HIGH", "NAV-LABEL", f"[{portal}] label section '{label}' memakai tanda kurung")
            # item-level checks
            for it in real:
                mid = it.get("id")
                if not mid or not it.get("label"):
                    rep.add("HIGH", "NAV-FIELD", f"[{portal}] section '{label}': item tanpa id/label ({it})")
                    continue
                for p in label_problems(it["label"]):
                    rep.add("HIGH", "NAV-LABEL",
                            f"[{portal}] pintu '{mid}' label '{it['label']}' {p}")
                if mid in seen:
                    rep.add("HIGH", "NAV-DUP",
                            f"[{portal}] moduleId '{mid}' duplikat (section '{seen[mid]}' & '{label}')")
                else:
                    seen[mid] = label
                if mid not in registry:
                    rep.add("HIGH", "NAV-GHOST",
                            f"[{portal}] menu '{mid}' (section '{label}') TIDAK ada di MODULE_REGISTRY "
                            f"— klik → layar kosong")


def check_duptab(rep: Report, nav: dict, cmap: dict):
    """NAV-DUPTAB — pintu yang isinya = TAB pintu lain di portal yang sama."""
    for portal, pdata in nav.items():
        items = []
        for sec in pdata.get("sections", []):
            real, _ = section_items(sec)
            items += [it for it in real if it.get("id")]
        file_of = {}
        for it in items:
            f = module_file(it["id"], cmap)
            if f:
                file_of[it["id"]] = f
        by_file = {}
        for mid, f in file_of.items():
            by_file.setdefault(str(f), []).append(mid)
        for mid, f in file_of.items():
            rep.bump()
            for _tabname, tabfile in fe_static.tab_components(fe_static.comp_path(f)).items():
                owners = [o for o in by_file.get(str(tabfile), []) if o != mid]
                for owner in owners:
                    rep.add("HIGH", "NAV-DUPTAB",
                            f"[{portal}] pintu '{owner}' isinya = TAB di pintu '{mid}' "
                            f"({Path(tabfile).name}) — satu isi dua pintu; buang salah satu")


def check_deadcall(rep: Report, nav: dict, cmap: dict, shapes: set, authoritative: bool = True):
    """NAV-DEADCALL — komponen pintu memanggil endpoint yang tak ada di backend."""
    sev = "HIGH" if authoritative else "WARN"
    if not authoritative:
        rep.add("INFO", "NAV-DEADCALL-DEGRADED",
                "backend mati → daftar route dari AST saja (tak lengkap); "
                "temuan NAV-DEADCALL diturunkan jadi WARN. Jalankan ulang saat backend hidup.")
    for portal, pdata in nav.items():
        for sec in pdata.get("sections", []):
            real, _ = section_items(sec)
            for it in real:
                mid = it.get("id")
                f = module_file(mid, cmap) if mid else None
                if not f:
                    continue
                # komponen pintu + komponen tab di dalamnya (hub) ikut diperiksa
                targets = {f: mid,
                           **{tf: mid for tf in fe_static.tab_components(fe_static.comp_path(f)).values()}}
                for comp, owner in targets.items():
                    tf = fe_static.comp_path(comp)
                    for raw, line, kind in fe_static.api_calls(tf):
                        shape = norm_path(raw)
                        if "$" in shape:
                            # template dengan ekspresi majemuk (`${a ? b : c}`) — periksa
                            # sebagai PREFIX saja; sisanya urusan gate kontrak.
                            prefix = shape.split("$")[0].rstrip("/")
                            if len(prefix.strip("/").split("/")) < 2:
                                continue
                            rep.bump()
                            if not any(s == prefix or s.startswith(prefix + "/") for s in shapes):
                                rep.add(sev, "NAV-DEADCALL",
                                        f"[{portal}] pintu '{owner}' memanggil {prefix}… — "
                                        f"TIDAK ADA route backend berawalan itu (404 senyap)",
                                        f"{_loc(tf)}:{line}")
                            continue
                        rep.bump()
                        if not path_exists(shape, shapes, allow_prefix=(kind == "template")):
                            rep.add(sev, "NAV-DEADCALL",
                                    f"[{portal}] pintu '{owner}' memanggil {shape} — "
                                    f"TIDAK ADA route backend (404 senyap)",
                                    f"{_loc(tf)}:{line}")


# ═════════════════════════════════════════════════════════════════════════════
# SELFTEST — bukti tiap guard benar-benar MERAH pada pelanggaran sintetis
# ═════════════════════════════════════════════════════════════════════════════
def selftest(quiet: bool = False) -> int:
    """Jalankan tiap aturan atas contoh pelanggaran; guard yang tidak menyala = gagal.

    Kenapa perlu: guard yang tak pernah dibuktikan merah adalah guard yang
    (diam-diam) mati. Pelanggaran dibuat SINTETIS di memori/berkas sementara,
    jadi repo tidak disentuh.
    """
    if not quiet:
        print("\n\033[1m=== SELFTEST GUARD NAVIGASI (harus MERAH semua) ===\033[0m")
    results = []

    def codes(fn, *a):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf if quiet else sys.stdout):
            rep = Report("SELFTEST", "sintetis", block_sev=())
            rep.write = lambda: None  # jangan timpa laporan asli
            fn(rep, *a)
        return {f.code for f in rep.findings}

    # NAV-FLAT + NAV-LABEL(group) + NAV-MAX + NAV-SINGLE + NAV-GHOST + NAV-DUP
    nav_flat = {"x": {"sections": [{"label": "A", "groups": [
        {"label": "Piutang (AR)", "items": [{"id": "m1", "label": "Satu"}, {"id": "m2", "label": "Dua"}]}]}]}}
    results.append(("NAV-FLAT", "NAV-FLAT" in codes(check_nav, nav_flat, {"m1", "m2"})))
    results.append(("NAV-LABEL(group kurung)", "NAV-LABEL" in codes(check_nav, nav_flat, {"m1", "m2"})))

    nav_max = {"x": {"sections": [{"label": "A", "items": [
        {"id": f"m{i}", "label": f"Pintu {i}"} for i in range(MAX_ITEMS + 1)]}]}}
    results.append(("NAV-MAX", "NAV-MAX" in codes(check_nav, nav_max, {f"m{i}" for i in range(MAX_ITEMS + 1)})))

    nav_label = {"x": {"sections": [{"label": "A", "items": [
        {"id": "m1", "label": "Tutup PO (Closure)"},
        {"id": "m2", "label": "Laporan Rekap Harian Gudang Pusat"},
        {"id": "m3", "label": "LAPORAN"}]}]}}
    lab = codes(check_nav, nav_label, {"m1", "m2", "m3"})
    results.append(("NAV-LABEL(kurung/panjang/kapital)", "NAV-LABEL" in lab))

    # NAV-DUPTAB & NAV-DEADCALL — pakai berkas sementara di dalam FE_SRC
    tmpdir = Path(tempfile.mkdtemp(prefix="navguard_selftest_"))
    try:
        (tmpdir / "TabChild.jsx").write_text(
            "export default function TabChild(){ return <div/>; }\n", encoding="utf-8")
        (tmpdir / "HubParent.jsx").write_text(
            "import React, { lazy } from 'react';\n"
            f"import HubTabs from '{FE_SRC}/components/erp/hubs/HubTabs';\n"
            "const TabChild = lazy(() => import('./TabChild'));\n"
            "export default function HubParent(p){ return <HubTabs hubId='h' "
            "tabs={[{ key:'a', label:'A', Component: TabChild }]} {...p} />; }\n", encoding="utf-8")
        (tmpdir / "DeadCaller.jsx").write_text(
            f"import {{ apiGet }} from '{FE_SRC}/lib/api';\n"
            "export default function DeadCaller(){ apiGet('/endpoint-yang-tidak-pernah-ada-x9'); "
            "return <div/>; }\n", encoding="utf-8")
        fe_static.read.cache_clear()
        fe_static.resolve_imports.cache_clear()

        cmap = {
            "hub": {"file": f"{tmpdir / 'HubParent.jsx'}::default", "redirect": None},
            "child": {"file": f"{tmpdir / 'TabChild.jsx'}::default", "redirect": None},
            "dead": {"file": f"{tmpdir / 'DeadCaller.jsx'}::default", "redirect": None},
        }
        nav_dup = {"x": {"sections": [{"label": "A", "items": [
            {"id": "hub", "label": "Hub"}, {"id": "child", "label": "Anak"}]}]}}
        results.append(("NAV-DUPTAB", "NAV-DUPTAB" in codes(check_duptab, nav_dup, cmap)))

        nav_dead = {"x": {"sections": [{"label": "A", "items": [
            {"id": "dead", "label": "Mati"}, {"id": "child", "label": "Anak"}]}]}}
        shapes, authoritative = backend_shapes()
        results.append(("NAV-DEADCALL", "NAV-DEADCALL" in codes(check_deadcall, nav_dead, cmap, shapes, authoritative)))
    finally:
        for p in tmpdir.glob("*"):
            p.unlink()
        tmpdir.rmdir()
        fe_static.read.cache_clear()
        fe_static.resolve_imports.cache_clear()

    if quiet:
        return [name for name, fired in results if not fired]
    print()
    ok = True
    green, red, reset, bold = "\033[92m", "\033[91m", "\033[0m", "\033[1m"
    for name, fired in results:
        mark = green + "MERAH OK" + reset if fired else red + "DIAM (GAGAL)" + reset
        print(f"    {mark}  {name}")
        ok = ok and fired
    verdict = (green + bold + "SELFTEST LULUS") if ok else (red + bold + "SELFTEST GAGAL")
    print(f"\n  {verdict} — {sum(1 for _, f in results if f)}/{len(results)} guard menyala{reset}\n")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="buktikan tiap guard MERAH pada pelanggaran sintetis")
    ap.add_argument("--no-selftest", action="store_true",
                    help="lewati self-test bawaan (hanya untuk debugging)")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    rep = Report("INV-NAV-01",
                 "Integritas navigasi (single/ghost/duplikat/depth + flat/max/label/duptab/deadcall)",
                 block_sev=("CRIT", "HIGH"))

    try:
        nav = extract_portal_nav()
    except Exception as e:  # noqa: BLE001
        rep.add("CRIT", "NAV-PARSE", f"gagal parse PORTAL_NAV: {e}")
        return rep.finish()
    registry = extract_registry_ids()
    rep.bump(len(registry))

    # Guard yang tak pernah dibuktikan merah = guard yang diam-diam mati (pelajaran
    # gate lint & _seg_match). Jadi self-test sintetis dijalankan SETIAP kali gate jalan.
    if not args.no_selftest:
        silent = selftest(quiet=True)
        if silent:
            rep.add("CRIT", "NAV-GUARD-DEAD",
                    f"guard berikut TIDAK menyala pada pelanggaran sintetis: {', '.join(silent)} "
                    f"— perbaiki guard-nya dulu, hasil HIJAU tidak bisa dipercaya")
        else:
            print(f"    self-test guard: {6} guard terbukti MERAH pada pelanggaran sintetis.")

    check_nav(rep, nav, registry)
    check_portal_alias(rep)

    cmap = registry_component_map()
    check_duptab(rep, nav, cmap)
    shapes, authoritative = backend_shapes()
    check_deadcall(rep, nav, cmap, shapes, authoritative)

    n_sections = sum(len(p.get("sections", [])) for p in nav.values())
    n_items = sum(len(section_items(s)[0]) for p in nav.values() for s in p.get("sections", []))
    print(f"    {len(nav)} portal, {n_sections} section, {n_items} pintu, "
          f"{len(registry)} id di registry diperiksa.")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
