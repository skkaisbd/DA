"""
services/rbac_audit.py — Audit hidup: approval tanpa izin & notifikasi tanpa target.

Permintaan owner (2026-08-07): "perlu halaman audit di Portal Sysadmin supaya
bisa saya pantau sendiri ke depan."

Cara kerja: analisis statis (AST) atas `backend/routes`, `backend/services`,
`backend/core` — TIDAK menyentuh data, jadi aman dijalankan kapan pun.

  A. ENDPOINT KEPUTUSAN (approve/reject/confirm/posting) → apakah ada gerbang
     izin (`require_perm` / `assert_can_act` / `can_act` / cek role + 403 /
     dependencies di router) atau hanya `require_auth` (siapa pun yang login).
  B. PENULIS NOTIFIKASI → apakah penerima ditargetkan (`user_id`,
     `target_roles`, `target_user_ids`). Notifikasi tanpa target berisiko
     tersembunyi atau terbaca role yang tidak berhak.
  C. FAKTA DATA: bagaimana notifikasi yang benar-benar ada di database
     ditargetkan (personal / per role / tanpa target).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SCAN_DIRS = ('routes', 'services', 'core')

DECISION_RE = re.compile(
    r'(approve|approval|reject|decline|verify|validate|authorize|post-to-gl|'
    r'posting|close-period|confirm|inspect)', re.I)
GUARD_RE = re.compile(
    r'require_perm|require_portal|assert_can_act|has_perm|can_act|require_role|'
    r'SUPER_ROLES|[A-Z][A-Z_]*ROLES|_require_[a-z_]+|'
    r'require_client_auth|require_vendor_auth|'
    r'403[^\n]{0,80}(role|izin|akses|hanya)|(role|izin|akses)[^\n]{0,80}403', re.I)
WRITERS = ('notif_insert', 'publish_notification')
TARGET_KW = {'user_id', 'target_roles', 'target_user_ids', 'recipient'}


def _deco(dec):
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    if dec.func.attr not in ('get', 'post', 'put', 'patch', 'delete'):
        return None
    path = str(dec.args[0].value) if (dec.args and isinstance(dec.args[0], ast.Constant)) else ''
    return dec.func.attr, path, any(k.arg == 'dependencies' for k in dec.keywords)


def _scan_file(path: Path):
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.split('\n')
    router_guarded = bool(re.search(r'APIRouter\((?:[^)]|\n)*dependencies\s*=', src))
    rel = str(path.relative_to(BACKEND))
    approvals, notifs = [], []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = '\n'.join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
            for dec in node.decorator_list:
                info = _deco(dec)
                if not info:
                    continue
                method, route, dec_dep = info
                if method == 'get' or not DECISION_RE.search(f'{route} {node.name}'):
                    continue
                deco_src = '\n'.join(lines[dec.lineno - 1:(dec.end_lineno or dec.lineno)])
                inline = bool(GUARD_RE.search(body) or GUARD_RE.search(deco_src))
                approvals.append({
                    'file': rel, 'line': node.lineno, 'method': method.upper(),
                    'route': route, 'func': node.name,
                    'guard': ('perm-check' if inline else
                              'router-dependency' if (router_guarded or dec_dep) else 'AUTH-ONLY'),
                })
        elif isinstance(node, ast.Call):
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else node.func.id if isinstance(node.func, ast.Name) else '')
            if name not in WRITERS:
                continue
            kw = {k.arg for k in node.keywords if k.arg}
            seg = ' '.join('\n'.join(
                lines[node.lineno - 1:(node.end_lineno or node.lineno)]).split())
            notifs.append({
                'file': rel, 'line': node.lineno, 'writer': name,
                'targeted': bool(kw & TARGET_KW),
                'target_kwargs': sorted(kw & TARGET_KW),
                'snippet': seg[:140],
            })
    return approvals, notifs


def scan_code() -> dict:
    approvals, notifs = [], []
    for d in SCAN_DIRS:
        for p in sorted((BACKEND / d).rglob('*.py')):
            if '__pycache__' in str(p):
                continue
            try:
                a, n = _scan_file(p)
            except SyntaxError:
                continue
            approvals += a
            notifs += n
    unguarded = [a for a in approvals if a['guard'] == 'AUTH-ONLY']
    untargeted = [n for n in notifs if not n['targeted']]
    return {
        'approvals': {
            'total': len(approvals),
            'guarded': len(approvals) - len(unguarded),
            'unguarded': len(unguarded),
            'unguarded_items': sorted(unguarded, key=lambda x: (x['file'], x['line'])),
        },
        'notification_writers': {
            'total': len(notifs),
            'targeted': len(notifs) - len(untargeted),
            'untargeted': len(untargeted),
            'untargeted_items': sorted(untargeted, key=lambda x: (x['file'], x['line'])),
            'by_writer': {w: sum(1 for n in notifs if n['writer'] == w) for w in WRITERS},
        },
    }


async def scan_data(db) -> dict:
    """Bagaimana notifikasi yang ADA di database ditargetkan (fakta, bukan kode)."""
    n = db.notifications
    total = await n.count_documents({})
    personal = await n.count_documents({'user_id': {'$ne': None}})
    role_root = await n.count_documents({'target_roles.0': {'$exists': True}})
    role_meta = await n.count_documents({'meta.target_roles.0': {'$exists': True}})
    users_root = await n.count_documents({'target_user_ids.0': {'$exists': True}})
    users_meta = await n.count_documents({'meta.target_user_ids.0': {'$exists': True}})
    untargeted = await n.count_documents({
        'user_id': None,
        'target_roles': {'$in': [None, []]}, 'meta.target_roles': {'$in': [None, []]},
        'target_user_ids': {'$in': [None, []]}, 'meta.target_user_ids': {'$in': [None, []]},
    })
    by_type = {r['_id']: r['n'] async for r in n.aggregate([
        {'$group': {'_id': '$type', 'n': {'$sum': 1}}}, {'$sort': {'n': -1}}])}
    top_subtypes = [{'subtype': r['_id'] or '(kosong)', 'count': r['n']} async for r in n.aggregate([
        {'$group': {'_id': '$subtype', 'n': {'$sum': 1}}}, {'$sort': {'n': -1}}, {'$limit': 10}])]
    return {
        'total': total,
        'personal_user_id': personal,
        'role_targeted': role_root + role_meta,
        'user_list_targeted': users_root + users_meta,
        'untargeted': untargeted,
        'by_type': by_type,
        'top_subtypes': top_subtypes,
    }


async def run_audit(db) -> dict:
    code = scan_code()
    data = await scan_data(db)
    findings = []
    if code['approvals']['unguarded']:
        findings.append({
            'level': 'warning',
            'title': f"{code['approvals']['unguarded']} endpoint keputusan tanpa gerbang izin",
            'detail': 'Endpoint di bawah hanya butuh "sudah login" — siapa pun bisa memutuskan.',
        })
    if code['notification_writers']['untargeted']:
        findings.append({
            'level': 'warning',
            'title': f"{code['notification_writers']['untargeted']} notifikasi ditulis tanpa target penerima",
            'detail': 'Tanpa target, notifikasi hanya terlihat admin/owner (berpotensi tak sampai).',
        })
    if data['untargeted']:
        findings.append({
            'level': 'info',
            'title': f"{data['untargeted']} notifikasi lama tanpa target di database",
            'detail': 'Hanya admin/owner yang bisa melihatnya (aturan audiens 2026-08-07).',
        })
    if not findings:
        findings.append({'level': 'ok', 'title': 'Tidak ada temuan',
                         'detail': 'Semua endpoint keputusan berizin & semua notifikasi bertarget.'})
    return {
        'audience_rule': ('penerima = user_id saya · target_user_ids memuat saya · '
                          'target_roles memuat role saya · tanpa target = hanya admin/owner'),
        'code': code, 'data': data, 'findings': findings,
    }
