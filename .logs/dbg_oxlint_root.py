#!/usr/bin/env python3
"""Probe: kenapa arm OXLINT pada cakupan ROOT '.' engine_success=False.

Dijalankan manual: cd /app && python3 .logs/dbg_oxlint_root.py
"""
import asyncio
import sys
from pathlib import Path

for sp in sorted(Path("/opt/plugins-venv/lib").glob("python3.*/site-packages")):
    sys.path.insert(0, str(sp))

from linters.lint_tools import run_javascript_oxlint_linter  # noqa: E402


async def main():
    for scope in ("/app", "/app/frontend"):
        r = await run_javascript_oxlint_linter([scope], trigger="guardrail")
        print("=" * 70)
        print("scope:", scope)
        print("engine_success:", r.engine_success)
        print("files_checked:", len(r.files_checked or []))
        print("blocking_count:", r.blocking_count)
        eo = getattr(r, "engine_output", "") or ""
        print("engine_output[:3000]:", eo[:3000])
        for attr in ("raw_output", "error", "stderr"):
            v = getattr(r, attr, None)
            if v:
                print(f"{attr}[:1500]:", str(v)[:1500])


asyncio.run(main())
