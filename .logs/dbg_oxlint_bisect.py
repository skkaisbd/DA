#!/usr/bin/env python3
"""Bisect: cakupan mana yang membuat arm OXLINT engine_success=False."""
import asyncio
import sys
from pathlib import Path

for sp in sorted(Path("/opt/plugins-venv/lib").glob("python3.*/site-packages")):
    sys.path.insert(0, str(sp))

from linters.lint_tools import run_javascript_oxlint_linter  # noqa: E402


async def main():
    for scope in ("/app/mobile", "/app/backups", "/app/eslint.config.js",
                  "/app/tests", "/app/scripts"):
        if not Path(scope).exists():
            print(scope, "TIDAK ADA")
            continue
        r = await run_javascript_oxlint_linter([scope], trigger="guardrail")
        print(f"{scope:28s} engine_success={r.engine_success} "
              f"files={len(r.files_checked or [])} blocking={r.blocking_count}")


asyncio.run(main())
