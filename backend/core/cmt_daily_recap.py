"""core/cmt_daily_recap.py — SSOT **Rekap Harian CMT** ("vendor mana yang belum diisi hari ini").

═══════════════════════════════════════════════════════════════════════════════
MASALAH NYATA
═══════════════════════════════════════════════════════════════════════════════
Setelah pintu "Input Vendor CMT" ada, staf DA memang BISA mengisi portal vendor
atas nama vendor — tetapi tidak ada yang memberitahu **vendor mana yang belum
dikerjakan hari ini**. Dengan puluhan vendor CMT, satu vendor yang terlewat
berarti progress hari itu tidak masuk, dan karena **tagihan CMT dihitung dari
progress produksi**, uangnya tidak bisa ditagih/diverifikasi.

Modul ini menjawab satu pertanyaan operasional: *"per vendor, pekerjaan harian
mana yang sudah terisi dan mana yang belum?"*

═══════════════════════════════════════════════════════════════════════════════
KEPUTUSAN OWNER (2026-08-08, lanjutan sesi Portal CMT Override)
═══════════════════════════════════════════════════════════════════════════════
1c. Bentuknya **checklist per tugas**, bukan lampu hijau/merah tunggal — satu
    baris per vendor, kolom per jenis pekerjaan, supaya kelihatan KURANG APA.
2a. Isinya **SEMUA vendor aktif** di master CMT (`vendor_partners`). Vendor yang
    memang tidak punya pekerjaan tetap tampil, ditandai "tidak ada pekerjaan" —
    supaya tidak ada yang hilang dari daftar tanpa penjelasan.
3a. Data yang **diisi vendor sendiri** dari portalnya IKUT dihitung "sudah diisi"
    (yang penting datanya masuk), tetapi sumbernya ditandai (`vendor`/`staf DA`).
4a. Rekap = **tampilan pertama** pintu "Input Vendor CMT".
5.  Tambahan: lihat tanggal lain · export Excel/PDF · kirim reminder.

═══════════════════════════════════════════════════════════════════════════════
KENAPA SATU BERKAS (SSOT), BUKAN DIHITUNG DI MASING-MASING ENDPOINT
═══════════════════════════════════════════════════════════════════════════════
Ada TIGA pengguna angka yang sama: layar rekap, berkas export (Excel/PDF), dan
pemilih sasaran tombol "kirim reminder". Kalau masing-masing menghitung sendiri,
suatu hari Excel akan bilang 5 vendor merah sementara layarnya bilang 3 — dan
tidak ada yang tahu mana yang benar. Semua memanggil :func:`build_recap`.

═══════════════════════════════════════════════════════════════════════════════
BATAS HARI = WIB (bukan UTC) — ini bukan detail kosmetik
═══════════════════════════════════════════════════════════════════════════════
Jam sistem container **UTC**. Kalau batas hari diambil dari `datetime.now()`
polos, maka selama **07 jam setiap hari** (00:00–07:00 WIB) rekap "hari ini"
sebenarnya menampilkan **hari sebelumnya** — persis jam staf produksi mulai
kerja. Semua rentang di sini memakai :func:`utils.waktu.wib_day_bounds_utc`.

═══════════════════════════════════════════════════════════════════════════════
DEFINISI (hasil AUDIT jalur tulis + tipe data di Mongo, bukan tebakan)
═══════════════════════════════════════════════════════════════════════════════
Untuk setiap tugas ada dua angka:

* ``waiting``    — pekerjaan yang MENUNGGU (kalau > 0 dan hari ini kosong ⇒ ✗)
* ``done_today`` — bukti pekerjaan itu dikerjakan pada tanggal rekap (⇒ ✓)

┌────────────┬──────────────────────────────┬────────────────────────────────────┐
│ Tugas      │ waiting                      │ done_today (field waktu)           │
├────────────┼──────────────────────────────┼────────────────────────────────────┤
│ terima     │ shipment `status='Sent'`     │ `Received` + `received_at` hari ini│
│ inspeksi   │ `Received` & belum Inspected │ inspeksi `created_at` hari ini     │
│ progress   │ job `In Progress`            │ `progress_date` hari ini           │
│ kirim      │ Σproduced − Σshipped (pcs)   │ `dispatch_date` hari ini           │
│ reminder   │ reminder `status='pending'`  │ `response_date` hari ini           │
└────────────┴──────────────────────────────┴────────────────────────────────────┘

Empat status kolom (sengaja EMPAT, bukan dua):

* ``done``    ✓  ada bukti hari ini, tidak ada sisa
* ``partial`` ✓+ ada bukti hari ini, TAPI masih ada sisa (jujur: jangan bilang
              "beres" kalau masih ada surat jalan menganggur)
* ``pending`` ✗  ada pekerjaan menunggu, hari ini belum ada bukti
* ``none``    —  memang tidak ada pekerjaan jenis ini

═══════════════════════════════════════════════════════════════════════════════
JEBAKAN YANG DITUTUP DI SINI
═══════════════════════════════════════════════════════════════════════════════
1. ``production_progress`` **tidak menyimpan** ``vendor_id`` (menempel ke
   ``job_id``). Menyaringnya dengan ``vendor_id`` menghasilkan NOL selamanya —
   kolom Progress akan abadi ✗ padahal setorannya masuk. Vendor diresolusi lewat
   ``production_jobs`` (pola sama dengan panel audit ``_vendor_filter``).
2. **Reminder rekap tidak boleh membuat vendor abadi-merah.** Tombol "kirim
   reminder" melahirkan dokumen ``reminders`` berstatus ``pending``; kalau ikut
   dihitung, kolom "Balas Reminder" langsung ✗ pada hari yang sama dan vendor
   tidak akan pernah bisa hijau. Reminder ``reminder_type='daily_recap'`` dengan
   ``recap_date`` = tanggal rekap DIKECUALIKAN dari ``waiting`` tanggal itu
   (hari berikutnya tetap dihitung — reminder tak dibalas memang pekerjaan).
3. **Agregasi per koleksi, bukan per vendor.** Jumlah query konstan (±10) walau
   vendor bertambah jadi ratusan; kalau per-vendor, layar pagi akan menembak
   Mongo ratusan kali.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from core.production_job_lifecycle import needs_closed_at_backfill, was_open_at
from utils.waktu import today_wib, wib_day_bounds_utc

# ── Definisi kolom (SSOT dipakai layar, export, dan pemilih reminder) ────────
# `module` = id tab di CMTOverridePortalModule ⇒ klik chip langsung membuka
# modul yang tepat (bukan selalu Dashboard). Kalau id tab berubah, ubah DI SINI.
TASKS: list[dict] = [
    {'key': 'terima', 'label': 'Terima Material', 'short': 'Terima',
     'module': 'receiving', 'unit': 'surat jalan'},
    {'key': 'inspeksi', 'label': 'Inspeksi Material', 'short': 'Inspeksi',
     'module': 'inspeksi', 'unit': 'kiriman'},
    {'key': 'progress', 'label': 'Progress Produksi', 'short': 'Progress',
     'module': 'progress', 'unit': 'job'},
    {'key': 'kirim', 'label': 'Kirim ke DA / Buyer', 'short': 'Kirim',
     'module': 'buyer-shipments', 'unit': 'pcs'},
    {'key': 'reminder', 'label': 'Balas Reminder', 'short': 'Reminder',
     'module': 'reminders', 'unit': 'reminder'},
]
TASK_KEYS = [t['key'] for t in TASKS]

# Jenis reminder yang lahir dari tombol "kirim reminder" pada rekap ini.
RECAP_REMINDER_TYPE = 'daily_recap'

_STATE_ORDER = {'pending': 0, 'partial': 1, 'done': 2, 'none': 3}


# ═══════════════════════════════════════════════════════════════════════════
# Util kecil
# ═══════════════════════════════════════════════════════════════════════════
def parse_day(raw: str | None) -> date:
    """``'YYYY-MM-DD'`` → :class:`date`. Kosong/salah format → hari ini (WIB).

    Sengaja TIDAK melempar error untuk input kosong: layar memanggil tanpa
    parameter untuk "hari ini", dan itu jalur paling sering dipakai.
    """
    if not raw:
        return today_wib()
    try:
        return datetime.strptime(str(raw).strip()[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError("Parameter date harus format YYYY-MM-DD (mis. 2026-08-08).") from exc


def _missing(field: str) -> dict:
    """Filter "field ini tidak ada atau null".

    Dipakai untuk dokumen LAMA yang lahir sebelum field waktunya ada. Tanpa ini,
    rekap akan menuduh pekerjaan "masih menunggu" hanya karena dokumen tuanya
    tidak punya stempel waktu — dan staf akan mengejar pekerjaan yang sudah beres.
    """
    return {'$or': [{field: {'$exists': False}}, {field: None}]}


def _state(done_today: int, waiting: int) -> str:
    if done_today > 0:
        return 'partial' if waiting > 0 else 'done'
    return 'pending' if waiting > 0 else 'none'


def _source(done_today: int, staff_n: int) -> str:
    """``'staff'`` / ``'vendor'`` / ``'mixed'`` / ``''`` (keputusan 3a)."""
    if done_today <= 0:
        return ''
    if staff_n >= done_today:
        return 'staff'
    if staff_n <= 0:
        return 'vendor'
    return 'mixed'


async def _group_count(db, coll: str, match: dict, key: str = 'vendor_id',
                       staff_field: str | None = None, qty_field: str | None = None) -> dict:
    """``{key_value: {'n': int, 'staff': int, 'qty': int}}`` dalam SATU query."""
    group: dict = {'_id': f'${key}', 'n': {'$sum': 1}}
    if staff_field:
        group['staff'] = {'$sum': {'$cond': [{'$eq': [f'${staff_field}', True]}, 1, 0]}}
    if qty_field:
        group['qty'] = {'$sum': {'$ifNull': [f'${qty_field}', 0]}}
    rows = await db[coll].aggregate([{'$match': match}, {'$group': group}]).to_list(None)
    return {r['_id']: {'n': r.get('n', 0), 'staff': r.get('staff', 0), 'qty': r.get('qty', 0)}
            for r in rows if r.get('_id')}


# ═══════════════════════════════════════════════════════════════════════════
# Info akun portal per vendor — SSOT dipakai rekap DAN daftar vendor override
# ═══════════════════════════════════════════════════════════════════════════
async def vendor_account_info(db, vendor_ids: list[str]) -> dict:
    """``{vendor_id: {accounts, active_accounts, has_active, last_login_at}}``.

    Dipakai dua layar (daftar vendor + rekap harian) untuk peringatan dobel input
    (keputusan owner 5a). Satu tempat supaya keduanya tidak pernah beda jawaban.
    """
    if not vendor_ids:
        return {}
    accounts = await db.users.find(
        {'cmt_vendor_id': {'$in': vendor_ids}},
        {'_id': 0, 'cmt_vendor_id': 1, 'email': 1, 'name': 1, 'role': 1,
         'is_active': 1, 'status': 1, 'last_login_at': 1},
    ).to_list(1000)

    out: dict = {}
    for a in accounts:
        out.setdefault(a['cmt_vendor_id'], []).append(a)

    info: dict = {}
    for vid in vendor_ids:
        accs = out.get(vid, [])
        active = [a for a in accs
                  if a.get('is_active') is not False and a.get('status', 'active') == 'active']
        logins = [a.get('last_login_at') for a in active if a.get('last_login_at')]
        info[vid] = {
            'accounts': accs,
            'active_accounts': active,
            'has_active': len(active) > 0,
            'last_login_at': max(logins) if logins else None,
        }
    return info


# ═══════════════════════════════════════════════════════════════════════════
# INTI
# ═══════════════════════════════════════════════════════════════════════════
async def prefetch_context(db, include_inactive: bool = False) -> dict:
    """Baca SEKALI semua data master yang tidak bergantung tanggal.

    KENAPA ADA: Rekap Mingguan memanggil :func:`build_recap` **7 kali**. Tanpa ini,
    daftar vendor, akun portal, seluruh `production_jobs`, dan seluruh
    `buyer_shipments` dibaca ulang 7 kali untuk hasil yang persis sama — layar
    pagi jadi 7× lebih mahal tanpa alasan. Dengan konteks bersama, yang berulang
    hanya agregasi yang MEMANG bergantung tanggal.
    """
    q = {} if include_inactive else {
        '$and': [{'is_active': {'$ne': False}}, {'active': {'$ne': False}}]
    }
    partners = await db.vendor_partners.find(
        q, {'_id': 0, 'id': 1, 'name': 1, 'code': 1, 'contact_name': 1,
            'contact_phone': 1, 'is_active': 1, 'active': 1},
    ).sort('name', 1).to_list(500)
    if not partners:
        return {'partners': [], 'pids': [], 'acc_info': {}, 'jobs': [],
                'job_vendor': {}, 'job_ids': [], 'ship_vendor': {},
                'ship_staff': {}, 'ship_ids': []}

    pids = [p['id'] for p in partners]
    acc_info = await vendor_account_info(db, pids)

    jobs = await db.production_jobs.find(
        {'vendor_id': {'$in': pids}},
        # `closed_at` WAJIB ikut: tanpanya "job jalan pada tanggal X" hanya bisa
        # ditebak dari status SEKARANG, dan rekap tanggal lampau akan memaafkan
        # kelalaian yang sudah terjadi begitu job-nya ditutup.
        {'_id': 0, 'id': 1, 'vendor_id': 1, 'status': 1, 'created_at': 1,
         'closed_at': 1, 'closed_at_estimated': 1},
    ).to_list(None)
    job_vendor = {j['id']: j['vendor_id'] for j in jobs if j.get('id')}

    bshipments = await db.buyer_shipments.find(
        {'vendor_id': {'$in': pids}},
        {'_id': 0, 'id': 1, 'vendor_id': 1, 'entered_by_staff': 1},
    ).to_list(None)

    return {
        'partners': partners,
        'pids': pids,
        'acc_info': acc_info,
        'jobs': jobs,
        'job_vendor': job_vendor,
        'job_ids': list(job_vendor),
        'ship_vendor': {s['id']: s['vendor_id'] for s in bshipments if s.get('id')},
        'ship_staff': {s['id']: s.get('entered_by_staff') is True
                       for s in bshipments if s.get('id')},
        'ship_ids': [s['id'] for s in bshipments if s.get('id')],
    }


async def build_recap(db, day: date | None = None, include_inactive: bool = False,
                      ctx: dict | None = None) -> dict:
    """Rekap harian seluruh vendor CMT untuk satu tanggal kalender **WIB**.

    ``ctx`` = hasil :func:`prefetch_context` (opsional). Dipakai Rekap Mingguan
    supaya data master tidak dibaca ulang untuk setiap hari.

    Bentuk hasil (dipakai apa adanya oleh layar, export, dan reminder)::

        {
          'date': '2026-08-08', 'is_today': True,
          'tasks': TASKS,
          'summary': {...},
          'rows': [{'vendor_id','vendor_name','status','pending_count',
                    'tasks': {'terima': {'state','waiting','done_today',...}, ...}}]
        }
    """
    day = day or today_wib()
    start, end = wib_day_bounds_utc(day)
    day_str = day.strftime('%Y-%m-%d')
    in_day = {'$gte': start, '$lt': end}

    if ctx is None:
        ctx = await prefetch_context(db, include_inactive)
    partners = ctx['partners']

    if not partners:
        return {'date': day_str, 'is_today': day == today_wib(), 'tasks': TASKS,
                'summary': _empty_summary(), 'rows': [], 'as_of_note': '',
                # Bentuk respons dijaga TETAP walau daftar vendor kosong — layar tidak
                # boleh harus menebak apakah sebuah field ada atau tidak.
                'as_of_note_base': '', 'legacy_note': '',
                'legacy_jobs_without_closed_at': 0}

    pids = ctx['pids']
    acc_info = ctx['acc_info']

    # ── 1. TERIMA MATERIAL ──────────────────────────────────────────────────
    # `received_at` ditulis SERVER pada transisi Sent→Received (bug-fix sesi ini;
    # sebelumnya hanya browser yang mengirimnya sebagai STRING sehingga rentang
    # tanggal tidak pernah cocok). `receipt_entered_at` ikut diterima sebagai
    # bukti untuk penerimaan yang dilakukan staf lewat mode override.
    terima_wait = await _group_count(
        db, 'vendor_shipments',
        {'vendor_id': {'$in': pids}, 'created_at': {'$lt': end},
         '$or': [{'status': 'Sent'}, {'received_at': {'$gte': end}}]})
    terima_done = await _group_count(
        db, 'vendor_shipments',
        {'vendor_id': {'$in': pids},
         '$or': [{'received_at': in_day}, {'receipt_entered_at': in_day}]},
        staff_field='receipt_entered_by_staff')

    # ── 2. INSPEKSI MATERIAL ────────────────────────────────────────────────
    insp_wait = await _group_count(
        db, 'vendor_shipments',
        {'vendor_id': {'$in': pids},
         '$and': [
             # sudah diterima pada akhir hari itu (dokumen lama tanpa
             # `received_at` dianggap diterima saat dibuat — satu-satunya
             # perkiraan yang tersedia, dan konservatif)
             {'$or': [{'received_at': {'$lt': end}},
                      {'$and': [{'status': 'Received'}, _missing('received_at'),
                                {'created_at': {'$lt': end}}]}]},
             # belum diinspeksi pada akhir hari itu
             {'$or': [{'inspected_at': {'$gte': end}},
                      {'$and': [{'inspection_status': {'$ne': 'Inspected'}},
                                _missing('inspected_at')]}]},
         ]})
    insp_done = await _group_count(
        db, 'vendor_material_inspections',
        {'vendor_id': {'$in': pids}, 'created_at': in_day},
        staff_field='entered_by_staff')

    # ── 3. PROGRESS PRODUKSI (vendor diresolusi lewat production_jobs) ──────
    jobs = ctx['jobs']
    job_vendor = ctx['job_vendor']
    job_ids = ctx['job_ids']

    prog_wait: dict = {}
    for j in jobs:
        # "Job jalan pada AKHIR tanggal ini" — aturannya ada di SATU tempat
        # (`core.production_job_lifecycle.was_open_at`) supaya rekap harian dan
        # mingguan tidak pernah menjawab berbeda. Sebelum `closed_at` ada, di sini
        # dipakai status SEKARANG (`status != 'In Progress' → skip`), sehingga job
        # yang dibuka Senin lalu ditutup Rabu HILANG dari rekap Senin — padahal
        # Senin itu vendor memang punya pekerjaan yang tidak dikerjakan.
        if not was_open_at(j, end):
            continue
        prog_wait.setdefault(j['vendor_id'], {'n': 0, 'staff': 0, 'qty': 0})['n'] += 1

    prog_done: dict = {}
    if job_ids:
        by_job = await _group_count(
            db, 'production_progress',
            {'job_id': {'$in': job_ids}, 'progress_date': in_day},
            key='job_id', staff_field='entered_by_staff', qty_field='completed_quantity')
        for jid, v in by_job.items():
            vid = job_vendor.get(jid)
            if not vid:
                continue
            slot = prog_done.setdefault(vid, {'n': 0, 'staff': 0, 'qty': 0})
            slot['n'] += v['n']
            slot['staff'] += v['staff']
            slot['qty'] += v['qty']

    # ── 4. KIRIM (CMT→DA / DA→buyer) ────────────────────────────────────────
    # "Menunggu" = barang yang sudah SELESAI diproduksi **sampai akhir hari itu**
    # tapi belum masuk surat jalan. Satuannya pcs (bukan dokumen) supaya staf
    # tahu besar pekerjaannya. Angka "selesai" diambil dari `production_progress`
    # (log peristiwa bertanggal) — BUKAN `production_job_items.produced_qty`
    # yang hanya menyimpan total berjalan tanpa tanggal, sehingga rekap tanggal
    # lampau tidak akan pernah bisa benar kalau memakainya. Keduanya terbukti
    # sama besar pada data hidup (Σprogress == produced_qty).
    produced: dict = {}
    if job_ids:
        by_job = await _group_count(
            db, 'production_progress',
            {'job_id': {'$in': job_ids},
             '$or': [{'progress_date': {'$lt': end}}, _missing('progress_date')]},
            key='job_id', qty_field='completed_quantity')
        for jid, v in by_job.items():
            vid = job_vendor.get(jid)
            if vid:
                produced[vid] = produced.get(vid, 0) + int(v['qty'] or 0)

    ship_vendor = ctx['ship_vendor']
    ship_staff = ctx['ship_staff']
    ship_ids = ctx['ship_ids']

    shipped: dict = {}
    kirim_done: dict = {}
    if ship_ids:
        by_ship_all = await _group_count(
            db, 'buyer_shipment_items',
            {'shipment_id': {'$in': ship_ids},
             '$or': [{'dispatch_date': {'$lt': end}}, _missing('dispatch_date')]},
            key='shipment_id', qty_field='qty_shipped')
        for sid, v in by_ship_all.items():
            vid = ship_vendor.get(sid)
            if vid:
                shipped[vid] = shipped.get(vid, 0) + int(v['qty'] or 0)

        by_ship_day = await _group_count(
            db, 'buyer_shipment_items',
            {'shipment_id': {'$in': ship_ids}, 'dispatch_date': in_day},
            key='shipment_id', qty_field='qty_shipped')
        for sid, v in by_ship_day.items():
            vid = ship_vendor.get(sid)
            if not vid:
                continue
            slot = kirim_done.setdefault(vid, {'n': 0, 'staff': 0, 'qty': 0})
            slot['n'] += v['n']
            slot['qty'] += int(v['qty'] or 0)
            if ship_staff.get(sid):
                slot['staff'] += v['n']

    # ── 5. BALAS REMINDER ───────────────────────────────────────────────────
    # Reminder yang LAHIR dari rekap tanggal ini dikecualikan (lihat docstring §2).
    rem_wait = await _group_count(
        db, 'reminders',
        {'vendor_id': {'$in': pids}, 'created_at': {'$lt': end},
         '$or': [{'status': 'pending'}, {'response_date': {'$gte': end}}],
         '$nor': [{'reminder_type': RECAP_REMINDER_TYPE, 'recap_date': day_str}]})
    rem_done = await _group_count(
        db, 'reminders',
        {'vendor_id': {'$in': pids}, 'response_date': in_day},
        staff_field='response_entered_by_staff')

    # ── Susun baris ─────────────────────────────────────────────────────────
    rows = []
    for p in partners:
        vid = p['id']
        acc = acc_info.get(vid, {})
        raw = {
            'terima': (terima_wait.get(vid, {}).get('n', 0),
                       terima_done.get(vid, {}), 0),
            'inspeksi': (insp_wait.get(vid, {}).get('n', 0),
                         insp_done.get(vid, {}), 0),
            'progress': (prog_wait.get(vid, {}).get('n', 0),
                         prog_done.get(vid, {}), 0),
            'kirim': (max(0, produced.get(vid, 0) - shipped.get(vid, 0)),
                      kirim_done.get(vid, {}), 0),
            'reminder': (rem_wait.get(vid, {}).get('n', 0),
                         rem_done.get(vid, {}), 0),
        }

        tasks: dict = {}
        for t in TASKS:
            waiting, done, _ = raw[t['key']]
            done_n = int(done.get('n', 0) or 0)
            staff_n = int(done.get('staff', 0) or 0)
            qty = int(done.get('qty', 0) or 0)
            st = _state(done_n, waiting)
            tasks[t['key']] = {
                'state': st,
                'waiting': int(waiting),
                'done_today': done_n,
                'qty_today': qty,
                'source': _source(done_n, staff_n),
                'module': t['module'],
                'detail': _detail(t, st, waiting, done_n, qty),
            }

        states = [tasks[k]['state'] for k in TASK_KEYS]
        if 'pending' in states:
            status = 'pending'
        elif 'partial' in states:
            status = 'partial'
        elif 'done' in states:
            status = 'done'
        else:
            status = 'idle'

        rows.append({
            'vendor_id': vid,
            'vendor_name': p.get('name', ''),
            'vendor_code': p.get('code', ''),
            'contact_name': p.get('contact_name', ''),
            'contact_phone': p.get('contact_phone', ''),
            'is_active': p.get('is_active') is not False and p.get('active') is not False,
            'has_active_portal_account': acc.get('has_active', False),
            'last_login_at': acc.get('last_login_at'),
            'account_count': len(acc.get('accounts', [])),
            'status': status,
            'pending_count': sum(1 for s in states if s == 'pending'),
            'pending_tasks': [t['label'] for t in TASKS if tasks[t['key']]['state'] == 'pending'],
            'tasks': tasks,
        })

    # Urutan layar = urutan kerja: yang paling perlu diurus di atas.
    rows.sort(key=lambda r: ({'pending': 0, 'partial': 1, 'done': 2, 'idle': 3}[r['status']],
                             -r['pending_count'], str(r['vendor_name']).lower()))

    summary = {
        'vendors_total': len(rows),
        'vendors_pending': sum(1 for r in rows if r['status'] == 'pending'),
        'vendors_partial': sum(1 for r in rows if r['status'] == 'partial'),
        'vendors_done': sum(1 for r in rows if r['status'] == 'done'),
        'vendors_idle': sum(1 for r in rows if r['status'] == 'idle'),
        'tasks_pending_total': sum(r['pending_count'] for r in rows),
        'tasks_done_total': sum(1 for r in rows for k in TASK_KEYS
                                if r['tasks'][k]['state'] in ('done', 'partial')),
        'qty_progress_today': sum(r['tasks']['progress']['qty_today'] for r in rows),
        'qty_shipped_today': sum(r['tasks']['kirim']['qty_today'] for r in rows),
    }

    # Catatan kejujuran data. Kolom "menunggu" dihitung **per akhir hari itu**
    # (memakai stempel waktu peristiwa), BUKAN kondisi sekarang.
    #
    # Sejak `closed_at` ada (fase 5), job yang sudah ditutup TETAP terhitung
    # sebagai "job jalan" pada tanggal-tanggal sebelum ia ditutup — jadi rekap
    # tanggal lampau tidak lagi memaafkan kelalaian yang sudah terjadi. Yang masih
    # bisa tidak diketahui hanyalah dokumen WARISAN: job yang sudah tertutup
    # SEBELUM fitur ini ada dan belum di-backfill. Jumlahnya disebut apa adanya —
    # laporan yang menyembunyikan ketidaktahuannya sendiri lebih berbahaya daripada
    # laporan yang mengakuinya.
    legacy_jobs = sum(1 for j in jobs if needs_closed_at_backfill(j))
    as_of_note_base = (f'Kolom "menunggu" dihitung menurut kondisi akhir tanggal {day_str} '
                       '(WIB). Job produksi yang ditutup SETELAH tanggal itu tetap '
                       'terhitung sebagai job jalan pada tanggal itu.')
    # Kalimat AKSI dipisah ke `legacy_note` supaya layar bisa menaikkannya menjadi
    # peringatan (amber) alih-alih menyelipkannya di ujung paragraf abu-abu 11px.
    # Ini satu-satunya sisa ketidaktahuan rekap tanggal lampau DAN obatnya cuma satu
    # perintah — catatan yang tak terbaca sama saja dengan tidak mengaku.
    legacy_note = ''
    if legacy_jobs:
        legacy_note = (f'{legacy_jobs} job lama tertutup tanpa stempel waktu '
                       'tutup (lahir sebelum fitur ini) sehingga tidak bisa dihitung '
                       'untuk tanggal lampau — jalankan migrasi '
                       'add_closed_at_to_production_jobs.py.')
    # `as_of_note` tetap UTUH (base + catatan, teks persis seperti sebelumnya) karena
    # berkas export dan pemanggil API lain membacanya sebagai satu kalimat.
    as_of_note = f'{as_of_note_base} Catatan: {legacy_note}' if legacy_note else as_of_note_base

    return {
        'date': day_str,
        'is_today': day == today_wib(),
        'tasks': TASKS,
        'summary': summary,
        'rows': rows,
        'legacy_jobs_without_closed_at': legacy_jobs,
        'as_of_note': as_of_note,
        # Dipecah supaya layar tidak menampilkan kalimat yang sama dua kali:
        # `as_of_note_base` untuk baris info, `legacy_note` untuk peringatan amber.
        'as_of_note_base': as_of_note_base,
        'legacy_note': legacy_note,
    }


def _empty_summary() -> dict:
    return {'vendors_total': 0, 'vendors_pending': 0, 'vendors_partial': 0,
            'vendors_done': 0, 'vendors_idle': 0, 'tasks_pending_total': 0,
            'tasks_done_total': 0, 'qty_progress_today': 0, 'qty_shipped_today': 0}


def _detail(task: dict, state: str, waiting: int, done_n: int, qty: int) -> str:
    """Keterangan singkat berbahasa manusia — dipakai layar, Excel, dan PDF sama."""
    key, unit = task['key'], task['unit']
    if state == 'none':
        return 'Tidak ada pekerjaan'
    if key == 'progress':
        did = f'{qty} pcs disetor' if qty else f'{done_n} setoran'
        if state == 'done':
            return did
        if state == 'partial':
            return f'{did} · {waiting} job masih jalan'
        return f'{waiting} job jalan, belum ada setoran'
    if key == 'kirim':
        did = f'{qty} pcs dikirim'
        if state == 'done':
            return did
        if state == 'partial':
            return f'{did} · sisa {waiting} pcs belum dikirim'
        return f'{waiting} pcs selesai belum dikirim'
    labels = {
        'terima': ('surat jalan diterima', 'surat jalan menunggu dikonfirmasi'),
        'inspeksi': ('inspeksi dikerjakan', 'kiriman belum diinspeksi'),
        'reminder': ('reminder dibalas', 'reminder belum dibalas'),
    }
    done_lbl, wait_lbl = labels.get(key, (f'{unit} dikerjakan', f'{unit} menunggu'))
    if state == 'done':
        return f'{done_n} {done_lbl}'
    if state == 'partial':
        return f'{done_n} {done_lbl} · sisa {waiting} {wait_lbl}'
    return f'{waiting} {wait_lbl}'


def pending_vendor_rows(recap: dict) -> list[dict]:
    """Baris vendor yang **belum diisi** (status ``pending``) — sasaran reminder.

    Sengaja TIDAK menyertakan ``partial``: vendor itu sudah menyetor hari ini,
    menegurnya justru membuat staf tidak dipercaya. ``partial`` tetap terlihat
    di layar (chip amber) dan bisa dipilih manual lewat ``vendor_ids``.
    """
    return [r for r in (recap.get('rows') or []) if r.get('status') == 'pending']



# ═══════════════════════════════════════════════════════════════════════════
# REKAP MINGGUAN — 7 hari BERGULIR (keputusan owner fase 4, 2026-08-10)
# ═══════════════════════════════════════════════════════════════════════════
# KENAPA "MERINGKAS", BUKAN "MENGHITUNG"
# --------------------------------------
# `build_week()` TIDAK punya satu pun query sendiri. Ia memanggil `build_recap()`
# untuk tiap hari (dengan `ctx` bersama) lalu hanya MERINGKAS hasilnya. Akibat yang
# disengaja: tab Mingguan **mustahil** berdebat dengan tab Harian, karena angkanya
# memang benda yang sama — bukan dua perhitungan yang "seharusnya" sama. Semua
# aturan sulit (batas WIB, definisi "terisi", pengecualian reminder rekap,
# resolusi vendor `production_progress`) otomatis ikut, tanpa disalin ulang.
#
# KEPUTUSAN OWNER (ditanya ulang 2026-08-10 karena catatan sesi lalu hilang)
# -------------------------------------------------------------------------
# 1. Pekan = **7 hari terakhir BERGULIR** (`akhir−6 … akhir`), bukan Senin–Minggu.
# 2. "Terlambat" dilaporkan sebagai **DUA angka**, tidak ada yang dibuang:
#      * `days_late`        = hari `pending`  (ada pekerjaan menunggu, NOL bukti)
#      * `days_unfinished`  = hari `pending` + `partial` (masih ada sisa)
#    `days_late` yang dipakai mengurutkan — itu yang benar-benar bolong.
# 3. Kolom: 7 kotak hari · terlambat · belum beres · hari tanpa setoran ·
#    total pcs disetor · total pcs dikirim · tren pcs (sparkline) · streak.
# 4. **Streak** = rentetan beruntun PALING AKHIR (mundur dari hari terakhir yang
#    sudah berjalan), **putus** pada hari `pending` ATAU `partial`.
# 5. Tombol reminder tab Mingguan menegur untuk **satu tanggal jelas** (hari
#    terakhir yang sudah berjalan) memakai `pending_vendor_rows()` yang SAMA
#    dengan tab Harian ⇒ dua tombol tidak akan pernah memilih vendor berbeda.
#
# TIGA ATURAN TURUNAN YANG DITULIS EKSPLISIT (supaya bukan tebakan orang berikutnya)
# ---------------------------------------------------------------------------------
# a. **"Hari tanpa setoran"** hanya dihitung pada hari vendor MEMANG punya job
#    jalan (`progress.state != 'none'`) tetapi `progress.done_today == 0`. Vendor
#    yang tidak diberi pekerjaan TIDAK boleh dihukum — itu angka bohong.
# b. **Hari `idle` NETRAL bagi streak**: tidak memutus (vendor tidak salah apa-apa)
#    tapi juga tidak menambah (tidak ada prestasi). Hanya `done` yang menambah.
# c. **Hari di masa depan** (> hari ini WIB) diberi state `future`, TIDAK dihitung
#    ke angka mana pun, dan `build_recap` tidak dipanggil untuk hari itu (hemat
#    ~10 query per hari yang belum terjadi).
WEEK_DAYS = 7
MAX_WEEK_DAYS = 31

_WD_SHORT = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
_WD_LONG = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']

# Status baris mingguan → urutan tampil (yang paling perlu diurus di atas).
_WEEK_STATUS_ORDER = {'late': 0, 'unfinished': 1, 'clean': 2, 'idle': 3}


def week_range(end_day: date | None = None,
               days: int = WEEK_DAYS) -> tuple[date, date, list[date]]:
    """``(mulai, akhir, [7 tanggal])`` untuk jendela **bergulir** yang BERAKHIR di
    ``end_day`` (default hari ini WIB).

    Sengaja bergulir (keputusan owner 1): "pekan ini" versi Senin–Minggu membuat
    hari Senin pagi selalu menampilkan pekan yang baru berumur satu hari — tidak
    berguna untuk pertanyaan "vendor mana yang belakangan ini sering bolong".
    """
    end = end_day or today_wib()
    days = max(1, min(int(days or WEEK_DAYS), MAX_WEEK_DAYS))
    start = end - timedelta(days=days - 1)
    return start, end, [start + timedelta(days=i) for i in range(days)]


def _day_meta(d: date, today: date) -> dict:
    wd = d.weekday()
    return {
        'date': d.strftime('%Y-%m-%d'),
        'weekday': _WD_LONG[wd],
        'short': _WD_SHORT[wd],
        'day_num': d.day,
        'is_today': d == today,
        'is_future': d > today,
    }


def _empty_week_summary(start: date, end: date, n_days: int, n_elapsed: int) -> dict:
    return {
        'start': start.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d'),
        'days': n_days, 'days_elapsed': n_elapsed,
        'vendors_total': 0, 'vendors_late': 0, 'vendors_unfinished': 0,
        'vendors_clean': 0, 'vendors_idle': 0,
        'days_late_total': 0, 'days_unfinished_total': 0, 'days_no_progress_total': 0,
        'qty_progress_total': 0, 'qty_shipped_total': 0, 'best_streak': 0,
    }


async def build_week(db, end_day: date | None = None, include_inactive: bool = False,
                     days: int = WEEK_DAYS, ctx: dict | None = None) -> dict:
    """Rekap **mingguan** (7 hari bergulir) seluruh vendor CMT.

    Hanya MERINGKAS :func:`build_recap` — lihat blok penjelasan di atas.

    Bentuk hasil::

        {
          'start': '2026-08-04', 'end': '2026-08-10', 'is_current': True,
          'days': [{'date','weekday','short','day_num','is_today','is_future'} × 7],
          'tasks': TASKS,
          'per_day': [{'date',...,'vendors_pending','qty_progress',...} × 7],
          'summary': {...},
          'rows': [{'vendor_id','vendor_name','cells':[...×7],'days_late',
                    'days_unfinished','days_no_progress','streak','trend',...}],
          'remind_date': '2026-08-10',
          'remind_pending': [{'vendor_id','vendor_name','pending_tasks'}],
        }
    """
    today = today_wib()
    start, end, day_list = week_range(end_day, days)
    elapsed = [d for d in day_list if d <= today]
    meta = [_day_meta(d, today) for d in day_list]

    if ctx is None:
        ctx = await prefetch_context(db, include_inactive)
    partners = ctx['partners']

    # Hari yang belum terjadi tidak ditanyakan ke Mongo sama sekali.
    recaps: dict[str, dict] = {}
    for d in elapsed:
        iso = d.strftime('%Y-%m-%d')
        recaps[iso] = await build_recap(db, d, include_inactive=include_inactive, ctx=ctx)

    # ── Ringkasan per hari: DIAMBIL dari summary harian, tidak dihitung ulang ──
    per_day = []
    for m in meta:
        if m['is_future']:
            per_day.append({**m, 'vendors_pending': 0, 'vendors_partial': 0,
                            'vendors_done': 0, 'vendors_idle': 0,
                            'tasks_pending_total': 0, 'qty_progress': 0, 'qty_shipped': 0})
            continue
        s = (recaps[m['date']] or {}).get('summary') or {}
        per_day.append({
            **m,
            'vendors_pending': int(s.get('vendors_pending') or 0),
            'vendors_partial': int(s.get('vendors_partial') or 0),
            'vendors_done': int(s.get('vendors_done') or 0),
            'vendors_idle': int(s.get('vendors_idle') or 0),
            'tasks_pending_total': int(s.get('tasks_pending_total') or 0),
            'qty_progress': int(s.get('qty_progress_today') or 0),
            'qty_shipped': int(s.get('qty_shipped_today') or 0),
        })

    if not partners:
        return {
            'start': start.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d'),
            'is_current': end == today, 'days': meta, 'tasks': TASKS,
            'per_day': per_day,
            'summary': _empty_week_summary(start, end, len(day_list), len(elapsed)),
            'rows': [], 'remind_date': '', 'remind_pending': [],
            'as_of_note': '', 'legacy_note': '',
            'legacy_jobs_without_closed_at': 0, 'rules_note': _WEEK_RULES_NOTE,
        }

    # Indeks baris harian per vendor supaya pencariannya O(1), bukan O(vendor×hari).
    idx: dict[str, dict] = {
        iso: {r['vendor_id']: r for r in (rec.get('rows') or [])}
        for iso, rec in recaps.items()
    }

    rows = []
    for p in partners:
        vid = p['id']
        cells = []
        for m in meta:
            if m['is_future']:
                cells.append({**m, 'state': 'future', 'pending_count': 0,
                              'pending_tasks': [], 'qty_progress': 0, 'qty_shipped': 0,
                              'progress_state': 'none', 'progress_done': 0, 'detail': ''})
                continue
            r = (idx.get(m['date']) or {}).get(vid) or {}
            tk = r.get('tasks') or {}
            prog = tk.get('progress') or {}
            kirim = tk.get('kirim') or {}
            cells.append({
                **m,
                'state': r.get('status', 'idle'),
                'pending_count': int(r.get('pending_count') or 0),
                'pending_tasks': list(r.get('pending_tasks') or []),
                'qty_progress': int(prog.get('qty_today') or 0),
                'qty_shipped': int(kirim.get('qty_today') or 0),
                'progress_state': prog.get('state', 'none'),
                'progress_done': int(prog.get('done_today') or 0),
            })

        real = [c for c in cells if not c['is_future']]
        days_late = sum(1 for c in real if c['state'] == 'pending')
        days_unfinished = sum(1 for c in real if c['state'] in ('pending', 'partial'))
        days_with_work = sum(1 for c in real if c['state'] != 'idle')
        # Aturan turunan (a): hanya hari yang MEMANG punya job jalan.
        days_no_progress = sum(1 for c in real
                               if c['progress_state'] != 'none' and c['progress_done'] == 0)

        # Aturan turunan (b): `idle` netral — tidak memutus, tidak menambah.
        streak, streak_broken_by = 0, ''
        for c in reversed(real):
            if c['state'] in ('pending', 'partial'):
                streak_broken_by = c['state']
                break
            if c['state'] == 'done':
                streak += 1

        late_dates = [c['date'] for c in real if c['state'] == 'pending']

        if days_late > 0:
            status = 'late'
        elif days_unfinished > 0:
            status = 'unfinished'
        elif days_with_work > 0:
            status = 'clean'
        else:
            status = 'idle'

        acc = (ctx.get('acc_info') or {}).get(vid, {})
        rows.append({
            'vendor_id': vid,
            'vendor_name': p.get('name', ''),
            'vendor_code': p.get('code', ''),
            'contact_name': p.get('contact_name', ''),
            'contact_phone': p.get('contact_phone', ''),
            'has_active_portal_account': acc.get('has_active', False),
            # Dipakai `pickFromRecap()` di layar (peringatan dobel input). Bentuk
            # baris sengaja dibuat SAMA dengan baris rekap harian supaya satu
            # fungsi pemilih vendor bisa melayani kedua tab.
            'last_login_at': acc.get('last_login_at'),
            'account_count': len(acc.get('accounts', [])),
            'cells': cells,
            'status': status,
            'days_late': days_late,
            'days_unfinished': days_unfinished,
            'days_no_progress': days_no_progress,
            'days_with_work': days_with_work,
            'qty_progress_total': sum(c['qty_progress'] for c in real),
            'qty_shipped_total': sum(c['qty_shipped'] for c in real),
            # Sparkline: satu angka per KOTAK (termasuk hari depan = 0) supaya
            # panjangnya selalu sama dengan jumlah kotak hari di layar.
            'trend': [c['qty_progress'] for c in cells],
            'trend_shipped': [c['qty_shipped'] for c in cells],
            'streak': streak,
            'streak_broken_by': streak_broken_by,
            'last_late_date': late_dates[-1] if late_dates else '',
            'late_dates': late_dates,
        })

    rows.sort(key=lambda r: (_WEEK_STATUS_ORDER[r['status']], -r['days_late'],
                             -r['days_unfinished'], -r['days_no_progress'],
                             str(r['vendor_name']).lower()))

    summary = {
        'start': start.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d'),
        'days': len(day_list), 'days_elapsed': len(elapsed),
        'vendors_total': len(rows),
        'vendors_late': sum(1 for r in rows if r['status'] == 'late'),
        'vendors_unfinished': sum(1 for r in rows if r['status'] == 'unfinished'),
        'vendors_clean': sum(1 for r in rows if r['status'] == 'clean'),
        'vendors_idle': sum(1 for r in rows if r['status'] == 'idle'),
        'days_late_total': sum(r['days_late'] for r in rows),
        'days_unfinished_total': sum(r['days_unfinished'] for r in rows),
        'days_no_progress_total': sum(r['days_no_progress'] for r in rows),
        'qty_progress_total': sum(r['qty_progress_total'] for r in rows),
        'qty_shipped_total': sum(r['qty_shipped_total'] for r in rows),
        'best_streak': max((r['streak'] for r in rows), default=0),
    }

    # Sasaran reminder = tanggal TERAKHIR yang sudah berjalan, memakai fungsi yang
    # SAMA dengan tab Harian (keputusan owner 5). "Tegur untuk 7 hari" tidak punya
    # tanggal yang jelas dan akan menabrak idempotensi per-vendor-per-tanggal.
    remind_date = elapsed[-1].strftime('%Y-%m-%d') if elapsed else ''
    remind_pending = [
        {'vendor_id': r['vendor_id'], 'vendor_name': r['vendor_name'],
         'pending_tasks': r.get('pending_tasks') or []}
        for r in pending_vendor_rows(recaps.get(remind_date) or {})
    ] if remind_date else []

    return {
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d'),
        'is_current': end == today,
        'days': meta,
        'tasks': TASKS,
        'per_day': per_day,
        'summary': summary,
        'rows': rows,
        'remind_date': remind_date,
        'remind_pending': remind_pending,
        # Diambil dari rekap harian (bukan dihitung ulang): jumlah job warisan yang
        # tertutup tanpa stempel waktu tutup. Ditampilkan apa adanya supaya layar
        # tidak menyembunyikan ketidaktahuannya sendiri.
        'legacy_jobs_without_closed_at': max(
            (int((r or {}).get('legacy_jobs_without_closed_at') or 0)
             for r in recaps.values()), default=0),
        # Kalimat aksinya juga DIAMBIL dari rekap harian, tidak disusun ulang di sini.
        # Kalau ditulis dua kali, suatu hari kedua layar akan menyuruh menjalankan
        # migrasi yang berbeda dan tidak ada yang tahu mana yang benar.
        'legacy_note': next((str((r or {}).get('legacy_note') or '')
                             for r in recaps.values() if (r or {}).get('legacy_note')), ''),
        'as_of_note': (f'Rentang {start.strftime("%Y-%m-%d")} … {end.strftime("%Y-%m-%d")} '
                       '(7 hari bergulir, batas hari WIB). Setiap kotak hari memakai '
                       'angka Rekap Harian tanggal itu — klik kotaknya untuk melihat '
                       'rinciannya. Job produksi yang ditutup SETELAH suatu tanggal '
                       'tetap terhitung sebagai job jalan pada tanggal itu.'),
        'rules_note': _WEEK_RULES_NOTE,
    }


_WEEK_RULES_NOTE = (
    'Terlambat = hari yang ada pekerjaan menunggu tapi NOL bukti pengisian. '
    'Belum beres = hari terlambat ditambah hari yang sudah diisi tapi masih ada sisa. '
    'Hari tanpa setoran hanya dihitung pada hari vendor memang punya job jalan. '
    'Streak = rentetan hari beruntun terakhir tanpa hari terlambat/belum beres '
    '(hari tanpa pekerjaan tidak memutus, tapi juga tidak menambah).'
)


# ══════════════════════════════════════════════════════════════════════════════
# F12a — PERBANDINGAN ANTAR-PEKAN (naik/turun dibanding pekan sebelumnya)
# ══════════════════════════════════════════════════════════════════════════════
# ATURAN KERAS: perbandingan ini TIDAK menghitung apa pun sendiri. Ia memanggil
# `build_week()` DUA KALI (jendela sekarang & jendela sebelumnya) dengan `ctx`
# yang SAMA, lalu hanya mengurangkan angka `summary`. Kalau suatu hari ada yang
# "mengoptimalkannya" dengan agregasi sendiri, kolom naik/turun akan mulai
# berbeda dari kotak hariannya — dan itu angka dasar tagihan CMT (gate RK-21).
#
# KEJUJURAN: pekan berjalan biasanya BELUM lengkap (mis. baru 3 dari 7 hari).
# Membandingkan 3 hari melawan 7 hari akan selalu tampak "turun". Jadi hasilnya
# selalu membawa `comparable` + `note`, dan angka volume (pcs) diberi versi
# **per hari berjalan** supaya perbandingannya adil.
_WEEK_DELTA_KEYS = (
    'qty_progress_total', 'qty_shipped_total',
    'days_late_total', 'days_unfinished_total', 'days_no_progress_total',
    'vendors_late', 'vendors_unfinished', 'vendors_clean', 'vendors_idle',
    'best_streak',
)

# Untuk angka ini, NAIK = buruk (semakin banyak hari terlambat semakin jelek).
# Dipakai layar untuk memilih warna, supaya keputusan "hijau/merah" tidak ditulis
# dua kali di frontend dan backend.
_WEEK_LOWER_IS_BETTER = frozenset({
    'days_late_total', 'days_unfinished_total', 'days_no_progress_total',
    'vendors_late', 'vendors_unfinished', 'vendors_idle',
})


def _per_day(value: float, elapsed: int) -> float:
    return round(float(value or 0) / elapsed, 2) if elapsed else 0.0


# ── F12b — SIAPA yang bergerak, bukan cuma "berapa" ──────────────────────────
# Kartu delta ringkasan menjawab "pekan ini lebih baik atau lebih buruk".
# Pertanyaan BERIKUTNYA di rapat selalu sama, dan ringkasan tidak bisa
# menjawabnya: **vendor mana**. Tanpa nama, angka ringkasan cuma jadi bahan
# berdebat dan rapatnya berakhir tanpa satu pun tindakan.
#
# KENAPA PERINGKATNYA DIPUTUSKAN DI SINI, BUKAN DI LAYAR
# Urutan "paling memburuk" adalah sebuah KEPUTUSAN, bukan tampilan: hari
# terlambat dinilai lebih berat daripada pcs. Kalau layar yang mengurutkan,
# export Excel/PDF akan mengurutkan dengan caranya sendiri — dan dua dokumen
# yang mengaku sama akan menunjuk vendor "terburuk" yang BERBEDA di rapat yang
# sama. Peringkat tinggal di SSOT ini supaya layar dan lampiran tidak bisa
# berselisih.
_MOVER_LIMIT = 5


def _vendor_direction(days_late_diff: int, qty_diff: int) -> str:
    """``'worse' | 'better' | 'flat'`` — hari terlambat MENANG atas pcs.

    Vendor yang menyetor lebih banyak pcs TAPI menambah hari nol-bukti tetap
    disebut **memburuk**. Alasannya uang: pcs yang muncul tanpa jejak harian
    tidak bisa dipakai memverifikasi tagihan CMT, jadi membiarkan angka pcs yang
    naik menutupi tambahan hari nol-bukti sama dengan menghapus masalahnya dari
    layar.

    Hanya dipanggil untuk vendor yang PUNYA PEKERJAAN di kedua jendela — lihat
    :func:`_vendor_compare_basis`.
    """
    if days_late_diff != 0:
        return 'worse' if days_late_diff > 0 else 'better'
    if qty_diff != 0:
        return 'better' if qty_diff > 0 else 'worse'
    return 'flat'


def _vendor_compare_basis(is_new: bool, work_now: int, work_prev: int) -> str:
    """``''`` bila layak dibandingkan, atau ALASAN kenapa tidak.

    Aturan yang sama dengan RK-23 ("hari tanpa setoran" tidak menghukum vendor
    yang tidak punya job), dibawa ke perbandingan antar-pekan. Tanpa ini, papan
    peringkat jadi menyesatkan dalam dua arah sekaligus:

    * vendor yang pekan lalu **tidak diberi pekerjaan** lalu pekan ini bekerja
      akan tampil sebagai "paling membaik" — memuji vendor atas keputusan kita
      sendiri memberinya order;
    * vendor yang pekan ini **tidak diberi pekerjaan** akan tampil "paling
      memburuk" karena pcs-nya turun ke 0 — menuduh vendor atas kekosongan yang
      kita sendiri sebabkan.

    Keduanya membuat daftar "vendor bermasalah" berisi nama yang salah, dan
    setelah sekali salah tegur, daftarnya berhenti dipercaya.
    """
    if is_new:
        return 'Vendor baru — belum ada di pekan sebelumnya.'
    if work_now <= 0 and work_prev <= 0:
        return 'Tidak ada pekerjaan di kedua pekan.'
    if work_prev <= 0:
        return 'Pekan sebelumnya vendor ini tidak punya pekerjaan.'
    if work_now <= 0:
        return 'Pekan ini vendor ini tidak punya pekerjaan.'
    return ''


async def build_week_comparison(db, end_day: date | None = None,
                                include_inactive: bool = False,
                                days: int = WEEK_DAYS,
                                ctx: dict | None = None) -> dict:
    """Rekap mingguan + perbandingan dengan **jendela sebelumnya** yang sama panjang.

    Return::

        {
          'current':  <hasil build_week()>,          # utuh, seperti biasa
          'previous': {'summary': {...}, 'start':…, 'end':…},
          'delta': {'<kunci>': {'now','prev','diff','pct','lower_is_better','better'}},
          'per_vendor': [{'vendor_id','vendor_name','qty_now','qty_prev','qty_diff',
                          'days_late_now','days_late_prev','days_late_diff',
                          'days_unfinished_now','days_unfinished_prev',
                          'days_unfinished_diff','days_with_work_now',
                          'days_with_work_prev','status_now','status_prev',
                          'direction','incomparable_reason','is_new'}],
          'movers': {'worsened': [...], 'improved': [...], 'counts': {...},
                     'limit': int, 'fair': bool, 'rule': str},
          'new_vendors': [...],                      # belum ada pekan lalu
          'comparable': bool, 'note': str,
        }
    """
    if ctx is None:
        ctx = await prefetch_context(db, include_inactive)

    cur = await build_week(db, end_day, include_inactive=include_inactive,
                           days=days, ctx=ctx)
    start_cur = datetime.strptime(cur['start'], '%Y-%m-%d').date()
    prev_end = start_cur - timedelta(days=1)
    prev = await build_week(db, prev_end, include_inactive=include_inactive,
                            days=days, ctx=ctx)

    s_now, s_prev = cur.get('summary') or {}, prev.get('summary') or {}
    el_now = int(s_now.get('days_elapsed') or 0)
    el_prev = int(s_prev.get('days_elapsed') or 0)

    delta: dict = {}
    for k in _WEEK_DELTA_KEYS:
        now_v = float(s_now.get(k) or 0)
        prev_v = float(s_prev.get(k) or 0)
        diff = round(now_v - prev_v, 2)
        lower_better = k in _WEEK_LOWER_IS_BETTER
        delta[k] = {
            'now': now_v, 'prev': prev_v, 'diff': diff,
            'pct': round((diff / prev_v * 100), 1) if prev_v else None,
            'lower_is_better': lower_better,
            'better': (diff < 0) if lower_better else (diff > 0),
            # Versi per hari berjalan — satu-satunya perbandingan yang adil ketika
            # pekan berjalan belum lengkap.
            'now_per_day': _per_day(now_v, el_now),
            'prev_per_day': _per_day(prev_v, el_prev),
        }

    prev_rows = {r['vendor_id']: r for r in (prev.get('rows') or [])}
    per_vendor = []
    for r in (cur.get('rows') or []):
        p = prev_rows.get(r['vendor_id']) or {}
        qty_now = int(r.get('qty_progress_total') or 0)
        qty_prev = int(p.get('qty_progress_total') or 0)
        late_now = int(r.get('days_late') or 0)
        late_prev = int(p.get('days_late') or 0)
        unf_now = int(r.get('days_unfinished') or 0)
        unf_prev = int(p.get('days_unfinished') or 0)
        work_now = int(r.get('days_with_work') or 0)
        work_prev = int(p.get('days_with_work') or 0)
        is_new = r['vendor_id'] not in prev_rows
        why_not = _vendor_compare_basis(is_new, work_now, work_prev)
        per_vendor.append({
            'vendor_id': r['vendor_id'],
            'vendor_name': r['vendor_name'],
            'vendor_code': r.get('vendor_code', ''),
            'qty_now': qty_now,
            'qty_prev': qty_prev,
            'qty_diff': qty_now - qty_prev,
            'days_late_now': late_now,
            'days_late_prev': late_prev,
            'days_late_diff': late_now - late_prev,
            'days_unfinished_now': unf_now,
            'days_unfinished_prev': unf_prev,
            'days_unfinished_diff': unf_now - unf_prev,
            # Dibawa supaya layar bisa MENJELASKAN kenapa sebuah vendor tidak
            # masuk peringkat, bukan cuma menghilangkannya.
            'days_with_work_now': work_now,
            'days_with_work_prev': work_prev,
            # Status ("late/unfinished/clean/idle") dibawa DUA-DUANYA supaya layar
            # bisa bilang "dulu rapi, sekarang terlambat" — kalimat yang jauh lebih
            # bisa ditindaklanjuti daripada "+2".
            'status_now': r.get('status', 'idle'),
            'status_prev': p.get('status', '') if not is_new else '',
            'direction': ('incomparable' if why_not
                          else _vendor_direction(late_now - late_prev, qty_now - qty_prev)),
            'incomparable_reason': why_not,
            'is_new': is_new,
        })

    # Papan peringkat HANYA berisi vendor yang punya pekerjaan di KEDUA jendela
    # (lihat `_vendor_compare_basis`). Yang lain tidak dibuang diam-diam:
    # jumlahnya tetap dilaporkan di `counts.incomparable` supaya selisih antara
    # "jumlah vendor" dan "jumlah yang diperingkat" selalu bisa dijelaskan.
    known = [v for v in per_vendor if v['direction'] != 'incomparable']
    worsened = sorted(
        (v for v in known if v['direction'] == 'worse'),
        key=lambda v: (-v['days_late_diff'], v['qty_diff'], str(v['vendor_name']).lower()),
    )
    improved = sorted(
        (v for v in known if v['direction'] == 'better'),
        key=lambda v: (v['days_late_diff'], -v['qty_diff'], str(v['vendor_name']).lower()),
    )
    new_vendors = [v for v in per_vendor if v['is_new']]

    comparable = el_now == el_prev and el_now > 0
    if el_now == 0:
        note = ('Pekan ini belum punya hari yang berjalan, jadi tidak ada yang '
                'bisa dibandingkan.')
    elif comparable:
        note = (f'Membandingkan {el_now} hari berjalan '
                f'({cur["start"]} … {cur["end"]}) dengan {el_prev} hari '
                f'({prev["start"]} … {prev["end"]}).')
    else:
        note = (f'Pekan ini baru {el_now} hari berjalan, pekan sebelumnya {el_prev} hari. '
                'Angka totalnya belum sebanding — pakai kolom "per hari" untuk '
                'perbandingan yang adil.')

    movers = {
        'worsened': worsened[:_MOVER_LIMIT],
        'improved': improved[:_MOVER_LIMIT],
        'limit': _MOVER_LIMIT,
        'counts': {
            'worsened': len(worsened),
            'improved': len(improved),
            'flat': sum(1 for v in known if v['direction'] == 'flat'),
            'incomparable': len(per_vendor) - len(known),
            'new': len(new_vendors),
            'ranked': len(known),
            'vendors': len(per_vendor),
        },
        # Peringkatnya tetap disusun walau jendelanya belum sama panjang, TAPI
        # ditandai supaya layar bisa memberi peringatan alih-alih memakai daftar
        # yang panjang jendelanya berbeda seolah-olah setara.
        'fair': comparable,
        'rule': ('Diurutkan dari tambahan HARI TERLAMBAT terbanyak; bila sama, '
                 'dari penurunan pcs terbesar. Vendor yang tidak punya pekerjaan '
                 'di salah satu pekan (termasuk vendor baru) tidak diperingkat.'),
    }

    return {
        'current': cur,
        'previous': {'start': prev['start'], 'end': prev['end'], 'summary': s_prev},
        'delta': delta,
        'per_vendor': per_vendor,
        'movers': movers,
        'new_vendors': new_vendors,
        'comparable': comparable,
        'note': note,
    }


# ══════════════════════════════════════════════════════════════════════════════
# F12b — PENGIRIMAN REMINDER REKAP (SSOT: dipakai tombol DAN penjadwal 16:00 WIB)
# ══════════════════════════════════════════════════════════════════════════════
def _recap_reminder_message(day_str: str, missing: list) -> str:
    daftar = ', '.join(missing) if missing else 'pengisian harian'
    return (f'Rekap harian {day_str}: data berikut belum masuk — {daftar}. '
            'Mohon dilengkapi hari ini agar progress dan tagihan CMT tidak tertunda.')


async def send_recap_reminders(db, day: date, *, vendor_ids: list | None = None,
                               message: str = '', actor: dict | None = None,
                               source: str = 'manual') -> dict:
    """Kirim reminder rekap harian. **Satu-satunya** penulis reminder rekap.

    Dipakai oleh DUA pemanggil, dan itu justru alasannya ada:

    * ``POST /api/cmt-override/daily-recap/remind`` — tombol di layar;
    * penjadwal **16:00 WIB** (`utils/scheduler.job_cmt_daily_recap_reminder`).

    Kalau penjadwal menyalin logikanya, suatu hari aturan idempotensi (satu
    reminder per vendor per tanggal) akan berbeda antara tombol dan penjadwal —
    dan vendor menerima teguran dobel setiap hari. Reminder rekap yang membanjiri
    inbox berhenti dibaca, dan setelah itu tidak ada lagi alat untuk menegur.

    Return ``{'date','sent','skipped','sent_count','skipped_count','candidates'}``.
    """
    from routes.production_rbac import resolve_vendor_doc
    from routes.shared import new_id, now

    day_str = day.strftime('%Y-%m-%d')
    recap = await build_recap(db, day)
    by_id = {r['vendor_id']: r for r in recap['rows']}

    if isinstance(vendor_ids, list) and vendor_ids:
        unknown = [v for v in vendor_ids if v not in by_id]
        if unknown:
            raise ValueError(
                f"Vendor tidak ada di master CMT aktif: {', '.join(unknown)}")
        targets = [by_id[v] for v in vendor_ids]
    else:
        targets = pending_vendor_rows(recap)

    custom = (message or '').strip()
    actor = actor or {}
    sent, skipped = [], []
    for row in targets:
        vid = row['vendor_id']
        dup = await db.reminders.find_one(
            {'vendor_id': vid, 'reminder_type': RECAP_REMINDER_TYPE,
             'recap_date': day_str}, {'_id': 0, 'id': 1})
        if dup:
            skipped.append({'vendor_id': vid, 'vendor_name': row['vendor_name'],
                            'reason': 'Sudah dikirim reminder rekap untuk tanggal ini',
                            'reminder_id': dup.get('id', '')})
            continue

        vendor_doc = await resolve_vendor_doc(db, vid)
        missing = row.get('pending_tasks') or []
        reminder = {
            'id': new_id(),
            'vendor_id': vid,
            'vendor_name': (vendor_doc or {}).get('garment_name', row.get('vendor_name', '')),
            'po_id': '', 'po_number': '',
            'reminder_type': RECAP_REMINDER_TYPE,
            'subject': f'Pengisian harian belum lengkap — {day_str}',
            'message': custom or _recap_reminder_message(day_str, missing),
            'priority': 'high' if len(missing) > 1 else 'normal',
            'status': 'pending', 'response': None, 'response_date': None,
            # Jejak rekap: dipakai untuk idempotensi DAN untuk mengecualikan
            # reminder ini dari hitungan "ada pekerjaan" pada tanggal yang sama.
            'recap_date': day_str,
            'recap_pending_tasks': missing,
            # Dari mana teguran ini datang — supaya vendor/staf bisa membedakan
            # teguran otomatis 16:00 dari teguran yang benar-benar diklik orang.
            'recap_source': source,
            'created_by': actor.get('name', '') or ('Penjadwal 16:00 WIB'
                                                    if source == 'scheduler' else ''),
            'created_at': now(), 'updated_at': now(),
        }
        await db.reminders.insert_one(reminder)
        sent.append({'vendor_id': vid, 'vendor_name': reminder['vendor_name'],
                     'reminder_id': reminder['id'], 'pending_tasks': missing})

    return {'date': day_str, 'sent': sent, 'skipped': skipped,
            'sent_count': len(sent), 'skipped_count': len(skipped),
            'candidates': len(targets)}
