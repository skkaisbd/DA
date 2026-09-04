#!/usr/bin/env python3
"""test_core_f15_kartu_terbaca.py — CORE TEST **F15**:
kartu punya LATAR, tulisannya TERBACA, dan cadangan token tidak berbohong.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN — DAN KENAPA KETIGANYA SEKELUARGA
═══════════════════════════════════════════════════════════════════════════════
Laporan pemilik (2026-08-14): *"beberapa page di portal marketing cardsnya masih
belum terdesign dengan baik seperti lupa di kasih background cardsnya, lalu ada
beberapa yang masih abu abu itu perbaiki."*

Sesudah diukur, keluhan itu bukan soal selera. Ada tiga kelas cacat yang
kebetulan punya satu sifat yang sama: **tidak pernah menjadi galat**, sehingga
bisa hidup berbulan-bulan tanpa ada yang tahu.

  (1) **Kelas Tailwind RUSAK** — `bg-foreground/[0.06]0`, `border-foreground/
      [0.01]0`, dst. Angka nyasar sesudah `]` membuat kelasnya tidak dikenal,
      jadi Tailwind tidak menghasilkan CSS apa pun. Elemennya benar-benar tanpa
      latar. Sebabnya find/replace massal yang gagal (`bg-white/60` → ganti
      `white/6` jadi `foreground/[0.06]` → `bg-foreground/[0.06]0`); pola yang
      sama menjelaskan `[0.01]0` (`/10`), `[0.02]0` (`/20`), `[0.03]0` (`/30`),
      `[0.04]0` (`/40`), `[0.08]0` (`/80`). **Diukur: 23 kejadian di 9 berkas.**
      Build HIJAU, lint HIJAU, tampilan rusak.

  (2) **Abu-abu di atas abu-abu** — `text-muted-foreground/50|60|70` pada
      elemen ber-`bg-muted`. Dengan tema produk ini rasio kontrasnya 1.9–2.6
      (lantai 3.0) di tema terang MAUPUN gelap. `muted-foreground` memang sudah
      warna redup; menambah modifikator opasitas hanya mencampurnya ke latar —
      tidak ada kasus di mana ia menolong. **Diukur: 56 kejadian.**

  (3) **Cadangan token yang MUSTAHIL bekerja** —
      `token || localStorage.getItem('auth_token')` di 30 tempat, padahal
      `auth_token` **tidak pernah ditulis** (`setItem('auth_token')` = 0
      kejadian); kunci yang benar `erp_token`. Jadi begitu prop `token` kosong,
      permintaannya mengirim `Bearer null` dan layar berkata "gagal memuat"
      tanpa sebab. Cadangan yang tidak mungkin bekerja LEBIH BURUK daripada
      tidak ada cadangan: ia membuat orang berhenti mencurigai token.

PENJAGA DI BERKAS INI (statik — layar tidak butuh backend untuk dijaga)
-----------------------------------------------------------------------
* `A-*` audit tampilan dijalankan ulang: 0 kelas rusak, 0 kontras di bawah 3.0.
* `B-*` tidak ada lagi `auth_token`; kunci token yang dipakai = `erp_token`.
* `C-*` pemilih/komponen BARU yang ditambahkan sesi ini punya latar tegas
  (`bg-background`/`bg-popover`) — bukan transparan yang mewarisi apa pun di
  belakangnya (penyebab "dropdown tembus pandang" yang klasik).
* `D-*` `PickingListModal` tidak lagi memakai variabel milik komponen induk
  (`ReferenceError` saat modal dibuka = layar putih).

Pakai:  python3 /app/test_core_f15_kartu_terbaca.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SRC = Path("/app/frontend/src")
AUDIT = Path("/app/memory/AUDIT_UI_CARD_CONTRAST.json")
G, R, X, B = "\033[92m", "\033[91m", "\033[0m", "\033[1m"
RES: list = []


def check(code: str, cond: bool, msg: str):
    RES.append((code, bool(cond), msg))
    print(f"  {G + '✓' + X if cond else R + '✗' + X} [{code}] {msg}")
    return bool(cond)


def section_audit():
    print(f"\n{B}[A] Kartu punya latar & tulisannya terbaca (audit dijalankan ulang){X}")
    try:
        subprocess.run([sys.executable, "/app/scripts/_audit_ui_card_contrast.py"],
                       capture_output=True, timeout=300, check=False)
        rep = json.loads(AUDIT.read_text())
    except Exception as e:  # noqa: BLE001
        check("A-0", False, f"audit tampilan tidak bisa dijalankan/dibaca: {e}")
        return

    check("A-0", rep.get("scanned_files", 0) >= 300,
          f"audit benar-benar memindai layar ({rep.get('scanned_files')} berkas)")

    broken = rep.get("broken_classes") or []
    ex = ", ".join(f"{Path(h['file']).name}:{h['line']} {h['cls']}" for h in broken[:4])
    check("A-1", not broken,
          f"tidak ada kelas Tailwind rusak ({len(broken)}) — kelas rusak tidak "
          f"menghasilkan CSS, jadi 'lupa background' TIDAK terlihat sebagai galat"
          + (f" — {ex}" if broken else ""))

    faded = rep.get("faded_on_muted") or []
    ex2 = ", ".join(f"{Path(h['file']).name}:{h['line']} {h['cls']}(rasio {h['contrast']})"
                    for h in faded[:4])
    check("A-2", not faded,
          f"tidak ada teks di atas latar `muted` dengan kontras < 3.0 ({len(faded)})"
          + (f" — {ex2}" if faded else ""))

    # F15-B — kelas yang DIRAKIT saat berjalan tidak pernah dibuat Tailwind.
    dyn = rep.get("dynamic_classes") or []
    ex3 = ", ".join(f"{Path(h['file']).name}:{h['line']}" for h in dyn[:5])
    check("A-4", not dyn,
          f"tidak ada kelas Tailwind yang dirakit saat berjalan ({len(dyn)}) — "
          f"`bg-${{color}}-500/5` tidak pernah dibuat (Tailwind membaca TEKS, "
          f"bukan menjalankan JS); terukur: kartu KPI 'Perlu Diserahkan' (teal) "
          f"memang tanpa latar & tanpa garis di bundel hasil build"
          + (f" — {ex3}" if dyn else ""))

    tone = Path("/app/frontend/src/lib/tone.js")
    check("A-5", tone.exists() and "bg-teal-50" in tone.read_text(),
          "`lib/tone.js` ada dan menulis kelasnya HARFIAH (nama warna boleh "
          "dinamis, kelasnya tidak)")

    # Audit harus MENGHITUNG kontras, bukan memakai ambang kasar. Versi pertama
    # memakai "opasitas < 100 = cacat" dan menuduh `text-foreground/80` (rasio
    # 8.6) sebagai cacat — penjaga yang salah tuduh berhenti dipercaya.
    asrc = Path("/app/scripts/_audit_ui_card_contrast.py").read_text()
    check("A-3", "contrast_on_muted" in asrc and "CONTRAST_FLOOR" in asrc,
          "audit MENGHITUNG rasio kontras (bukan ambang opasitas kasar yang "
          "menuduh `text-foreground/80` padahal rasionya 8.6)")


def section_token():
    print(f"\n{B}[B] Cadangan token tidak berbohong{X}")
    hits = []
    for f in list(SRC.rglob("*.jsx")) + list(SRC.rglob("*.js")):
        try:
            s = f.read_text(errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        if "getItem('auth_token')" in s or 'getItem("auth_token")' in s:
            hits.append(str(f.relative_to(SRC)))
    check("B-1", not hits,
          f"tidak ada lagi cadangan `auth_token` yang mustahil bekerja "
          f"({len(hits)})" + (f" — {hits[:3]}" if hits else ""))

    written = [f for f in list(SRC.rglob("*.jsx")) + list(SRC.rglob("*.js"))
               if "setItem('auth_token'" in f.read_text(errors="ignore")]
    check("B-2", not written,
          "`auth_token` memang tidak pernah ditulis — jadi memakainya sebagai "
          "cadangan SELALU menghasilkan `Bearer null` (ini alasan B-1 ada)")

    app = (SRC / "App.js").read_text()
    check("B-3", "setItem('erp_token'" in app,
          "kunci token yang benar (`erp_token`) memang ditulis saat login")


NEW_COMPONENTS = {
    "components/erp/pickers/MasterProductSelect.jsx": ("bg-popover", "bg-background"),
    "components/erp/pickers/BuyerCatalogSelect.jsx": ("bg-background",),
}


def section_komponen_baru():
    print(f"\n{B}[C] Komponen baru punya latar tegas (bukan transparan){X}")
    for rel, needles in NEW_COMPONENTS.items():
        f = SRC / rel
        name = Path(rel).name
        if not check(f"C-1·{name}", f.exists(), f"{rel} ada"):
            continue
        s = f.read_text()
        check(f"C-2·{name}", any(n in s for n in needles),
              f"{name} memakai latar tegas ({'/'.join(needles)}) — dropdown & "
              f"kotak isian tanpa latar akan menampilkan apa pun di belakangnya")


def section_picking_modal():
    print(f"\n{B}[D] Modal tidak memakai variabel milik komponen lain{X}")
    f = SRC / "components/erp/marketing/UnifiedOrdersDashboard.jsx"
    s = f.read_text()
    m = re.search(r"function PickingListModal\(\{([^}]*)\}", s)
    check("D-1", bool(m) and "accountFilter" in (m.group(1) if m else ""),
          "`PickingListModal` menerima `accountFilter` sebagai PROP "
          "(dulu memakai variabel induk ⇒ ReferenceError begitu modal dibuka)")
    check("D-2", "accountFilter={accountFilter}" in s,
          "pemanggilnya benar-benar mengirim lingkup toko yang sedang dipilih — "
          "daftar picking tidak diam-diam mencakup semua toko")


def main() -> int:
    print(f"{B}══ CORE TEST F15 — KARTU PUNYA LATAR & TULISANNYA TERBACA ══{X}")
    section_audit()
    section_token()
    section_komponen_baru()
    section_picking_modal()

    passed = sum(1 for _, p, _ in RES if p)
    total = len(RES)
    print(f"\n{B}{'═' * 70}{X}")
    for code, p, msg in RES:
        if not p:
            print(f"  {R}GAGAL{X} [{code}] {msg}")
    print(f"{B}HASIL: {passed}/{total} penjaga LULUS{X}")
    print("  " + (G + "HIJAU" + X if passed == total else R + "MERAH" + X))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
