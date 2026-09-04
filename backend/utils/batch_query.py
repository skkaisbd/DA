"""Helper utilities for batch DB operations to eliminate N+1 patterns.

Usage example:
    from utils.batch_query import prefetch_map, prefetch_group

    pos = await db.production_pos.find({...}).to_list(length=10000)
    po_ids = [p['po_id'] for p in pos]
    items_by_po = await prefetch_group(db.po_items, 'po_id', po_ids)
    # items_by_po[po_id] -> [item, item, ...]

    refs_by_id = await prefetch_map(db.production_pos, po_ids)
    # refs_by_id[po_id] -> single doc
"""
from typing import Iterable, List, Dict, Any, Optional


async def prefetch_map(
    collection,
    ids: Iterable[Any],
    *,
    key: str = "id",
    projection: Optional[dict] = None,
) -> Dict[Any, dict]:
    """Fetch many docs in a single `$in` query and return a {id: doc} map.

    - Strips `_id` from all returned docs unless projection says otherwise.
    - Returns empty dict when `ids` is empty (no DB call).
    """
    ids = [i for i in ids if i is not None and i != ""]
    if not ids:
        return {}
    proj = projection if projection is not None else {"_id": 0}
    cursor = collection.find({key: {"$in": list(set(ids))}}, proj)
    docs = await cursor.to_list(length=None)
    return {d.get(key): d for d in docs if d.get(key) is not None}


async def prefetch_group(
    collection,
    foreign_key: str,
    ids: Iterable[Any],
    *,
    projection: Optional[dict] = None,
    sort: Optional[List[tuple]] = None,
) -> Dict[Any, List[dict]]:
    """Fetch all child docs whose foreign_key in ids, grouped by foreign_key.

    Returns {fk_value: [doc, ...]}.
    """
    ids = [i for i in ids if i is not None and i != ""]
    if not ids:
        return {}
    proj = projection if projection is not None else {"_id": 0}
    cursor = collection.find({foreign_key: {"$in": list(set(ids))}}, proj)
    if sort:
        cursor = cursor.sort(sort)
    docs = await cursor.to_list(length=None)
    grouped: Dict[Any, List[dict]] = {}
    for d in docs:
        fk = d.get(foreign_key)
        if fk is None:
            continue
        grouped.setdefault(fk, []).append(d)
    return grouped


async def prefetch_count_group(
    collection,
    foreign_key: str,
    ids: Iterable[Any],
    *,
    extra_query: Optional[dict] = None,
) -> Dict[Any, int]:
    """Single aggregate to count docs grouped by foreign_key. Returns {fk: count}."""
    ids = [i for i in ids if i is not None and i != ""]
    if not ids:
        return {}
    match: Dict[str, Any] = {foreign_key: {"$in": list(set(ids))}}
    if extra_query:
        match.update(extra_query)
    pipeline = [
        {"$match": match},
        {"$group": {"_id": f"${foreign_key}", "n": {"$sum": 1}}},
    ]
    out: Dict[Any, int] = {}
    async for row in collection.aggregate(pipeline):
        out[row["_id"]] = row["n"]
    return out
