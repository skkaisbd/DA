"""F3 — pengencang "sambungan longgar" Tech Pack R&D.

Empat masalah yang ditutup (proposal §2.3 / §C):

C1  Baris BOM punya DUA sumber kebenaran: input teks `material` **dan** dropdown
    master `material_id`. Baris yang tidak tertaut master **tidak punya harga &
    faktor konversi satuan** ⇒ HPP-nya salah TANPA peringatan. Sekarang setiap
    baris diberi `master_linked` + `master_link_note`, dan dokumen membawa
    `bom_unlinked_count` supaya layar bisa memasang badge peringatan.

C2  `fabric_consumption.size` bisa menyimpang dari daftar ukuran style.
    Sekarang ditandai `size_off_list` bila di luar `size_list`.

C3  **INTI**: `measurements[].values` dikunci STRING nama kolom. Ganti nama kolom
    (`XL` → `EXTRA L`) membuat seluruh nilai kolom itu YATIM tanpa peringatan.
    Sekarang `size_columns` = `[{col_id, label}]` dengan `col_id` **stabil**, dan
    `values` dikunci `col_id`. Ganti label tidak lagi menyentuh nilai.
    Migrasi bersifat **idempoten** dan **tidak menghilangkan apa pun**: bentuk
    lama disimpan sebagai `values_legacy`, kunci yang tidak dikenali disimpan di
    `orphan_values` (bukan dibuang), dan `values_count_in/out` dicatat agar bisa
    dibuktikan gate.

C4/C5  Dimensi warna: `colorways[]` pada tech pack, serta kolom warna pada
    `fabrics[]` dan `bom_items[]` — semuanya merujuk master `rahaza_colors`.
"""
import uuid


def _new_col_id() -> str:
    return f'col_{uuid.uuid4().hex[:10]}'


def _s(v) -> str:
    return str(v if v is not None else '').strip()


# ══════════════════════════════════════════════════════════════════════════════
# C3 — size_columns: [{col_id, label}] + measurements berkunci col_id
# ══════════════════════════════════════════════════════════════════════════════

def normalize_size_columns(raw) -> list:
    """Terima `['S','M']` (lama) ATAU `[{col_id,label}]` (baru) → selalu bentuk baru.

    IDEMPOTEN: `col_id` yang sudah ada **dipertahankan**, jadi menjalankan ini
    berulang kali tidak pernah memutus tautan nilai measurement.
    """
    out, seen = [], set()
    for item in (raw or []):
        if isinstance(item, dict):
            label = _s(item.get('label') or item.get('name') or item.get('col') or item.get('size'))
            col_id = _s(item.get('col_id'))
        else:
            label, col_id = _s(item), ''
        if not label and not col_id:
            continue
        if not col_id:
            col_id = _new_col_id()
        if col_id in seen:
            col_id = _new_col_id()
        seen.add(col_id)
        out.append({'col_id': col_id, 'label': label or col_id})
    return out


def normalize_measurements(raw_rows, size_columns) -> tuple:
    """Kunci `values` dengan `col_id`. Tidak ada nilai yang boleh hilang.

    Return `(rows, stats)` dengan `stats = {values_in, values_out, orphans}`.
    Aturan pemetaan per baris:
      1. kunci yang SUDAH `col_id`      → dipakai apa adanya
      2. kunci = LABEL kolom (case-ins) → dipetakan ke `col_id`-nya
      3. kunci lain (kolom sudah hilang)→ disimpan di `orphan_values` (TIDAK dibuang)
      4. baris lama pipih `{point,S,M}` → dibaca sebagai kunci label
    """
    cols = size_columns or []
    id_set = {c['col_id'] for c in cols}
    by_label = {}
    for c in cols:
        by_label.setdefault(_s(c['label']).upper(), c['col_id'])

    reserved = {'point', 'values', 'values_legacy', 'orphan_values', 'note', 'notes',
                'tolerance', 'unit', 'seq'}

    rows, v_in, v_out, orphan_total = [], 0, 0, 0
    for r in (raw_rows or []):
        r = dict(r or {})
        source = {}
        if isinstance(r.get('values'), dict) and r['values']:
            source = dict(r['values'])
        elif isinstance(r.get('values_legacy'), dict) and r['values_legacy']:
            source = dict(r['values_legacy'])
        else:
            # baris lama pipih: {point, 'S': '50', 'M': '52', ...}
            source = {k: v for k, v in r.items()
                      if k not in reserved and not isinstance(v, (dict, list))}

        # Nilai cadangan yang dikirim ulang klien HARUS ikut dihitung, kalau tidak
        # nilai kolom yang dihapus akan hilang pada penyimpanan berikutnya.
        # Kuncinya tidak akan cocok kolom mana pun ⇒ jatuh ke `orphans` lagi,
        # KECUALI kolomnya dibuat ulang dengan label yang sama (lalu nilainya pulih).
        if isinstance(r.get('orphan_values'), dict):
            for k, v in r['orphan_values'].items():
                source.setdefault(k, v)

        source = {k: v for k, v in source.items() if v not in (None, '')}
        v_in += len(source)

        values, orphans = {}, {}
        for k, v in source.items():
            key = _s(k)
            if key in id_set:
                values[key] = v
            elif key.upper() in by_label:
                values[by_label[key.upper()]] = v
            else:
                orphans[key] = v

        v_out += len(values)
        orphan_total += len(orphans)

        row = {
            'point': _s(r.get('point')),
            'values': values,
            # bentuk lama disimpan supaya bisa diverifikasi / dipulihkan
            'values_legacy': (r.get('values_legacy')
                              if isinstance(r.get('values_legacy'), dict) and r.get('values_legacy')
                              else source),
        }
        if orphans:
            # kolomnya sudah dihapus dari size_columns — nilainya TIDAK dibuang
            row['orphan_values'] = orphans
        if r.get('note'):
            row['note'] = r['note']
        rows.append(row)

    return rows, {'values_in': v_in, 'values_out': v_out, 'orphans': orphan_total}


