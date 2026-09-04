#!/usr/bin/env python3
"""
Refinement analisis IA: dari daftar moduleId "tidak ada di PORTAL_NAV", pisahkan
  (a) TERJANGKAU SEBAGAI TAB  — komponennya di-import oleh hub/modul lain yang ADA di nav
  (b) BENAR-BENAR TAK TERJANGKAU — tidak di nav, tidak diimport modul mana pun
READ-ONLY.
"""
import re
from pathlib import Path

ERP = Path('/app/frontend/src/components/erp')
NAV = ERP / 'portal-shell' / 'portalNav.js'
REG = ERP / 'moduleRegistry.js'

nav_ids = set(re.findall(r"id: '([^']+)'", NAV.read_text(encoding='utf-8')))

reg = REG.read_text(encoding='utf-8')
# id -> component symbol
body = reg[reg.index('export const MODULE_REGISTRY'):]
entries = {}
for m in re.finditer(r"'([^']+)':\s*(makeRedirect\(|withProps\(\s*([A-Za-z_]\w*)|makeModuleWithTab\(\s*([A-Za-z_]\w*)|([A-Za-z_]\w*))", body):
    mid = m.group(1)
    if m.group(2).startswith('makeRedirect'):
        entries[mid] = 'makeRedirect(...)'
    else:
        entries[mid] = m.group(3) or m.group(4) or m.group(5)
# symbol -> file path (from lazy import)
sym2file = dict(re.findall(r"const\s+([A-Za-z_][\w]*)\s*=\s*lazy\(\(\)\s*=>\s*import\('([^']+)'\)\)", reg))

# semua file JSX yang di-import oleh file lain (selain moduleRegistry)
all_src = {}
for f in Path('/app/frontend/src').rglob('*.js*'):
    try:
        all_src[f] = f.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        pass

REG_PATH = REG.resolve()


def imported_elsewhere(basename: str):
    """cari file lain (bukan moduleRegistry) yang mengimpor basename"""
    hits = []
    for f, txt in all_src.items():
        if f.resolve() == REG_PATH or f.name == basename + '.jsx':
            continue
        if re.search(rf"import\(['\"][^'\"]*/{re.escape(basename)}['\"]\)", txt) or \
           re.search(rf"import\s+{re.escape(basename)}\s+from", txt):
            hits.append(str(f.relative_to('/app/frontend/src')))
    return hits


real = {k: v for k, v in entries.items() if not str(v).startswith('makeRedirect')}
unreached = sorted(k for k in real if k not in nav_ids)

tab_reachable, truly = [], []
for mid in unreached:
    sym = real[mid]
    fp = sym2file.get(sym)
    base = Path(fp).name if fp else sym
    hits = imported_elsewhere(base)
    if hits:
        tab_reachable.append((mid, base, hits[:3]))
    else:
        truly.append((mid, base))

print('=' * 88)
print(f'moduleId NYATA yang TIDAK ada di PORTAL_NAV: {len(unreached)}')
print('=' * 88)
print(f'\n(a) TERJANGKAU sebagai TAB / sub-komponen — {len(tab_reachable)}')
for mid, base, hits in tab_reachable:
    print(f'  {mid:<36} {base:<38} ← {hits[0]}')
print(f'\n(b) BENAR-BENAR TAK TERJANGKAU dari UI — {len(truly)}')
for mid, base in truly:
    print(f'  {mid:<36} {base}')
