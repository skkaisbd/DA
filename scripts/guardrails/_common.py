"""Shared helpers for da guardrail scanners (adapted from Rahaza-Travel)."""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"


class Guard:
    """Minimal guard-result accumulator with a consistent PASS/FAIL contract."""

    def __init__(self, inv_id: str, title: str):
        self.inv_id = inv_id
        self.title = title
        self.violations = []
        self.checked = 0
        print(f"\n{B}{'='*64}{X}\n  {inv_id} — {title}\n{B}{'='*64}{X}")

    def bump(self, n: int = 1):
        self.checked += n

    def add(self, msg: str):
        self.violations.append(msg)
        print(f"    {R}[FAIL]{X} {msg}")

    def finish(self) -> int:
        if self.violations:
            print(f"\n  {R}{B}✗ {self.inv_id} MERAH — {len(self.violations)} pelanggaran "
                  f"({self.checked} diperiksa).{X}\n")
            return 1
        print(f"\n  {G}{B}✓ {self.inv_id} HIJAU — {self.checked} diperiksa, 0 pelanggaran.{X}\n")
        return 0
