"""
CV. Dewi Aditya ERP — API v1 Path Rewriter
Batch 3 — E-6 (Path Consolidation) + E-7 (API Versioning)

Provides a unified /api/v1/* namespace that aliases the existing per-module paths.
The original paths remain 100% backward-compatible.

Path mapping:
  /api/v1/employees/**           -> /api/rahaza/employees/**
  /api/v1/payroll/profiles/**    -> /api/rahaza/payroll-profiles/**
  /api/v1/payroll/runs/**        -> /api/rahaza/payroll-runs/**
  /api/v1/salary/adjustments/**  -> /api/rahaza/salary-adjustments/**
  /api/v1/kpi/**                 -> /api/dewi/kpi/**
  /api/v1/journals/**            -> /api/rahaza/journals/**
  /api/v1/coa/**                 -> /api/rahaza/coa/**
  /api/v1/orders/**              -> /api/rahaza/orders/**
  /api/v1/materials/**           -> /api/rahaza/materials/**
  /api/v1/customers/**           -> /api/rahaza/customers/**
  /api/v1/attendance/**          -> /api/rahaza/attendance/**
  /api/v1/work-orders/**         -> /api/rahaza/work-orders/**
  /api/v1/finance/**             -> /api/finance/**
  /api/v1/marketing/**           -> /api/marketing/**
  /api/v1/hr/**                  -> /api/dewi/hr/** (where available)
"""
import re
import logging
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

# ── Ordered path rules: (pattern, replacement) ───────────────────────────────
# More specific rules first; each uses a regex match + re.sub replacement.
V1_RULES: list[tuple[re.Pattern, str]] = [
    # HR / People
    (re.compile(r"^/api/v1/employees"), "/api/rahaza/employees"),
    (re.compile(r"^/api/v1/attendance"), "/api/rahaza/attendance"),
    (re.compile(r"^/api/v1/salary/adjustments"), "/api/rahaza/salary-adjustments"),
    (re.compile(r"^/api/v1/salary/grades"), "/api/rahaza/salary-grades"),
    (re.compile(r"^/api/v1/salary"), "/api/rahaza/salary"),
    # Payroll — sub-resource mapping (hyphen → slash in v1)
    (re.compile(r"^/api/v1/payroll/profiles"), "/api/rahaza/payroll-profiles"),
    (re.compile(r"^/api/v1/payroll/allowances"), "/api/rahaza/payroll-allowances"),
    (re.compile(r"^/api/v1/payroll/runs"), "/api/rahaza/payroll-runs"),
    (re.compile(r"^/api/v1/payroll"), "/api/rahaza/payroll"),
    # KPI / Performance
    (re.compile(r"^/api/v1/kpi"), "/api/dewi/kpi"),
    # Finance / Accounting
    (re.compile(r"^/api/v1/journals"), "/api/rahaza/journals"),
    (re.compile(r"^/api/v1/coa"), "/api/rahaza/coa"),
    (re.compile(r"^/api/v1/finance"), "/api/finance"),
    # Inventory / Production
    (re.compile(r"^/api/v1/materials"), "/api/rahaza/materials"),
    (re.compile(r"^/api/v1/orders"), "/api/rahaza/orders"),
    (re.compile(r"^/api/v1/work-orders"), "/api/rahaza/work-orders"),
    (re.compile(r"^/api/v1/customers"), "/api/rahaza/customers"),
    # Marketing
    (re.compile(r"^/api/v1/marketing"), "/api/marketing"),
    # Catch-all: /api/v1/* -> /api/*  (for any unmapped paths)
    (re.compile(r"^/api/v1/"), "/api/"),
]


def rewrite_v1_path(path: str) -> str:
    """
    Translate an /api/v1/* path to the corresponding legacy path.
    Returns the original path if no rule matches.
    """
    for pattern, replacement in V1_RULES:
        if pattern.match(path):
            new_path = pattern.sub(replacement, path, count=1)
            log.debug(f"[API v1] {path} -> {new_path}")
            return new_path
    return path


class APIv1PathRewriteMiddleware:
    """
    ASGI middleware that rewrites /api/v1/* paths to legacy equivalents.
    Transparent to the app — modifies scope['path'] and scope['raw_path'].
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path.startswith("/api/v1/"):
                rewritten = rewrite_v1_path(path)
                if rewritten != path:
                    scope = dict(scope)
                    scope["path"] = rewritten
                    scope["raw_path"] = rewritten.encode()
        await self.app(scope, receive, send)
