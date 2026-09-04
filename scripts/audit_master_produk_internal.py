#!/usr/bin/env python3
"""audit_master_produk_internal.py — INVENTARIS FIELD **Master Produk Internal DA**
dan pemetaannya ke ENDPOINT yang memakainya.

═══════════════════════════════════════════════════════════════════════════════
KENAPA ALAT INI ADA (dan bukan dibaca dengan mata)
═══════════════════════════════════════════════════════════════════════════════
Pertanyaan "field apa saja yang ada di master data produk, dan dipakai endpoint
mana saja" TIDAK bisa dijawab dari isi database, karena:

  * DB demo sering **tertinggal** dari kode — saat audit ini dibuat,
    `rahaza_models` hanya punya 7 kunci (`code`, `name`, `description`, …)
    padahal `POST /api/rahaza/models` menulis 13 kunci (`category`,
    `material_kg_per_pcs`, `bundle_size`, `sop_steps`, …). Menjawab dari DB akan
    **menyembunyikan** field yang sudah ada di kode tapi belum pernah terisi.
  * Sebaliknya, dokumen WARISAN bisa punya kunci yang **sudah tidak ditulis lagi**
    (mis. alias `yarn_*` yang penulisannya dihentikan di FASE 11). Menjawab dari
    kode saja akan menyembunyikan kunci yang masih nyata ada di dokumen lama.

Jadi jawaban yang benar = **gabungan** keduanya, dan setiap field ditandai
sumbernya (KODE / DB / KEDUANYA). Itulah yang dicetak alat ini.

Bahayanya kalau ditebak: menambah field baru di atas peta yang salah berarti
menulis data yang **tidak pernah dibaca siapa pun** (fitur mati), atau menabrak
nama yang sudah dipakai jalur lain (mis. `image_paths` = hasil UPLOAD berkas vs
`reference_images` = URL eksternal — dua field berbeda yang mudah tertukar).

═══════════════════════════════════════════════════════════════════════════════
CARA KERJA (dan batasnya — dibaca sebelum dipercaya)
═══════════════════════════════════════════════════════════════════════════════
1. Semua `*.py` backend dipindai (kecuali `__pycache__`, `_archive`, `tests`).
2. Per berkas: prefix `APIRouter(prefix=...)` + semua dekorator
   `@router.<method>("<path>")` dicatat beserta nomor barisnya.
3. Setiap sentuhan koleksi target (`db.<koleksi>`) dipetakan ke **endpoint
   terdekat di atasnya**, lalu jenis operasinya diklasifikasikan
   (insert / update / find / aggregate / count / delete).
4. Nama field diambil dari teks statement itu. Kalau statement-nya
   `insert_one(doc)` / `update_one(..., {"$set": upd})` — yaitu dokumennya
   dibangun di variabel — alat ini **melacak balik** definisi `doc = {` /
   `upd = {` di fungsi yang sama. Tanpa langkah ini, `create_model` akan
   tampak "tidak menulis field apa pun".
5. Frontend (`frontend/src`) digrep untuk tiap field agar kelihatan mana yang
   benar-benar sampai ke LAYAR dan mana yang hanya hidup di backend.

**BATAS:** ini analisis STATIK berbasis regex, bukan pelacak tipe. Field yang
namanya dibentuk dinamis (`doc[f"{x}_qty"]`) tidak akan terlihat. Karena itu
angkanya harus dibaca sebagai "minimal sekian", bukan "pasti hanya sekian".

Pakai::

    python3 scripts/audit_master_produk_internal.py              # ringkasan
    python3 scripts/audit_master_produk_internal.py --field code # 1 field saja
    python3 scripts/audit_master_produk_internal.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BE = os.path.join(APP, 'backend')
FE = os.path.join(APP, 'frontend', 'src')

G, R, Y, B, C, X, BOLD = ('\033[92m', '\033[91m', '\033[93m', '\033[94m',
                          '\033[96m', '\033[0m', '\033[1m')

# ─────────────────────────────────────────────────────────────────────────────
# Koleksi yang MEMBENTUK "master produk internal DA".
# Urutannya = urutan cerita: produk → varian(SKU) → sumbu varian → resep bahan.
# `products`/`product_variants` IKUT dipindai justru karena sudah DEPRECATED —
# supaya kelihatan hitam-putih bahwa pintu itu tidak boleh dipakai lagi.
# ─────────────────────────────────────────────────────────────────────────────
COLLECTIONS: dict[str, str] = {
    'rahaza_models': 'MASTER PRODUK INTERNAL (model/artikel) — sumber kebenaran',
    'rahaza_model_variants': 'VARIAN produk = SKU per (model × warna × size)',
    'rahaza_sizes': 'Sumbu SIZE (master ukuran)',
    'rahaza_colors': 'Sumbu WARNA (palet master)',
    'rahaza_boms': 'BOM / resep bahan per model (+size)',
    'products': '[DEPRECATED] master produk legacy',
    'product_variants': '[DEPRECATED] varian produk legacy',
}

OP_PATTERNS = [
    ('insert', re.compile(r'\.(insert_one|insert_many)\s*\(')),
    ('update', re.compile(r'\.(update_one|update_many|find_one_and_update|replace_one)\s*\(')),
    ('delete', re.compile(r'\.(delete_one|delete_many)\s*\(')),
    ('count', re.compile(r'\.(count_documents|estimated_document_count)\s*\(')),
    ('aggregate', re.compile(r'\.aggregate\s*\(')),
    ('read', re.compile(r'\.(find_one|find|distinct)\s*\(')),
]

DECORATOR = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*[\'"]([^\'"]*)[\'"]')
PREFIX = re.compile(r'APIRouter\(\s*prefix\s*=\s*[\'"]([^\'"]*)[\'"]')
# Beberapa berkas TIDAK membuat router sendiri, tapi mengimpornya dari modul
# bersama (mis. `from routes.dewi_rnd_shared import router`). Tanpa menelusuri
# ini, path-nya tercetak tanpa prefix (`POST /styles/...` padahal aslinya
# `POST /api/dewi/rnd/styles/...`) — dan path yang salah di dokumen audit lebih
# berbahaya daripada tidak ada dokumen sama sekali.
IMPORTED_ROUTER = re.compile(r'from\s+routes\.(\w+)\s+import\s+([^\n]*\brouter\b)')
FUNC = re.compile(r'^\s*(async\s+def|def)\s+(\w+)')
QUOTED = re.compile(r'[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]')
VAR_ARG = re.compile(r'\.(?:insert_one|insert_many|replace_one)\s*\(\s*(\w+)\s*[,)]')
SET_VAR = re.compile(r'[\'"]\$(?:set|setOnInsert)[\'"]\s*:\s*(\w+)\s*[,}]')

# Kata yang muncul di dalam statement tapi BUKAN nama field.
NOT_FIELDS = {
    '_id', 'id_', 'true', 'false', 'none', 'utf', 'jpg', 'jpeg', 'png', 'webp',
    'gif', 'application', 'json', 'image', 'i', 'db', 'self', 'request', 'user',
    'str', 'int', 'float', 'bool', 'list', 'dict', 'set',
}
MONGO_OPS = re.compile(r'^\$')

# Nama yang terlalu UMUM: jumlah kemunculannya di frontend tidak berarti apa-apa
# (hampir setiap entitas punya `id`/`name`/`status`), jadi angkanya TIDAK dicetak
# — mencetaknya hanya akan membuat kolom LAYAR tampak meyakinkan padahal kosong
# maknanya. Yang penting justru field SPESIFIK: kalau LAYAR-nya 0, field itu
# memang tidak pernah sampai ke pengguna.
GENERIC_FIELDS = {'id', 'name', 'code', 'status', 'active', 'created_at',
                  'updated_at', 'created_by', 'created_by_name', 'notes',
                  'description', 'category', 'model_id', 'size_id', 'color_id'}


def iter_py_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ('__pycache__', '_archive', 'node_modules', 'tests', 'legacy')]
        for fn in sorted(filenames):
            if fn.endswith('.py'):
                yield os.path.join(dirpath, fn)


def balanced_block(lines: list[str], start: int, max_lines: int = 60) -> tuple[str, int]:
    """Ambil teks dari `start` sampai tanda kurung/kurawal seimbang."""
    depth, buf = 0, []
    for i in range(start, min(start + max_lines, len(lines))):
        buf.append(lines[i])
        depth += lines[i].count('(') + lines[i].count('{') + lines[i].count('[')
        depth -= lines[i].count(')') + lines[i].count('}') + lines[i].count(']')
        if depth <= 0 and i > start - 1:
            return '\n'.join(buf), i
    return '\n'.join(buf), min(start + max_lines, len(lines)) - 1


def find_var_literal(lines: list[str], before: int, var: str) -> str:
    """Lacak balik definisi `var = {` (dokumen dibangun di variabel).

    Tanpa ini, `doc = {...}` lalu `insert_one(doc)` akan tampak tidak menulis
    field apa pun — dan itulah pola yang dipakai `POST /api/rahaza/models`.
    """
    pat = re.compile(rf'^\s*{re.escape(var)}\s*=\s*[{{(]')
    upd = re.compile(rf'^\s*{re.escape(var)}\s*\[')
    text = []
    for i in range(before, max(before - 120, -1), -1):
        if pat.match(lines[i]):
            blk, _ = balanced_block(lines, i)
            text.append(blk)
            break
    # tangkap juga `upd['x'] = ...` / `body['x'] = ...` setelah definisinya
    for i in range(max(before - 120, 0), before + 1):
        if upd.match(lines[i]):
            text.append(lines[i])
    return '\n'.join(text)


def fields_from_text(text: str, exclude: set[str] | None = None) -> set[str]:
    """Ambil nama field dari teks statement.

    Dua saringan yang WAJIB ada, karena tanpanya hasilnya menyesatkan:
    * **nama KOLEKSI** ikut tertangkap (jendela statement sering menyebut
      `db.rahaza_sizes` dll) ⇒ dibuang lewat `exclude`;
    * **NILAI literal** ikut tertangkap (mis. `body.get("category") or "Sweater"`
      membuat "Sweater" tampak sebagai field) ⇒ dibuang dengan aturan: field di
      backend ini SELALU snake_case huruf kecil.
    """
    out = set()
    for m in QUOTED.finditer(text):
        k = m.group(1)
        if MONGO_OPS.match(k) or k.lower() in NOT_FIELDS or len(k) < 2:
            continue
        if k != k.lower():          # ada huruf kapital ⇒ nilai, bukan nama field
            continue
        if exclude and k in exclude:
            continue
        out.add(k)
    return out


def _read(path: str) -> str | None:
    """Baca berkas teks; `None` kalau tidak terbaca (biner/izin/hilang)."""
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return None


def _imported_prefix(blob: str) -> str:
    """Prefix router yang diimpor dari modul bersama (`from routes.X import router`).

    Dipakai berkas seperti `dewi_rnd_styles.py` yang memakai router milik
    `dewi_rnd_shared.py` (`prefix="/api/dewi/rnd"`).
    """
    for m in IMPORTED_ROUTER.finditer(blob):
        mod = os.path.join(BE, 'routes', f'{m.group(1)}.py')
        sub = _read(mod)
        if sub is None:
            continue
        pm = PREFIX.search(sub)
        if pm:
            return pm.group(1)
    return ''


def scan_backend() -> tuple[dict, dict, dict]:
    """→ (field_map, endpoint_map, coll_endpoints)"""
    field_map: dict[str, dict[str, dict[str, set]]] = {
        c: defaultdict(lambda: defaultdict(set)) for c in COLLECTIONS}
    coll_endpoints: dict[str, set] = {c: set() for c in COLLECTIONS}
    endpoint_map: dict[str, str] = {}

    coll_res = {c: re.compile(rf'\bdb\.{re.escape(c)}\b') for c in COLLECTIONS}

    for path in iter_py_files(BE):
        raw = _read(path)
        if raw is None:
            continue
        lines = raw.split('\n')
        blob = '\n'.join(lines)
        if not any(c in blob for c in COLLECTIONS):
            continue

        pm = PREFIX.search(blob)
        prefix = pm.group(1) if pm else _imported_prefix(blob)
        decos: list[tuple[int, str, str]] = []
        funcs: list[tuple[int, str]] = []
        for i, ln in enumerate(lines):
            d = DECORATOR.search(ln)
            if d:
                decos.append((i, d.group(1).upper(), (prefix + d.group(2)) or prefix))
            f = FUNC.match(ln)
            if f:
                funcs.append((i, f.group(2)))

        rel = os.path.relpath(path, APP)
        # Nama koleksi yang disebut di berkas ini — supaya tidak terhitung field.
        colls_here = set(re.findall(r'\bdb\.(\w+)', blob))
        for coll, rx in coll_res.items():
            for i, ln in enumerate(lines):
                if not rx.search(ln):
                    continue
                op = 'touch'
                for name, opx in OP_PATTERNS:
                    if opx.search(ln):
                        op = name
                        break
                # endpoint terdekat DI ATAS baris ini
                ep = None
                for dl, meth, p in decos:
                    if dl < i:
                        ep = f'{meth} {p}'
                    else:
                        break
                fn = None
                for fl, name in funcs:
                    if fl < i:
                        fn = name
                    else:
                        break
                label = ep or f'(bukan endpoint) {fn or "?"}'
                if ep:
                    endpoint_map[ep] = rel
                coll_endpoints[coll].add((label, rel))

                block, _ = balanced_block(lines, i)
                text = block
                vm = VAR_ARG.search(block)
                if vm:
                    text += '\n' + find_var_literal(lines, i, vm.group(1))
                sm = SET_VAR.search(block)
                if sm:
                    text += '\n' + find_var_literal(lines, i, sm.group(1))
                for f in fields_from_text(text, exclude=colls_here):
                    field_map[coll][f][op].add(f'{label}  ·  {rel}:{i + 1}')
    return field_map, endpoint_map, coll_endpoints


def scan_frontend(fields: set[str]) -> dict[str, set]:
    hits: dict[str, set] = defaultdict(set)
    if not os.path.isdir(FE):
        return hits
    pats = {f: re.compile(rf'\b{re.escape(f)}\b') for f in fields}
    for dirpath, dirnames, filenames in os.walk(FE):
        dirnames[:] = [d for d in dirnames if d not in ('node_modules', '_archive')]
        for fn in filenames:
            if not fn.endswith(('.js', '.jsx', '.ts', '.tsx')):
                continue
            p = os.path.join(dirpath, fn)
            blob = _read(p)
            if blob is None:
                continue
            for f, rx in pats.items():
                if rx.search(blob):
                    hits[f].add(os.path.relpath(p, APP))
    return hits


def db_keys() -> dict[str, dict[str, int]]:
    """Kunci yang BENAR-BENAR ada di dokumen (menangkap field warisan)."""
    out: dict[str, dict[str, int]] = {c: {} for c in COLLECTIONS}
    try:
        from pymongo import MongoClient
        cli = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'),
                          serverSelectionTimeoutMS=3000)
        db = cli[os.environ.get('DB_NAME', 'test_database')]
        for c in COLLECTIONS:
            counter: dict[str, int] = defaultdict(int)
            for doc in db[c].find({}, limit=500):
                for k in doc:
                    if k != '_id':
                        counter[k] += 1
            out[c] = dict(counter)
        cli.close()
    except Exception as e:                                    # noqa: BLE001
        print(f'  {Y}! DB tidak terbaca ({e.__class__.__name__}) — '
              f'inventaris hanya dari KODE{X}')
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--field', help='tampilkan hanya field ini')
    ap.add_argument('--collection', help='tampilkan hanya koleksi ini')
    ap.add_argument('--json', dest='json_out', help='tulis hasil ke berkas JSON')
    a = ap.parse_args()

    print(f'{B}{"=" * 100}{X}')
    print(f'  {BOLD}INVENTARIS FIELD — MASTER PRODUK INTERNAL DA{X}  '
          f'(kode: backend/  ·  layar: frontend/src/)')
    print(f'{B}{"=" * 100}{X}')

    fmap, _emap, cends = scan_backend()
    dbk = db_keys()
    all_fields = {f for c in fmap for f in fmap[c]}
    fe = scan_frontend(all_fields)

    report: dict[str, dict] = {}
    for coll, desc in COLLECTIONS.items():
        if a.collection and a.collection != coll:
            continue
        fields = fmap[coll]
        in_db = dbk.get(coll) or {}
        if not fields and not in_db:
            continue
        print(f'\n{C}{BOLD}▶ {coll}{X}  — {desc}')
        print(f'  {"":2}dokumen di DB: {sum(1 for _ in [0]) and ""}'
              f'{max(in_db.values()) if in_db else 0}  ·  '
              f'field dari KODE: {len(fields)}  ·  field di DB: {len(in_db)}')
        print(f'  {"-" * 96}')
        print(f'  {"FIELD":34s}{"SUMBER":10s}{"TULIS":6s}{"BACA":5s}{"LAYAR":6s}')
        print(f'  {"-" * 96}')
        rows = {}
        for f in sorted(set(fields) | set(in_db)):
            if a.field and a.field != f:
                continue
            ops = fields.get(f, {})
            w = sum(len(ops.get(k, ())) for k in ('insert', 'update'))
            r = sum(len(ops.get(k, ())) for k in ('read', 'aggregate', 'count', 'touch'))
            src = ('KEDUANYA' if f in fields and f in in_db
                   else 'KODE' if f in fields else 'DB-saja')
            col = G if src == 'KEDUANYA' else (Y if src == 'KODE' else R)
            fe_n = len(fe.get(f, ()))
            if f in GENERIC_FIELDS:
                fe_cell = f'{B}umum{X}'
            elif fe_n:
                fe_cell = f'{G}{fe_n}{X}'
            else:
                fe_cell = f'{R}0{X}'
            print(f'  {f:34s}{col}{src:10s}{X}{w:<6d}{r:<5d}{fe_cell}')
            rows[f] = {
                'sumber': src, 'tulis': sorted(
                    x for k in ('insert', 'update') for x in ops.get(k, ())),
                'baca': sorted(
                    x for k in ('read', 'aggregate', 'count', 'touch') for x in ops.get(k, ())),
                'layar': sorted(fe.get(f, ())), 'dokumen_di_db': in_db.get(f, 0),
            }
        report[coll] = {'deskripsi': desc, 'fields': rows,
                        'endpoints': sorted(f'{lbl}  ·  {src}' for lbl, src in cends[coll])}

        if a.field:
            for f, d in rows.items():
                print(f'\n  {BOLD}{f}{X} — TULIS:')
                for x in d['tulis'] or ['    (tidak ada)']:
                    print(f'      · {x}')
                print(f'  {BOLD}{f}{X} — BACA/FILTER:')
                for x in d['baca'] or ['    (tidak ada)']:
                    print(f'      · {x}')
                print(f'  {BOLD}{f}{X} — LAYAR:')
                for x in d['layar'] or ['    (TIDAK ADA DI FRONTEND)']:
                    print(f'      · {x}')

    if not a.field:
        for coll in report:
            print(f'\n{C}{BOLD}▶ ENDPOINT yang menyentuh {coll}{X} '
                  f'({len(report[coll]["endpoints"])})')
            for e in report[coll]['endpoints']:
                print(f'    · {e}')

    print(f'\n{Y}Catatan: analisis STATIK (regex). Field bernama dinamis tidak '
          f'terlihat ⇒ baca angkanya sebagai "minimal", bukan "pasti hanya".{X}')
    print(f'{Y}"LAYAR 0" = field itu tidak pernah disebut frontend ⇒ kandidat '
          f'field mati ATAU memang khusus backend.{X}')

    if a.json_out:
        with open(a.json_out, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f'\n{G}✓ JSON ditulis: {a.json_out}{X}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
