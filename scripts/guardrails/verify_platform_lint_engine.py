#!/usr/bin/env python3
"""INV-LINT-01 — GATE LINT PLATFORM harus benar-benar bisa JALAN & LULUS.

═══════════════════════════════════════════════════════════════════════════════
KELAS BUG YANG DIJAGA — "sesi selesai tapi tidak bisa diserahkan"
═══════════════════════════════════════════════════════════════════════════════
Gate pra-penyelesaian platform MELEMPAR

    "JavaScript linting failed due to a linter engine error."

dan itu MEM-BLOK tool `finish` / `ask_human`. Jadi sebuah sesi bisa
menyelesaikan seluruh pekerjaannya lalu **tidak bisa menyerahkan hasilnya**.
Itu persis yang terjadi di akhir FASE 20.

═══════════════════════════════════════════════════════════════════════════════
AKAR MASALAH YANG SEBENARNYA (FASE 21 — dua RCA sebelumnya KELIRU)
═══════════════════════════════════════════════════════════════════════════════
Kode platform (`linters/lint_tools.py`, `linters/engines.py`,
`plugins/tools/agent/mcp_tools.py::lint_javascript_oxlint`) dibaca langsung:

    engine_success = oxlint_success AND import_success        # per grup paket
    ...
    if blocking_count == 0 and not engine_success:  raise ToolError(...)

Tiga fakta yang mengubah segalanya:
  1. Gate memakai arm **OXLINT**, bukan ESLint (`tool=lint_javascript_oxlint
     path=/app/frontend` di log). Semua diagnosa yang memperbaiki ESLint saja
     tidak pernah menyentuh penyebabnya.
  2. oxlint rc=1 (ADA temuan) **dianggap sukses**. Jadi temuan lint bukan
     penyebabnya.
  3. Yang menjatuhkannya adalah **Import Validation**: 35 import relatif YATIM
     di `frontend/src/components/erp/_archive/**` — akibat praktik "pindahkan
     modul mati ke `_archive/`" yang memindahkan berkasnya tapi tidak
     memperbarui import relatifnya — plus `setupTests.js` mengimpor
     `@testing-library/jest-dom` yang tidak ada di `package.json`.
     `import_success = False` ⇒ `engine_success = False`; dan karena SELURUH
     temuan oxlint tersaring habis oleh allowlist, `blocking_count = 0` ⇒
     tepat kombinasi yang melempar "engine error".

     ⇒ FASE 20 merusaknya SENDIRI di sesi yang sama (ia yang mengarsipkan
       `CMTManagementModule` / `CMTProgressModule` / `CMTPackingModule`).

Kenapa dua RCA sebelumnya keliru:
  · FASE 12 menyalahkan `mobile/eslint.config.js` (MODULE_NOT_FOUND).
  · FASE 14 menyalahkan symlink `eslint-formatter-unix` dan "membuktikan"
    `eslint . --format unix` rc=0 — perintah yang **tidak pernah dijalankan
    platform** (platform memakai `--format=<abs>` + `--config <abs>`).
  · FASE 21 iterasi-1 (guard ini sendiri) menguji **arm ESLint**. Ia HIJAU
    sementara gate tetap MERAH.
  ⇒ Pelajaran yang sama tiga kali: **menguji sesuatu yang mirip ≠ menguji yang
    dipakai.** Karena itu guard ini memanggil FUNGSI PLATFORM-nya sendiri,
    untuk KEDUA arm, pada CAKUPAN yang sama dengan gate.

SEVERITY
  HIGH  `engine_success = False` pada arm/cakupan mana pun ⇒ gate akan menolak
        `finish`/`ask_human`. MEM-BLOK.
  WARN  risiko laten: arm ESLint pada cakupan gabungan mobile+frontend
        (config `expo`) melewati batas waktu 60 detik platform.
  INFO  paket `linters` platform tak bisa diimpor (environment non-Emergent) —
        tidak diuji, bukan merah palsu.

Usage:
  cd /app && python3 scripts/guardrails/verify_platform_lint_engine.py [--quiet]
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from gr_common import Report, ROOT  # noqa: E402

_CANDIDATE_SITE_PACKAGES = sorted(
    Path("/opt/plugins-venv/lib").glob("python3.*/site-packages")
) + [Path("/opt/plugins-venv/lib/python3.11/site-packages")]

# Batas waktu subprocess platform (linters/engines.py). Dipakai untuk WARN laten.
PLATFORM_TIMEOUT_S = 60


def _import_platform():
    for sp in _CANDIDATE_SITE_PACKAGES:
        if not sp.is_dir():
            continue
        if str(sp) not in sys.path:
            sys.path.insert(0, str(sp))
        try:
            from linters.lint_tools import (  # noqa: PLC0415
                run_javascript_linter,
                run_javascript_oxlint_linter,
            )
            from linters.import_validator import ImportValidator  # noqa: PLC0415
            from linters.lint_utils import (  # noqa: PLC0415
                JAVASCRIPT_EXTENSIONS,
                _normalize_candidate_paths,
            )
            return {
                "oxlint": run_javascript_oxlint_linter,
                "eslint": run_javascript_linter,
                "ImportValidator": ImportValidator,
                "normalize": _normalize_candidate_paths,
                "js_ext": JAVASCRIPT_EXTENSIONS,
                "err": None,
            }
        except Exception as e:  # noqa: BLE001
            last = e
    return {"err": locals().get("last", ImportError("paket `linters` platform tak ada"))}


def _scopes(workspace: str) -> list[str]:
    """Cakupan yang REALISTIS dilint gate: tiap akar paket + root workspace."""
    out = [workspace]
    for name in ("frontend", "mobile"):
        p = os.path.join(workspace, name)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "package.json")):
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--deep", action="store_true",
                    help="ikut menguji risiko LATEN cakupan gabungan expo "
                         "(memakan ~60 detik; tidak dijalankan gate default)")
    args = ap.parse_args()

    rep = Report(
        "INV-LINT-01",
        "Gate lint platform bisa jalan & lulus (oxlint + import validation)",
        block_sev=() if args.report_only else ("HIGH",),
    )

    P = _import_platform()
    if P.get("err"):
        rep.add("INFO", "LINT-NOPLATFORM",
                f"paket linter platform tak bisa diimpor ({P['err']}) — tidak diuji")
        return rep.finish()

    workspace = os.environ.get("WORKSPACE_ROOT", str(ROOT))
    scopes = _scopes(workspace)

    async def probe():
        # ── 1. IMPORT VALIDATION — faktor tersembunyi yang menjatuhkan gate ──
        for scope in scopes:
            rep.bump()
            v = P["ImportValidator"](workspace)
            out, ok = await v.validate_directory(scope)
            rel = os.path.relpath(scope, workspace) or "."
            if not ok:
                first = next((ln.strip() for ln in (out or "").splitlines()
                              if ln.strip()), "(tanpa detail)")
                n = len([ln for ln in (out or "").splitlines() if " - " in ln])
                rep.add("HIGH", "LINT-IMPORT-BROKEN",
                        f"Import Validation GAGAL pada '{rel}' ({n} temuan) ⇒ "
                        f"engine_success=False ⇒ gate menolak `finish`/`ask_human`. "
                        f"Pertama: {first}", rel)
            elif not args.quiet:
                print(f"    ✓ import validation '{rel}': BERSIH")

        # ── 2. ARM OXLINT — inilah yang dipakai gate pra-penyelesaian ────────
        for scope in scopes:
            rep.bump()
            rel = os.path.relpath(scope, workspace) or "."
            t = time.monotonic()
            r = await P["oxlint"]([scope], trigger="guardrail")
            dt = time.monotonic() - t
            if not r.files_checked:
                if not args.quiet:
                    print(f"    · oxlint '{rel}': tak ada berkas JS/TS — dilewati")
                continue
            if not r.engine_success:
                raw = (getattr(r, "engine_output", "") or "")[:300].replace("\n", " | ")
                rep.add("HIGH", "LINT-ENGINE-DOWN",
                        f"arm OXLINT '{rel}': engine_success=False ⇒ gate akan "
                        f"menolak `finish`/`ask_human`. Keluaran: {raw}", rel)
            elif not args.quiet:
                print(f"    ✓ oxlint '{rel}': engine JALAN ({len(r.files_checked)} berkas, "
                      f"{dt:.1f}s, blocking {r.blocking_count})")

        # ── 3. ARM ESLINT — hanya dengan --deep (lambat, bukan arm yang dipakai gate)
        # Gate pra-penyelesaian memakai arm OXLINT (§2). Arm ESLint dipakai tool
        # `lint_javascript` yang jarang dipanggil, dan memakan ~11 detik/cakupan.
        for scope in (scopes if args.deep else []):
            rep.bump()
            rel = os.path.relpath(scope, workspace) or "."
            t = time.monotonic()
            r = await P["eslint"]([scope], trigger="guardrail")
            dt = time.monotonic() - t
            if not r.files_checked:
                continue
            raw = (getattr(r, "raw_output", "") or "")
            if not r.engine_success or raw.startswith("❌"):
                rep.add("HIGH", "LINT-ESLINT-DOWN",
                        f"arm ESLINT '{rel}': engine tidak jalan. "
                        f"Keluaran: {' | '.join(raw.splitlines()[:5])[:300]}", rel)
            elif not args.quiet:
                print(f"    ✓ eslint '{rel}': engine JALAN ({len(r.files_checked)} berkas, "
                      f"{dt:.1f}s, blocking {r.blocking_count})")

        # ── 4. RISIKO LATEN — cakupan gabungan dgn berkas Expo di posisi 1 ───
        # `_detect_framework` memakai path PERTAMA, jadi kalau gate suatu hari
        # melint mobile+frontend bersama dengan berkas mobile di depan, config
        # `expo` (yang memuat eslint-plugin-import) dipakai untuk SEMUA 600+
        # berkas frontend dan menembus batas 60 detik platform.
        allf = P["normalize"]([workspace], P["js_ext"])
        mob = [f for f in allf if f"{os.sep}mobile{os.sep}" in f]
        oth = [f for f in allf if f not in mob]
        if args.deep and mob and oth:
            rep.bump()
            t = time.monotonic()
            r = await P["eslint"](mob + oth, trigger="guardrail")
            dt = time.monotonic() - t
            raw = (getattr(r, "raw_output", "") or "")
            if not r.engine_success and "timed out" in raw:
                rep.add("WARN", "LINT-EXPO-SCOPE-SLOW",
                        f"risiko LATEN: bila gate melint mobile+frontend bersama "
                        f"(berkas Expo di posisi pertama), config `expo` dipakai untuk "
                        f"{len(allf)} berkas dan MELEWATI batas {PLATFORM_TIMEOUT_S}s "
                        f"({dt:.0f}s). Penutup permanennya: arsipkan `mobile/` "
                        f"(scaffold Expo, tanpa fitur ERP) atau pasang dependensinya.")
            elif not args.quiet:
                print(f"    ✓ cakupan gabungan (expo-first): {dt:.1f}s, "
                      f"engine_success={r.engine_success}")

    asyncio.run(probe())

    if any(f.sev == "HIGH" for f in rep.findings):
        print("\n    PERBAIKAN:")
        print("      python3 scripts/fix_archive_import_paths.py --dry-run  # lalu --apply")
        print("      bash    scripts/fix_root_lint_resolution.sh")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
