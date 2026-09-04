"""
AUDIT: flow approval & notifikasi vs RBAC (2026-08-07).

Pertanyaan owner: "apakah notifikasi dan approval sudah berjalan benar dan
logicnya benar? cek semua flow yang butuh approval dan yang menimbulkan
notifikasi. pastikan link ke RBAC — jangan sampai role A menerima notifikasi
role B."

Analisis statis (AST) atas seluruh `backend/routes` + `backend/services`:

  A. ENDPOINT APPROVAL  — apakah dijaga izin (require_perm / require_portal /
     has_perm / can_act / router dependencies) atau HANYA require_auth
     (artinya siapa pun yang login bisa menyetujui).
  B. PENULIS NOTIFIKASI — apakah penerima ditargetkan (user_id / target_roles /
     target_user_ids) atau siaran tanpa target (berisiko bocor lintas role).

Jalankan: python3 /app/scripts/audit_approval_notif_rbac.py [--json]
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path('/app/backend')
DIRS = ['routes', 'services', 'core']

APPROVAL_RE = re.compile(
    r'(approve|approval|reject|decline|submit|verify|validate|authorize|'
    r'owner-approve|owner-reject|post-to-gl|posting|close-period|confirm)', re.I)
GUARD_RE = re.compile(
    r'require_perm|require_portal|has_perm|can_act|require_role|'
    r'SUPER_ROLES|[A-Z][A-Z_]*ROLES|_require_[a-z_]+|'
    r'require_client_auth|require_vendor_auth|'
    r'403[^\n]{0,80}(role|izin|akses|hanya)|(role|izin|akses)[^\n]{0,80}403', re.I)
TARGET_RE = re.compile(r'user_id\s*=|target_roles\s*=|target_user_ids\s*=|recipient\s*=')


def deco_info(dec):
    """('post', '/x/{id}/approve') dari @router.post('/x/{id}/approve') bila ada."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    method = dec.func.attr
    if method not in ('get', 'post', 'put', 'patch', 'delete'):
        return None
    path = ''
    if dec.args and isinstance(dec.args[0], ast.Constant):
        path = str(dec.args[0].value)
    has_dep = any(k.arg == 'dependencies' for k in dec.keywords)
    return method, path, has_dep


def audit_file(path: Path):
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.split('\n')

    # Router-level dependencies (APIRouter(..., dependencies=[...])) berlaku
    # untuk SEMUA endpoint di file itu.
    router_guarded = bool(re.search(r'APIRouter\((?:[^)]|\n)*dependencies\s*=', src))

    approvals, notifs = [], []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body_src = '\n'.join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
        for dec in node.decorator_list:
            info = deco_info(dec)
            if not info:
                continue
            method, route, dec_dep = info
            if method == 'get':
                continue
            target = f'{route} {node.name}'
            if not APPROVAL_RE.search(target):
                continue
            deco_src = '\n'.join(lines[dec.lineno - 1:(dec.end_lineno or dec.lineno)])
            guarded = bool(GUARD_RE.search(body_src) or GUARD_RE.search(deco_src)
                           or dec_dep or router_guarded)
            approvals.append({
                'file': str(path.relative_to(ROOT)), 'line': node.lineno,
                'method': method.upper(), 'route': route, 'func': node.name,
                'guard': ('router-dependency' if (router_guarded or dec_dep) and
                          not GUARD_RE.search(body_src) else
                          'perm-check' if GUARD_RE.search(body_src) or GUARD_RE.search(deco_src)
                          else 'AUTH-ONLY'),
            })

    # Penulis notifikasi
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else '')
        if name not in ('notif_insert', 'publish_notification'):
            continue
        kw = {k.arg for k in node.keywords if k.arg}
        targeted = bool(kw & {'user_id', 'target_roles', 'target_user_ids', 'recipient'})
        seg = '\n'.join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
        notifs.append({
            'file': str(path.relative_to(ROOT)), 'line': node.lineno, 'writer': name,
            'targeted': targeted,
            'kwargs': sorted(kw & {'user_id', 'target_roles', 'target_user_ids',
                                   'subtype', 'type', 'type_'}),
            'snippet': ' '.join(seg.split())[:110],
        })
    return approvals, notifs


def main():
    approvals, notifs = [], []
    for d in DIRS:
        for p in sorted((ROOT / d).rglob('*.py')):
            if '__pycache__' in str(p):
                continue
            try:
                a, n = audit_file(p)
            except SyntaxError as e:
                print(f'!! gagal parse {p}: {e}')
                continue
            approvals += a
            notifs += n

    unguarded = [a for a in approvals if a['guard'] == 'AUTH-ONLY']
    untargeted = [n for n in notifs if not n['targeted']]

    if '--json' in sys.argv:
        print(json.dumps({'approvals': approvals, 'notifs': notifs}, indent=2))
        return

    print('=' * 78)
    print(f'A. ENDPOINT APPROVAL: {len(approvals)} ditemukan · '
          f'{len(approvals) - len(unguarded)} dijaga izin · {len(unguarded)} HANYA require_auth')
    print('=' * 78)
    for a in unguarded:
        print(f"  [TANPA IZIN] {a['method']:6} {a['route']:<52} {a['file']}:{a['line']}")
    print()
    print('=' * 78)
    print(f'B. PENULIS NOTIFIKASI: {len(notifs)} pemanggilan · '
          f'{len(untargeted)} tanpa target penerima')
    print('=' * 78)
    for n in untargeted:
        print(f"  [TANPA TARGET] {n['writer']:22} {n['file']}:{n['line']}  {n['snippet']}")
    print()
    by_writer = {}
    for n in notifs:
        by_writer.setdefault(n['writer'], []).append(n)
    for w, rows in by_writer.items():
        print(f"  · {w}: {len(rows)} pemanggilan "
              f"({sum(1 for r in rows if r['targeted'])} bertarget)")


if __name__ == '__main__':
    main()
