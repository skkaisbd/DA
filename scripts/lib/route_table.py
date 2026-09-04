"""route_table — SSOT tabel route backend (GROUND TRUTH) untuk guardrail.
=========================================================================

## Kenapa modul ini ada (guardrail yang berbohong, FASE 14)

`gr_common.all_routes()` membaca path dari **dekorator** saja
(`@router.get("/dashboard")`) dan **tidak pernah me-resolve `prefix=`** pada
`APIRouter(prefix=...)` / `app.include_router(..., prefix=...)`.

Akibatnya CHECK A (`DUP_ROUTE`, severity HIGH) **berbohong dua arah**:

**5 FALSE POSITIVE** — dilaporkan HIGH "hanya definisi TERAKHIR yang aktif",
padahal keempat/keduanya hidup di path berbeda karena prefix router berbeda:

| Dilaporkan | Kenyataan |
|---|---|
| `GET /dashboard` 4× | `/api/assets/dashboard`, `/api/acc/dashboard`, `/api/dewi/portal-saya/hr/dashboard`, `/api/dewi/rnd/design/dashboard` |
| `GET|POST /loans` | `/api/assets/loans` vs `/api/acc/loans` |
| `GET|POST /materials` | `/api/dewi/rnd/materials` vs `/api/rahaza/inventory/materials` |

**7 FALSE NEGATIVE** — duplikat NYATA yang TIDAK PERNAH terlihat: seluruh
`routes/marketing_task_templates.py` di-`include_router()` **DUA KALI** di
`server.py` (baris 1452 & 1696). Scan dekorator mustahil melihat ini — dari sisi
file, tiap route hanya ditulis sekali.

Guardrail yang merah untuk hal yang salah **lebih buruk daripada tidak ada**:
9 HIGH yang 5-nya palsu membuat semua orang berhenti percaya, lalu 7 duplikat
sungguhan lewat tanpa diperiksa selama berbulan-bulan.

## Solusinya: tanya SUMBER KEBENARAN, jangan menebak dari teks
`runtime_route_table()` mengimpor `server.app` **di subprocess terpisah** lalu
menyalin `app.routes` — tabel yang PERSIS dipakai FastAPI saat melayani request.
Ini tidak bisa keliru soal prefix maupun include ganda.

Subprocess dipakai supaya:
  * efek samping impor `server.py` tidak mengotori proses guardrail;
  * kegagalan (env kurang / DB mati) tidak merobohkan gate — tinggal `None`
    lalu pemanggil jatuh ke AST dengan label jujur "bukan ground truth".

`/api/openapi.json` TIDAK dipakai untuk ini: OpenAPI menyimpan path sebagai
kunci dict, jadi duplikat justru HILANG dari sana — persis informasi yang dicari.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path("/app/backend")

# Skrip yang dijalankan di subprocess. Sengaja pendek & tanpa dependensi lain.
_DUMPER = r"""
import json, os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

# Bungkam log startup router supaya stdout hanya berisi JSON.
import logging
logging.disable(logging.CRITICAL)

import io, contextlib
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
    from server import app

out = []
for r in app.routes:
    path = getattr(r, "path", None)
    if not path:
        continue
    ep = getattr(r, "endpoint", None)
    mod = getattr(ep, "__module__", "") if ep else ""
    fn = getattr(ep, "__name__", "") if ep else ""
    methods = getattr(r, "methods", None)
    if not methods:
        # WebSocketRoute tidak punya `.methods`. FASE 19: dulu route WebSocket
        # HILANG dari tabel ini, sehingga `/api/comm/ws` (dipakai
        # useCommWebSocket.js) selalu dilaporkan "FE memanggil endpoint yang
        # tidak ada" — padahal route-nya hidup. OpenAPI juga tidak memuatnya,
        # jadi tabel ini satu-satunya tempat ia bisa terlihat.
        if r.__class__.__name__ == "WebSocketRoute" or hasattr(r, "session"):
            out.append({"method": "WEBSOCKET", "path": path, "module": mod, "func": fn})
        continue
    for m in methods:
        if m in ("HEAD", "OPTIONS"):
            continue
        out.append({"method": m, "path": path, "module": mod, "func": fn})
sys.stdout.write("@@ROUTES@@" + json.dumps(out))
"""


def runtime_route_table(timeout: int = 240) -> list[dict] | None:
    """Tabel route SUNGGUHAN dari `app.routes`. None bila gagal dimuat.

    Return: [{method, path, module, func}, …] — path SUDAH termasuk prefix.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DUMPER],
            cwd=str(BACKEND), capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONWARNINGS": "ignore"},
        )
    except Exception:
        return None
    marker = "@@ROUTES@@"
    if marker not in (proc.stdout or ""):
        return None
    try:
        data = json.loads(proc.stdout.split(marker, 1)[1])
    except Exception:
        return None
    return data if isinstance(data, list) and data else None


def duplicate_routes(table: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """(METHOD, path) yang punya >1 handler → daftar handler (urutan registrasi).

    ┌─ KOREKSI FASE 19 ──────────────────────────────────────────────────────────┐
    │ Docstring ini DULU menyatakan "Handler TERAKHIR-lah yang dipakai FastAPI".  │
    │ Itu **SALAH** dan berlawanan arah dengan `scripts/audit_duplication.py`     │
    │ yang menyatakan yang DIDAFTARKAN DULUAN yang menang. Dua alat penjaga yang  │
    │ saling bertentangan ⇒ triase-nya bisa memperbaiki handler yang salah.      │
    │                                                                            │
    │ Dibuktikan dengan menanyakan framework-nya, bukan membaca dokumen:          │
    │   `python3 scripts/probe_fastapi_duplicate_route_semantics.py`              │
    │   dekorator langsung ×2          → FIRST                                    │
    │   include_router ×2 prefix sama  → FIRST                                    │
    │ Starlette `Router.app` menelusuri `self.routes` dan BERHENTI pada kecocokan │
    │ PERTAMA ⇒ **yang didaftarkan DULUAN menang, yang belakangan MATI.**         │
    └────────────────────────────────────────────────────────────────────────────┘
    """
    seen: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in table:
        seen[(r["method"], r["path"])].append(r)
    return {k: v for k, v in seen.items() if len(v) > 1}


def describe_duplicate(method: str, path: str, owners: list[dict]) -> tuple[str, str]:
    """(pesan, lokasi) siap dipakai laporan guardrail.

    Membedakan dua penyakit yang penanganannya BEDA:
      * `include_router` ganda  → semua owner modul+fungsi sama ⇒ perbaiki server.py
      * dua implementasi beda   → owner berbeda ⇒ satu handler MATI, cek perilakunya

    Pemenangnya adalah handler PERTAMA (lihat koreksi di `duplicate_routes`).
    """
    sigs = [f'{o.get("module")}.{o.get("func")}' for o in owners]
    uniq = list(dict.fromkeys(sigs))
    winner = sigs[0]
    losers = sigs[1:]
    if len(uniq) == 1:
        msg = (f"{method} {path} terdaftar {len(owners)}x oleh handler yang SAMA "
               f"({uniq[0]}) — router di-include lebih dari sekali di server.py")
    else:
        msg = (f"{method} {path} punya {len(owners)} handler BERBEDA — "
               f"aktif: {winner} · MATI: {', '.join(losers)}")
    return msg, "; ".join(sigs)
