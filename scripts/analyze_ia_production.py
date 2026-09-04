#!/usr/bin/env python3
"""
Analisis IA (Information Architecture) — Portal Produksi vs Portal Maklon.

Read-only. Menghasilkan fakta mentah:
  1. Struktur nav per portal (kedalaman, jumlah pintu, jumlah item/section)
  2. Pintu Produksi: modul NYATA vs REDIRECT (makeRedirect)
  3. Modul domain produksi yang ADA di registry tapi TIDAK ADA di nav mana pun (tak terjangkau)
  4. moduleId yang muncul di >1 portal (shortcut lintas-portal / ambigu kepemilikan)
  5. Tab isi hub produksi
Dipakai untuk menyusun proposal IA. Tidak mengubah apa pun.
"""
import re
import json
from pathlib import Path

SRC = Path('/app/frontend/src/components/erp')
NAV = SRC / 'portal-shell' / 'portalNav.js'
REG = SRC / 'moduleRegistry.js'

nav_src = NAV.read_text(encoding='utf-8')
reg_src = REG.read_text(encoding='utf-8')


def strip_comments(s: str) -> str:
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    s = re.sub(r'(?m)^\s*//.*$', '', s)
    s = re.sub(r'(?<![:"\'/])//[^\n]*$', '', s, flags=re.M)
    return s


# ─── 1. Parse PORTAL_NAV ────────────────────────────────────────────────────
nav_clean = strip_comments(nav_src)
start = nav_clean.index('export const PORTAL_NAV')
body = nav_clean[start:]
end = body.index('\n};')
body = body[:end]

portals = {}
# split per portal key at indent 2
portal_iter = list(re.finditer(r'\n  (\w+): \{\n    title: \'([^\']*)\',', body))
for i, m in enumerate(portal_iter):
    pid = m.group(1)
    title = m.group(2)
    seg = body[m.end(): portal_iter[i + 1].start() if i + 1 < len(portal_iter) else len(body)]
    sections = []
    sec_iter = list(re.finditer(r"\n      \{\n        label: '([^']*)',", seg))
    for j, sm in enumerate(sec_iter):
        sec_label = sm.group(1)
        sseg = seg[sm.end(): sec_iter[j + 1].start() if j + 1 < len(sec_iter) else len(seg)]
        groups = []
        gm_iter = list(re.finditer(r"\n          \{\n            label: '([^']*)',", sseg))
        if gm_iter:
            for k, gm in enumerate(gm_iter):
                gseg = sseg[gm.end(): gm_iter[k + 1].start() if k + 1 < len(gm_iter) else len(sseg)]
                ids = re.findall(r"id: '([^']+)',\s*label: '([^']*)'", gseg)
                groups.append({'label': gm.group(1), 'items': ids})
            sections.append({'label': sec_label, 'groups': groups})
        else:
            ids = re.findall(r"id: '([^']+)',\s*label: '([^']*)'", sseg)
            sections.append({'label': sec_label, 'items': ids})
    portals[pid] = {'title': title, 'sections': sections}


def flat(portal):
    out = []
    for s in portals[portal]['sections']:
        if 'items' in s:
            out += [(s['label'], None, i, l) for i, l in s['items']]
        else:
            for g in s['groups']:
                out += [(s['label'], g['label'], i, l) for i, l in g['items']]
    return out


# ─── 2. Parse MODULE_REGISTRY ───────────────────────────────────────────────
reg_clean = strip_comments(reg_src)
rstart = reg_clean.index('export const MODULE_REGISTRY')
rbody = reg_clean[rstart:]
entries = dict(re.findall(r"'([^']+)':\s*([A-Za-z_][\w.]*|makeRedirect\([^)]*\)|withProps\([^)]*\)|makeModuleWithTab\([^)]*\))", rbody))

redirects = {k: v for k, v in entries.items() if v.startswith('makeRedirect')}
real = {k: v for k, v in entries.items() if not v.startswith('makeRedirect')}

nav_ids = {}
for p in portals:
    for sec, grp, mid, lbl in flat(p):
        nav_ids.setdefault(mid, []).append((p, sec, grp, lbl))

PROD_PREFIX = ('prod-', 'production-', 'cmt-', 'da-cmt', 'po-closure', 'wo-')

print('=' * 78)
print('1. STRUKTUR NAV — semua portal')
print('=' * 78)
print(f"{'portal':<14}{'sections':>9}{'pakai groups':>14}{'pintu':>7}{'max item/section':>18}")
for p in portals:
    f = flat(p)
    uses_groups = any('groups' in s for s in portals[p]['sections'])
    per_sec = {}
    for sec, grp, mid, lbl in f:
        per_sec[sec] = per_sec.get(sec, 0) + 1
    print(f"{p:<14}{len(portals[p]['sections']):>9}{('YA' if uses_groups else '-'):>14}{len(f):>7}{max(per_sec.values()):>18}")

print()
print('=' * 78)
print('2. PORTAL PRODUKSI — isi nav sekarang (AS-IS)')
print('=' * 78)
for sec, grp, mid, lbl in flat('production'):
    kind = 'REDIRECT→' + re.findall(r"makeRedirect\('([^']+)'", redirects[mid])[0] if mid in redirects else ('modul' if mid in real else '❌TIDAK ADA DI REGISTRY')
    other = [x[0] for x in nav_ids[mid] if x[0] != 'production']
    dup = f"  ⚠ juga di: {','.join(other)}" if other else ''
    print(f"  [{sec[:22]:<22}|{(grp or '-')[:22]:<22}] {mid:<32} {lbl:<26} {kind}{dup}")

print()
print('=' * 78)
print('3. PORTAL MAKLON — isi nav sekarang (acuan yang dianggap RAPIH)')
print('=' * 78)
for sec, grp, mid, lbl in flat('maklon'):
    other = [x[0] for x in nav_ids[mid] if x[0] != 'maklon']
    dup = f"  ⚠ juga di: {','.join(other)}" if other else ''
    print(f"  [{sec[:24]:<24}] {mid:<30} {lbl:<26}{dup}")

print()
print('=' * 78)
print('4. MODUL DOMAIN PRODUKSI — di registry, NYATA (bukan redirect), TAPI TIDAK ADA DI NAV')
print('=' * 78)
orphans = []
for mid, comp in sorted(real.items()):
    if mid.startswith(PROD_PREFIX) and mid not in nav_ids:
        orphans.append((mid, comp))
for mid, comp in orphans:
    print(f"  {mid:<38} → {comp}")
print(f"  TOTAL tak terjangkau (domain produksi): {len(orphans)}")

print()
print('=' * 78)
print('5. SEMUA MODUL NYATA TAK TERJANGKAU (semua domain)')
print('=' * 78)
all_orph = [(m, c) for m, c in sorted(real.items()) if m not in nav_ids]
for mid, comp in all_orph:
    print(f"  {mid:<38} → {comp}")
print(f"  TOTAL: {len(all_orph)}")

print()
print('=' * 78)
print('6. moduleId MUNCUL DI >1 PORTAL')
print('=' * 78)
for mid, places in sorted(nav_ids.items()):
    if len(places) > 1:
        print(f"  {mid:<32} " + ' | '.join(f"{p}:{lbl}" for p, s, g, lbl in places))

print()
print('=' * 78)
print('7. PINTU DI NAV YANG TIDAK ADA DI REGISTRY (ghost)')
print('=' * 78)
ghosts = [m for m in nav_ids if m not in entries]
print('  ' + (', '.join(ghosts) if ghosts else '(tidak ada)'))
