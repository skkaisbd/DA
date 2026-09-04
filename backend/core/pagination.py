"""Shared server-side pagination helpers (Phase 10A, moved in Backend Refactor Phase 0).

Backward-compatible pagination:
  - If the request includes `page` OR `per_page`, the endpoint returns a
    paginated envelope: {"items": [...], "total": N, "page": P,
    "per_page": M, "total_pages": T}.
  - Otherwise, the endpoint returns the legacy array response — but with a
    safety cap applied to the underlying Mongo query so no request can load
    unbounded data by accident.

Pure move from server.py — behavior is byte-for-byte identical.
"""

LEGACY_DEFAULT_CAP = 1000   # hard cap when no pagination requested
PAGE_DEFAULT_SIZE = 20
PAGE_MAX_SIZE = 200


def _paginate_params(sp):
    """Parse `page` / `per_page` from query params.

    Returns (page, per_page, skip, wants_paginated)
    where `wants_paginated` is True only when the caller explicitly asked.
    """
    page_raw = sp.get('page')
    per_page_raw = sp.get('per_page')
    wants = page_raw is not None or per_page_raw is not None
    try:
        page = max(1, int(page_raw)) if page_raw is not None else 1
    except Exception:
        page = 1
    try:
        per_page = int(per_page_raw) if per_page_raw is not None else PAGE_DEFAULT_SIZE
    except Exception:
        per_page = PAGE_DEFAULT_SIZE
    per_page = max(1, min(per_page, PAGE_MAX_SIZE))
    skip = (page - 1) * per_page
    return page, per_page, skip, wants


def _paginated_envelope(items, total, page, per_page):
    total_pages = (total + per_page - 1) // per_page if per_page else 1
    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    }


def _sort_params(sp, default_by='created_at', default_dir='desc', allowed=None):
    """Parse `sort_by` / `sort_dir` query params. Returns list suitable for Mongo .sort().
    `allowed` is an optional whitelist of sortable field names.
    """
    by = sp.get('sort_by') or default_by
    if allowed is not None and by not in allowed:
        by = default_by
    dir_raw = (sp.get('sort_dir') or default_dir).lower()
    direction = 1 if dir_raw == 'asc' else -1
    return [(by, direction)]
