"""Shared document-enrichment helpers (moved in Backend Refactor Phase 0).

Pure move from server.py — behavior is byte-for-byte identical.
"""


async def enrich_with_product_photos(items, db):
    """Attach product photo (if any) to each item dict.

    Looks up `products` by the unique product_ids referenced in `items` and
    adds `product_photo` and `product_photo_url` keys (None when missing).
    Items without a product_id are returned unchanged. Safe on empty input.
    """
    if not items:
        return items
    product_ids = list({it.get('product_id') for it in items if it.get('product_id')})
    if not product_ids:
        return items
    photo_docs = await db.products.find(
        {'id': {'$in': product_ids}},
        {'_id': 0, 'id': 1, 'photo': 1, 'photo_url': 1}
    ).to_list(None)
    photo_map = {d['id']: d for d in photo_docs}
    for it in items:
        pid = it.get('product_id')
        meta = photo_map.get(pid) if pid else None
        if meta:
            if 'photo' in meta and meta.get('photo') is not None:
                it.setdefault('product_photo', meta['photo'])
            if 'photo_url' in meta and meta.get('photo_url') is not None:
                it.setdefault('product_photo_url', meta['photo_url'])
    return items