def measurement_columns_for_view(tp: dict) -> list:
    """Kolom siap-tampil `[{col_id,label}]` untuk sebuah dokumen tech pack."""
    return normalize_size_columns(tp.get('size_columns'))


# ══════════════════════════════════════════════════════════════════════════════
# C4/C5 — dimensi warna (colorways, warna kain, warna baris BOM)
# ══════════════════════════════════════════════════════════════════════════════

async def normalize_colorways(db, raw) -> list:
    """`colorways[]` tech pack → daftar warna master (dedupe, urutan dijaga)."""
    from routes.dewi_rnd_colors import _resolve_color
    out, seen = [], set()
    for item in (raw or []):
        if isinstance(item, str):
            item = {'name': item}
        doc, _created = await _resolve_color(db, item or {}, allow_create=True)
        if not doc or doc['id'] in seen:
            continue
        seen.add(doc['id'])
        out.append({
            'color_id': doc['id'], 'code': doc.get('code') or '',
            'name': doc.get('name') or '', 'hex': doc.get('hex') or '#CCCCCC',
        })
    return out


async def attach_row_color(db, row: dict) -> dict:
    """Lengkapi kolom warna satu baris (`fabrics[]` / `bom_items[]`) dari master."""
    from routes.dewi_rnd_colors import _resolve_color
    has_hint = any(_s(row.get(k)) for k in ('color_id', 'color_code', 'color_name', 'color'))
    if not has_hint:
        row.setdefault('color_id', '')
        row.setdefault('color_code', '')
        row.setdefault('color_name', '')
        row.setdefault('color_hex', '')
        return row
    doc, _created = await _resolve_color(db, {
        'color_id': row.get('color_id'),
        'code': row.get('color_code'),
        'name': row.get('color_name') or row.get('color'),
    }, allow_create=False)
    if doc:
        row['color_id'] = doc['id']
        row['color_code'] = doc.get('code') or ''
        row['color_name'] = doc.get('name') or ''
        row['color_hex'] = doc.get('hex') or '#CCCCCC'
    else:
        # warna diketik bebas & belum ada di master → tetap disimpan, tapi ditandai
        row.setdefault('color_id', '')
        row['color_name'] = _s(row.get('color_name') or row.get('color'))
        row['color_hex'] = _s(row.get('color_hex')) or ''
        row['color_off_master'] = bool(row['color_name'])
    return row


# ══════════════════════════════════════════════════════════════════════════════
# C2 — fabric_consumption.size harus ikut daftar ukuran style
# ══════════════════════════════════════════════════════════════════════════════

def normalize_fabric_consumption(raw, size_list) -> tuple:
    """Tandai baris konsumsi yang ukurannya di luar `size_list` (§2.3.2)."""
    allowed = {_s(s).upper() for s in (size_list or [])}
    out, off = [], 0
    for r in (raw or []):
        row = dict(r or {})
        size = _s(row.get('size'))
        row['size'] = size
        if size and allowed and size.upper() not in allowed:
            row['size_off_list'] = True
            off += 1
        else:
            row.pop('size_off_list', None)
        out.append(row)
    return out, off
