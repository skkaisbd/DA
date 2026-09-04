"""core/cmt_override.py — SSOT **Portal CMT Override** (staf DA mengisi ATAS NAMA vendor CMT).

═══════════════════════════════════════════════════════════════════════════════
MASALAH NYATA YANG DISELESAIKAN
═══════════════════════════════════════════════════════════════════════════════
Sebagian vendor CMT (sub-kontraktor jahit) TIDAK memakai sistem: tidak mau/tidak
bisa login portal. Akibatnya seluruh rantai CMT mentok — padahal **tagihan CMT
dihitung dari progress produksi**, jadi data yang tidak masuk = uang yang tidak
bisa ditagih/diverifikasi.

Modul ini memberi staf DA jalan resmi untuk mengisi 11 modul Portal Vendor CMT
atas nama vendor, **tanpa** menyamar jadi vendor (tidak ada token palsu, tidak
ada akun bayangan) dan **tanpa** menghilangkan jejak siapa yang mengetik.

═══════════════════════════════════════════════════════════════════════════════
KEPUTUSAN OWNER (2026-08-08) — jangan diubah tanpa persetujuan owner
═══════════════════════════════════════════════════════════════════════════════
1a. Cakupan = **SEMUA 11 modul** portal vendor di-mirror (bukan sebagian).
2b. Yang berhak = ``admin``, ``superadmin``, ``admin_produksi``,
    ``supervisor_produksi``, ``ppic``. Setiap aksi tercatat NAMANYA.
3a. Jejak override **TERCATAT + KELIHATAN**: dokumen menyimpan ``entered_by`` +
    ``on_behalf_of_vendor``, dan badge "diinput staf DA" muncul di layar
    monitoring & invoice. Alasan owner: kalau ada selisih tagihan, harus bisa
    tahu angka itu dari vendor atau dari staf.
4a. Dropdown vendor = **semua vendor aktif** di master CMT (``vendor_partners``).
    TIDAK ada flag "tidak pakai sistem" (owner menolak menambah flag).
5a. Vendor yang punya akun portal aktif **tetap boleh** di-override, tapi UI
    WAJIB memberi peringatan "hati-hati dobel input" + tanggal login terakhir.

═══════════════════════════════════════════════════════════════════════════════
KENAPA HEADER, BUKAN QUERY/BODY PARAM DI 11 MODUL FRONTEND
═══════════════════════════════════════════════════════════════════════════════
11 komponen ``engine/Vendor*.jsx`` SUDAH terbukti jalan di portal vendor asli.
Kalau override diminta lewat ``?vendor_id=`` maka 11 komponen itu harus diedit
satu-satu (≈40 pemanggilan API) — dan setiap komponen yang lupa diedit akan
menampilkan data SELURUH vendor kepada staf, kesalahan yang tidak kelihatan.

Dengan header ``X-CMT-Override-Vendor``:
  * scoping dikerjakan di BACKEND lewat satu pintu (:func:`apply_scope`),
  * 11 komponen dipakai ULANG apa adanya ⇒ risiko regresi portal vendor ~nol,
  * mustahil "layar override bilang X padahal vendor melihat Y", karena kode
    pembacanya benar-benar sama.

═══════════════════════════════════════════════════════════════════════════════
INVARIAN KEAMANAN (dijaga gate INV-CMTOV / scripts/verify_cmt_override.py)
═══════════════════════════════════════════════════════════════════════════════
OV-1  Header override HANYA dihormati untuk role di :data:`OVERRIDE_ROLES`.
      Role lain yang mengirim header ⇒ **403 eksplisit**, bukan diabaikan diam-diam
      (kalau diabaikan, staf tak berhak akan melihat data SELURUH vendor dan
      menyangka dirinya sedang ter-scope — persis kesalahan yang paling mahal).
OV-2  Akun vendor TIDAK BOLEH memakai header ini (mustahil vendor A menyamar
      jadi vendor B) ⇒ 403.
OV-3  Vendor tujuan wajib ADA di ``vendor_partners`` dan berstatus aktif.
OV-4  Setiap dokumen yang lahir dari mode override WAJIB membawa stempel
      :func:`stamp` (``entered_by_staff=True`` + nama staf + vendor yang diwakili).
OV-5  Dokumen yang TIDAK lahir dari mode override tidak boleh ikut distempel —
      field-nya bahkan tidak ditambahkan (nol perubahan pada data lama).
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from core.helpers import now

# Nama header override. Sengaja spesifik (bukan `X-Vendor-Id`) supaya tidak
# pernah tertukar dengan filter biasa dan mudah dicari di seluruh repo.
OVERRIDE_HEADER = 'X-CMT-Override-Vendor'

# Keputusan owner 2b. `superadmin` tetap masuk daftar walau umumnya bypass —
# supaya modul ini tidak bergantung pada perilaku check_role().
OVERRIDE_ROLES = frozenset({
    'admin',
    'superadmin',
    'admin_produksi',
    'supervisor_produksi',
    'ppic',
})

# Kunci cache pada request.state supaya satu request tidak menembak Mongo
# berulang kali hanya untuk memvalidasi vendor yang sama.
_STATE_KEY = '_cmt_override_ctx'
_STATE_DONE = '_cmt_override_done'


def header_value(request: Request) -> str:
    """Isi header override yang sudah dirapikan (string kosong bila tidak ada)."""
    try:
        return (request.headers.get(OVERRIDE_HEADER) or '').strip()
    except Exception:
        return ''


def is_override_role(user: dict) -> bool:
    return (user.get('role') or '').strip().lower() in OVERRIDE_ROLES


async def resolve_override(request: Request, user: dict, db) -> dict | None:
    """Baca + validasi header override. ``None`` bila mode override tidak aktif.

    Mengembalikan konteks:
    ``{vendor_id, vendor_name, vendor_code, staff_id, staff_name, staff_role}``

    Melempar 403/404/400 sesuai invarian OV-1..OV-3. Hasilnya di-cache di
    ``request.state`` (termasuk hasil ``None``) supaya idempoten dan murah.
    """
    if getattr(request.state, _STATE_DONE, False):
        return getattr(request.state, _STATE_KEY, None)

    vid = header_value(request)
    if not vid:
        setattr(request.state, _STATE_KEY, None)
        setattr(request.state, _STATE_DONE, True)
        return None

    role = (user.get('role') or '').strip().lower()

    # OV-2 — vendor tidak boleh menyamar jadi vendor lain.
    from routes.production_rbac import is_vendor
    if is_vendor(user):
        raise HTTPException(
            403,
            'Akun vendor tidak boleh memakai Portal CMT Override. '
            'Header override hanya untuk staf DA.',
        )

    # OV-1 — role tak berhak DITOLAK, bukan diabaikan.
    if role not in OVERRIDE_ROLES:
        raise HTTPException(
            403,
            'Anda tidak berhak mengisi data atas nama vendor CMT. '
            f"Role yang diizinkan: {', '.join(sorted(OVERRIDE_ROLES))}.",
        )

    # OV-3 — vendor tujuan harus ada & aktif di master CMT.
    partner = await db.vendor_partners.find_one({'id': vid}, {'_id': 0})
    if not partner:
        raise HTTPException(
            404,
            f'Vendor CMT tidak ditemukan di master (vendor_id={vid}). '
            'Buka menu Vendor CMT untuk memastikan datanya ada.',
        )
    # Dokumen lama memakai `active`, yang baru `is_active` — hormati keduanya,
    # dan hanya blokir bila BENAR-BENAR False (dokumen tanpa field = aktif).
    if partner.get('is_active') is False or partner.get('active') is False:
        raise HTTPException(
            400,
            f"Vendor CMT '{partner.get('name', vid)}' sudah tidak aktif. "
            'Aktifkan dulu di menu Vendor CMT sebelum mengisi atas namanya.',
        )

    ctx = {
        'vendor_id': partner['id'],
        'vendor_name': partner.get('name', ''),
        'vendor_code': partner.get('code', ''),
        'staff_id': user.get('id', ''),
        'staff_name': user.get('name', ''),
        'staff_role': role,
    }
    setattr(request.state, _STATE_KEY, ctx)
    setattr(request.state, _STATE_DONE, True)
    return ctx


async def get_override(request: Request, user: dict, db=None) -> dict | None:
    """Alias nyaman: ambil konteks override (mengambil db sendiri bila perlu)."""
    if db is None:
        from database import get_db
        db = get_db()
    return await resolve_override(request, user, db)


def stamp(ctx: dict | None) -> dict:
    """Stempel jejak audit untuk diselipkan ke dokumen (OV-4/OV-5).

    Mode normal (``ctx is None``) mengembalikan ``{}`` — **tidak satu field pun**
    ditambahkan, sehingga dokumen non-override identik dengan sebelum fitur ini
    ada (penting: repo ini menjaga "tidak ada angka tersimpan yang bergeser").
    """
    if not ctx:
        return {}
    return {
        'entered_by_staff': True,
        'entered_by': ctx.get('staff_name', ''),
        'entered_by_id': ctx.get('staff_id', ''),
        'entered_by_role': ctx.get('staff_role', ''),
        'on_behalf_of_vendor': ctx.get('vendor_id', ''),
        'on_behalf_of_vendor_name': ctx.get('vendor_name', ''),
        'entered_at': now(),
    }


def entry_source(doc: dict | None) -> str:
    """``'staff'`` bila dokumen diinput staf DA, ``'vendor'`` bila dari vendor.

    Dipakai layar monitoring & invoice untuk badge "diinput staf DA" (keputusan
    3a). Satu pintu supaya semua layar menjawab sama.
    """
    if doc and doc.get('entered_by_staff') is True:
        return 'staff'
    return 'vendor'


async def effective_vendor_id(request: Request, user: dict, db,
                              body_vendor_id: str | None = None) -> str | None:
    """Vendor yang berlaku untuk sebuah **penulisan**.

    Urutan (satu pintu untuk semua endpoint tulis):
      1. akun vendor  → identitas dari tokennya (tidak bisa dipalsukan),
      2. mode override → vendor yang sedang diwakili,
      3. staf biasa    → ``vendor_id`` dari body (perilaku lama, tak berubah).

    ``resolve_override`` dipanggil lebih dulu agar OV-2 (vendor tak boleh memakai
    header override) benar-benar ditegakkan, bukan diabaikan diam-diam.
    """
    from routes.production_rbac import is_vendor, vendor_identity
    ctx = await resolve_override(request, user, db)
    if is_vendor(user):
        return vendor_identity(user)
    if ctx:
        return ctx['vendor_id']
    return body_vendor_id


async def apply_scope(request: Request, user: dict, db, query: dict,
                      field: str = 'vendor_id',
                      param_vendor_id: str | None = None) -> str | None:
    """Satu pintu scoping **pembacaan**. Mengembalikan vendor_id yang dipakai.

    * akun vendor  → dipaksa ke vendornya sendiri (tak bisa ditembus query param),
    * mode override → dipaksa ke vendor yang diwakili (staf melihat PERSIS apa
      yang vendor lihat — inilah yang membuat layar override tidak bisa bohong),
    * staf biasa    → ikut ``param_vendor_id`` bila dikirim (perilaku lama).

    ``resolve_override`` dipanggil LEBIH DULU (juga untuk akun vendor) supaya
    invarian OV-2 benar-benar berlaku: vendor yang mengirim header override
    ditolak 403, tidak "diabaikan dengan aman". Kalau diabaikan, kesalahan
    integrasi tidak pernah terlihat sampai suatu hari header itu dihormati.
    """
    from routes.production_rbac import is_vendor, vendor_identity
    ctx = await resolve_override(request, user, db)
    if is_vendor(user):
        vid = vendor_identity(user)
        if vid:
            query[field] = vid
        return vid
    if ctx:
        query[field] = ctx['vendor_id']
        return ctx['vendor_id']
    if param_vendor_id:
        query[field] = param_vendor_id
        return param_vendor_id
    return None
