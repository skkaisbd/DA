#!/usr/bin/env python3
"""
Probe READ-ONLY: cari panggilan FE lewat wrapper apiGet/apiPost/... yang TIDAK
menulis literal '/api' (titik buta gate INV-CONTRACT-01, karena fe_calls()
mencari literal '/api/...'). Semua GET diprobe; POST/PUT/DELETE hanya dicatat
(tidak dieksekusi) — cukup dicek eksistensinya dengan OPTIONS/GET 405.

Tidak mengubah data apa pun.
"""
import re
import subprocess
import json
from pathlib import Path
from collections import defaultdict

FE = Path('/app/frontend/src')
BASE = 'http://localhost:8001'
TOKEN = Path('/tmp/.adm_tok').read_text().strip()

pat = re.compile(r"api(Get|Post|Put|Patch|Delete)\(\s*'(/[a-z0-9][^']*)'")
calls = defaultdict(set)  # path -> {methods}
where = defaultdict(set)  # path -> {file:line}

for f in FE.rglob('*.js*'):
    try:
        txt = f.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    for i, line in enumerate(txt.split('\n'), 1):
        if line.strip().startswith('//') or line.strip().startswith('*'):
            continue
        for m in pat.finditer(line):
            method, path = m.group(1).upper(), m.group(2)
            if path.startswith('/api'):
                continue
            calls[path].add(method)
            where[path].add(f"{f.relative_to(FE)}:{i}")


def probe(path, method):
    url = f"{BASE}/api{path}"
    if method == 'GET':
        cmd = ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', url,
               '-H', f'Authorization: Bearer {TOKEN}']
    else:
        # cek eksistensi tanpa efek: GET ke path yang seharusnya POST → 405 kalau ada
        cmd = ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', url,
               '-H', f'Authorization: Bearer {TOKEN}']
    return subprocess.run(cmd, capture_output=True, text=True, timeout=40).stdout.strip()


dead, ok, unclear = [], [], []
for path in sorted(calls):
    methods = calls[path]
    code = probe(path, 'GET' if 'GET' in methods else sorted(methods)[0])
    row = (code, path, ','.join(sorted(methods)), sorted(where[path])[:2])
    if code == '404':
        dead.append(row)
    elif code in ('200', '201', '405', '422', '400', '403'):
        ok.append(row)
    else:
        unclear.append(row)

print('=' * 90)
print('PANGGILAN FE TANPA LITERAL "/api" (titik buta gate kontrak) — total path unik:', len(calls))
print('=' * 90)
print(f'\n🔴 MATI (HTTP 404) — {len(dead)}')
for code, p, m, w in dead:
    print(f'  {code}  {m:<12} /api{p}')
    for x in w:
        print(f'          ← {x}')
print(f'\n✅ ADA ({len(ok)})')
for code, p, m, w in ok:
    print(f'  {code}  {m:<12} /api{p}')
print(f'\n❔ TAK JELAS ({len(unclear)})')
for code, p, m, w in unclear:
    print(f'  {code}  {m:<12} /api{p}')
